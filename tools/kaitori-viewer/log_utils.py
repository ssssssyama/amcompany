"""実行ログの保存・共有ヘルパー

run.py が起動時にログファイルを1つ作成し、環境変数
`KAITORI_LOG_FILE` で全サブプロセスに渡す。price_server/
auto_extract は同じファイルに追記することで、1実行分のログが
時系列で1ファイルにまとまる。

サマリJSONも同じ日時名で保存され、後から集計・検証できる。

ログディレクトリ: ~/.kaitori-viewer/logs/
  run_YYYYMMDDHHMM.log         # 全プロセスのログ（追記）
  summary_YYYYMMDDHHMM.json    # run.py のサマリ（1実行分）

古いログは rotate_logs() で最大 N 件に制限される（デフォルト30件）。
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".kaitori-viewer" / "logs"
ENV_LOG_FILE = "KAITORI_LOG_FILE"
ENV_LOG_RUN_TS = "KAITORI_LOG_RUN_TS"


def create_run_log_file() -> Path:
    """新しい実行用ログファイルを作成し、環境変数にパスをセットする。

    run.py が起動時に1回だけ呼び、子プロセスは `attach_to_log_file` で
    同じファイルに追記する。

    Returns:
        作成したログファイルのパス
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M")
    log_file = LOG_DIR / f"run_{ts}.log"
    # ヘッダを書き込む
    header = (
        f"=== 買取価格ツール 実行ログ ===\n"
        f"開始時刻: {datetime.now().isoformat(timespec='seconds')}\n"
        f"ログファイル: {log_file}\n"
        f"{'=' * 60}\n"
    )
    log_file.write_text(header, encoding="utf-8")
    # 環境変数で子プロセスに共有
    os.environ[ENV_LOG_FILE] = str(log_file)
    os.environ[ENV_LOG_RUN_TS] = ts
    return log_file


def attach_to_log_file(logger: logging.Logger | None = None) -> Path | None:
    """環境変数 KAITORI_LOG_FILE が設定されていれば、その FileHandler を
    logger に追加する。

    price_server / auto_extract / 各 worker から呼び、同じファイルに
    ログを集約する。

    Args:
        logger: ロガー。None なら root logger

    Returns:
        追加されたログファイルのパス（env var 未設定なら None）
    """
    log_path = os.environ.get(ENV_LOG_FILE)
    if not log_path:
        return None
    log_file = Path(log_path)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # 既に同じファイルのハンドラが付いていれば skip
        target = logger if logger else logging.getLogger()
        for h in target.handlers:
            if isinstance(h, logging.FileHandler) and \
               Path(h.baseFilename).resolve() == log_file.resolve():
                return log_file
        handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(processName)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        target.addHandler(handler)
        # root logger を使う場合 INFO 以上を拾う
        if target.level == logging.NOTSET or target.level > logging.INFO:
            target.setLevel(logging.INFO)
        return log_file
    except OSError as e:
        # ログファイルが書けなくても機能は続行
        print(f"[log_utils] ログファイル添付失敗: {e}", flush=True)
        return None


def save_summary(summary: dict, ts: str | None = None) -> Path | None:
    """run.py のサマリを JSON で保存する。

    Args:
        summary: サマリ dict（件数・TOP商品・更新情報等）
        ts: タイムスタンプ文字列（省略時は env var から取得、さらに無ければ現在時刻）

    Returns:
        保存した JSON ファイルのパス
    """
    if ts is None:
        ts = os.environ.get(ENV_LOG_RUN_TS) or datetime.now().strftime("%Y%m%d%H%M")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"summary_{ts}.json"
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path
    except OSError as e:
        print(f"[log_utils] サマリ保存失敗: {e}", flush=True)
        return None


def rotate_logs(max_runs: int = 30) -> int:
    """古いログを削除して最新 N 実行分だけ残す。

    Returns:
        削除した件数
    """
    if not LOG_DIR.exists():
        return 0
    # run_*.log と summary_*.json を紐付けて管理
    logs = sorted(LOG_DIR.glob("run_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    excess = logs[max_runs:]
    removed = 0
    for log in excess:
        try:
            log.unlink()
            removed += 1
            # 同時刻のサマリも削除
            ts = log.stem.replace("run_", "")
            summary = LOG_DIR / f"summary_{ts}.json"
            if summary.exists():
                summary.unlink()
        except OSError:
            continue
    return removed


def list_past_runs(limit: int = 10) -> list[dict]:
    """過去の実行サマリ一覧を返す（新しい順）"""
    if not LOG_DIR.exists():
        return []
    summaries = sorted(LOG_DIR.glob("summary_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    result = []
    for s in summaries:
        try:
            data = json.loads(s.read_text(encoding="utf-8"))
            ts = s.stem.replace("summary_", "")
            result.append({"timestamp": ts, "path": str(s), **data})
        except Exception:
            continue
    return result
