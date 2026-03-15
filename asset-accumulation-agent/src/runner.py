"""Runner - エージェントスケジューラ

使い方:
    python -m src.runner --once                    # 全エージェント1回
    python -m src.runner --agent audio_pack --once # 指定エージェントのみ
    python -m src.runner --daemon                  # 24時間稼働
    python -m src.runner --stats                   # 蓄積状況レポート
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

from .agent import BaseAgent, Context
from .catalog import Catalog
from .config import get_agent_config, load_config
from .quality import run_quality_check

logger = logging.getLogger(__name__)


def discover_agents() -> dict[str, type[BaseAgent]]:
    """組み込みエージェントを検出して返す。"""
    agents: dict[str, type[BaseAgent]] = {}
    try:
        from .agents import AGENT_REGISTRY

        agents.update(AGENT_REGISTRY)
    except ImportError:
        pass
    return agents


def create_agent(
    agent_cls: type[BaseAgent], config: dict[str, Any]
) -> BaseAgent:
    """設定からエージェントインスタンスを生成する。"""
    params = config.get("params", {})
    interval = config.get("interval", agent_cls.interval_seconds)
    agent = agent_cls(params=params)
    agent.interval_seconds = interval
    return agent


def run_agent_cycle(
    agent: BaseAgent,
    ctx: Context,
    catalog: Catalog,
    quality_threshold: float = 0.7,
) -> int:
    """エージェントを1サイクル実行し、品質チェックを通過したアセット数を返す。"""
    logger.info(f"[{agent.name}] サイクル開始")
    start = time.time()

    try:
        assets = agent.run(ctx)
    except Exception as e:
        logger.error(f"[{agent.name}] 実行エラー: {e}")
        agent.mark_run()
        return 0

    passed = 0
    for asset in assets:
        ok, score = run_quality_check(asset, quality_threshold)
        asset.quality_score = score
        if ok:
            asset.status = "quality_passed"
            passed += 1
        catalog.add(asset)

    agent.mark_run()
    elapsed = time.time() - start
    logger.info(
        f"[{agent.name}] 完了: {len(assets)}件生成, {passed}件品質通過 ({elapsed:.1f}s)"
    )
    return passed


def print_stats(catalog: Catalog) -> None:
    """蓄積状況レポートを表示する。"""
    stats = catalog.stats()
    print("\n=== 資産蓄積レポート ===\n")
    print(f"総アセット数: {stats['total_assets']}")
    print(f"推定総価値: ¥{stats['total_estimated_value_yen']:,.0f}")
    print()

    if stats["by_agent"]:
        print("--- エージェント別 ---")
        for name, data in stats["by_agent"].items():
            print(f"  {name}: {data['count']}件 (¥{data['total_value_yen']:,.0f})")
        print()

    if stats["by_status"]:
        print("--- ステータス別 ---")
        for status, count in stats["by_status"].items():
            print(f"  {status}: {count}件")
    print()

    # カタログ成長分析
    growth = catalog.growth_stats()
    if growth["total_products"] > 0:
        print("=== カタログ成長レポート ===\n")
        print(f"総商品数: {growth['total_products']}")
        print(f"パッケージ済: {growth['packaged_count']}")
        print(f"クロスリファレンス密度: {growth['cross_reference_density']} (1商品あたり)")
        print(f"推定月間露出: {growth['estimated_exposure']}回")
        print()

        if growth["by_product_type"]:
            print("--- 商品タイプ別 ---")
            for ptype, count in growth["by_product_type"].items():
                print(f"  {ptype}: {count}件")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Asset Accumulation Agent Runner")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルパス")
    parser.add_argument("--once", action="store_true", help="全エージェント1回実行")
    parser.add_argument("--agent", type=str, help="指定エージェントのみ実行")
    parser.add_argument("--daemon", action="store_true", help="デーモンモード（24時間稼働）")
    parser.add_argument("--stats", action="store_true", help="蓄積状況レポート表示")
    parser.add_argument("--interval", type=int, default=60, help="デーモンモードのチェック間隔（秒）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config(args.config)
    catalog = Catalog(config["catalog_path"])
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.stats:
        print_stats(catalog)
        return

    # エージェント検出・初期化
    registry = discover_agents()
    if not registry:
        logger.warning("登録済みエージェントがありません")
        return

    agents: list[BaseAgent] = []
    for name, cls in registry.items():
        agent_config = get_agent_config(config, name)
        if not agent_config.get("enabled", True):
            logger.info(f"[{name}] 無効化されています、スキップ")
            continue
        if args.agent and name != args.agent:
            continue
        agent = create_agent(cls, agent_config)
        agents.append(agent)
        logger.info(f"[{name}] 初期化完了 (interval={agent.interval_seconds}s)")

    if not agents:
        logger.warning("実行対象のエージェントがありません")
        return

    ctx = Context(output_dir=output_dir, config=config, catalog=catalog)

    if args.once or args.agent:
        # 1回実行モード
        for agent in agents:
            run_agent_cycle(agent, ctx, catalog)
        print_stats(catalog)
        return

    if args.daemon:
        # デーモンモード
        shutdown = False

        def handle_signal(signum: int, frame: Any) -> None:
            nonlocal shutdown
            logger.info("シャットダウンシグナルを受信、現在のサイクル完了後に停止します...")
            shutdown = True

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        logger.info(f"デーモンモード開始 (チェック間隔: {args.interval}s)")
        cycle = 0

        while not shutdown:
            # 各エージェントのestimate_valueでソートし、高い順に実行
            runnable = [a for a in agents if a.should_run(catalog)]
            if runnable:
                runnable.sort(key=lambda a: a.estimate_value(catalog), reverse=True)
                for agent in runnable:
                    if shutdown:
                        break
                    ctx.cycle = cycle
                    run_agent_cycle(agent, ctx, catalog)
                cycle += 1

            if not shutdown:
                time.sleep(args.interval)

        logger.info("シャットダウン完了")
        print_stats(catalog)
        return

    # デフォルト: --once と同じ
    for agent in agents:
        run_agent_cycle(agent, ctx, catalog)
    print_stats(catalog)


if __name__ == "__main__":
    main()
