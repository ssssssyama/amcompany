"""統合ランチャー — サーバー・Streamlit・自動抽出・Chrome拡張巡回を1コマンドで起動

データフロー（一本化）:
    [1] run.py が price_server 起動
    [2] auto_extract が API/スクレイパー経由で価格取得 & キャッシュ書込
    [3] auto_extract が残りJANを Chrome拡張の巡回キューへ投入
    [4] --open-chrome 指定時、ブラウザを起動して拡張の自動巡回を誘発
    [5] --wait-extension 指定時（デフォルトON）、Chrome拡張の完了まで待機
    [6] 全結果を Streamlit ビューアで閲覧

使い方:
    python run.py                             # 全モード（サーバー+UI+抽出+拡張待機）
    python run.py --open-chrome               # + 自動的にChromeを開いて巡回を誘発
    python run.py --no-wait-extension         # 拡張完了を待たず即終了
    python run.py --no-ui                     # Streamlitなし（CLIのみ）
    python run.py --extract --top 100 --threshold 5000
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent


def run_price_server(port: int, shops: list[str], threshold: int, shipping: int):
    """price_server.py をサブプロセスで起動"""
    cmd = [sys.executable, str(TOOL_DIR / "price_server.py")]
    cmd += ["--port", str(port)]
    cmd += ["--threshold", str(threshold)]
    cmd += ["--shipping", str(shipping)]
    cmd += ["--shops", *shops]
    return subprocess.Popen(cmd, cwd=str(TOOL_DIR))


def run_streamlit(port: int):
    """Streamlit をサブプロセスで起動"""
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(TOOL_DIR / "app.py"),
         "--server.port", str(port), "--server.headless", "true"],
        cwd=str(TOOL_DIR),
    )


def run_auto_extract(args: argparse.Namespace):
    """auto_extract.py をサブプロセスで実行"""
    cmd = [sys.executable, str(TOOL_DIR / "auto_extract.py")]
    cmd += ["--threshold", str(args.threshold)]
    cmd += ["--shipping", str(args.shipping)]
    cmd += ["--top", str(args.top)]
    cmd += ["--shops", *args.shops]
    cmd += ["--rakuten-bonus", str(args.rakuten_bonus)]
    cmd += ["--yahoo-bonus", str(args.yahoo_bonus)]
    if args.min_kaitori:
        cmd += ["--min-kaitori", str(args.min_kaitori)]
    if args.no_scraper:
        cmd += ["--no-scraper"]
    if args.open_browser > 0:
        cmd += ["--open-browser", str(args.open_browser)]
    if args.clear_cache:
        cmd += ["--clear-cache"]
    if args.categories is not None:
        cmd += ["--categories", *args.categories]
    if args.wait_extension:
        cmd += ["--wait-extension"]
        cmd += ["--extension-timeout", str(args.extension_timeout)]
    return subprocess.Popen(cmd, cwd=str(TOOL_DIR))


def main():
    parser = argparse.ArgumentParser(
        description="買取価格ツール統合ランチャー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python run.py                             フル稼働（サーバー+Streamlit+抽出+Chrome拡張待機）
  python run.py --open-chrome               + Chromeを自動起動して拡張巡回を誘発
  python run.py --no-wait-extension         拡張完了を待たず即終了
  python run.py --extract --open-browser 5  + ブラウザで上位5件を開く
  python run.py --no-ui                     Streamlitなし
        """,
    )
    # モード
    parser.add_argument("--extract", action="store_true", default=True, help="自動利益抽出を実行（デフォルトON）")
    parser.add_argument("--no-extract", action="store_true", help="自動利益抽出を無効化")
    parser.add_argument("--no-ui", action="store_true", help="Streamlit UIを起動しない")

    # サーバー設定
    parser.add_argument("--server-port", type=int, default=8502, help="価格サーバーのポート")
    parser.add_argument("--ui-port", type=int, default=8501, help="Streamlitのポート")

    # 抽出設定（auto_extract.py に渡す）
    parser.add_argument("--threshold", type=int, default=3000, help="最低利益閾値(円)")
    parser.add_argument("--shipping", type=int, default=1000, help="送料合計(円)")
    parser.add_argument("--top", type=int, default=1000, help="検索件数")
    parser.add_argument("--shops", nargs="*", default=None, help="利用する買取店（省略時は全店）")
    parser.add_argument("--rakuten-bonus", type=float, default=10.0, help="楽天ボーナスPT(%%)")
    parser.add_argument("--yahoo-bonus", type=float, default=7.0, help="Yahoo!ボーナスPT(%%)")
    parser.add_argument("--min-kaitori", type=int, default=5000, help="買取価格の下限(円)")
    parser.add_argument("--no-scraper", action="store_true", help="スクレイパー無効化")
    parser.add_argument("--open-browser", type=int, default=0, metavar="N",
                        help="利益上位N件の量販店検索URLをブラウザで開く")
    parser.add_argument("--clear-cache", action="store_true", help="キャッシュをクリア")
    parser.add_argument("--categories", nargs="*", default=None,
                        help="検索対象カテゴリ（auto_extract.pyに渡す）。--categories all で全カテゴリ")

    # ログ閲覧モード
    parser.add_argument("--list-logs", action="store_true",
                        help="過去の実行サマリ一覧を表示して終了")
    parser.add_argument("--inspect-posts", action="store_true",
                        help="Chrome拡張/APIからのPOST履歴を集計表示して終了（反映されたか検証）")
    parser.add_argument("--inspect-posts-filter", default=None,
                        help="--inspect-posts でフィルタ（例: chrome_extension, skipped_ratio, ソース名）")

    # 価格乖離検証モード
    parser.add_argument("--verify-prices", action="store_true",
                        help="キャッシュ内の価格を実ページで再検証（他の処理はスキップ）")
    parser.add_argument("--verify-auto-remove", action="store_true",
                        help="--verify-prices で異常エントリを自動削除")
    parser.add_argument("--verify-threshold", type=float, default=0.30,
                        help="価格乖離の許容率（デフォルト 0.30 = ±30%%）")
    parser.add_argument("--verify-max", type=int, default=None,
                        help="検証する最大件数")

    # お気に入り自動追加モード
    parser.add_argument("--add-favorites", action="store_true",
                        help="楽天/Yahooの利益商品を自動でお気に入りに追加")
    parser.add_argument("--favorites-min-profit", type=int, default=3000,
                        help="お気に入り追加対象の最小現金利益（デフォルト3000円）")
    parser.add_argument("--favorites-source", choices=["楽天", "Yahoo"], default=None,
                        help="お気に入り追加を特定ソースのみに限定")
    parser.add_argument("--favorites-max", type=int, default=None,
                        help="お気に入り追加する最大件数")
    parser.add_argument("--favorites-dry-run", action="store_true",
                        help="お気に入り追加対象のみ表示（実行しない）")
    parser.add_argument("--favorites-headed", action="store_true",
                        help="初回ログイン用にヘッドフル起動")

    # Chrome拡張連携
    parser.add_argument("--wait-extension", action="store_true", default=True,
                        help="Chrome拡張の巡回完了まで待機（デフォルトON）")
    parser.add_argument("--no-wait-extension", action="store_true",
                        help="Chrome拡張の完了を待たず抽出完了時点で終了")
    parser.add_argument("--extension-timeout", type=int, default=300,
                        help="Chrome拡張の待機秒数（デフォルト300秒）")
    parser.add_argument("--open-chrome", action="store_true",
                        help="price_server起動後にChromeを自動で開く（拡張巡回を誘発）")
    parser.add_argument("--chrome-landing", default="https://www.biccamera.com/",
                        help="--open-chrome 時に開く最初のURL（拡張をactivateさせるため対応サイトが推奨）")

    args = parser.parse_args()

    # --list-logs: 過去実行のサマリ一覧を表示して終了
    if args.list_logs:
        _print_past_runs()
        sys.exit(0)

    # --inspect-posts: POST履歴を集計して表示
    if args.inspect_posts:
        _inspect_post_history(args.inspect_posts_filter)
        sys.exit(0)

    # --verify-prices: キャッシュを実ページで再検証
    if args.verify_prices:
        from price_discrepancy_verifier import verify_cache, _print_summary
        report = verify_cache(
            threshold=args.verify_threshold,
            max_entries=args.verify_max,
            auto_remove=args.verify_auto_remove,
        )
        _print_summary(report)
        sys.exit(0 if report["problem_count"] == 0 else 1)

    # --add-favorites: 楽天/Yahooの利益商品をお気に入りに追加
    if args.add_favorites:
        from favorite_adder import add_favorites
        result = add_favorites(
            min_profit=args.favorites_min_profit,
            source_filter=args.favorites_source,
            max_items=args.favorites_max,
            dry_run=args.favorites_dry_run,
            headless=not args.favorites_headed,
        )
        print(f"お気に入り追加結果: {result}")
        sys.exit(0 if result["added"] > 0 or args.favorites_dry_run else 1)

    # --no-wait-extension で待機を無効化
    if args.no_wait_extension:
        args.wait_extension = False

    # --no-extract で抽出を無効化
    if args.no_extract:
        args.extract = False

    # 全店デフォルト
    if args.shops is None:
        sys.path.insert(0, str(TOOL_DIR))
        from csv_loader import SHOP_NAMES
        args.shops = list(SHOP_NAMES)

    processes = []

    # シグナルハンドラ: Ctrl+C で全プロセスを停止（サブプロセス起動前に登録）
    def shutdown(sig=None, frame=None):
        print("\n[run] 停止中...")
        for proc in processes:
            if proc and proc.poll() is None:
                proc.terminate()
        for proc in processes:
            if proc:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, shutdown)

    # 0. 実行ログファイルを作成（子プロセスが env var 経由で同じファイルに追記）
    try:
        from log_utils import create_run_log_file, rotate_logs
        log_file = create_run_log_file()
        print(f"[run] 実行ログ: {log_file}")
        removed = rotate_logs(max_runs=30)
        if removed:
            print(f"[run] 古いログを {removed} 件削除")
    except Exception as _e:
        log_file = None
        print(f"[run] ログファイル作成失敗（続行）: {_e}")

    # キャッシュ状態スナップショット（Chrome拡張の成果計測用ベースライン）
    cache_baseline = _snapshot_cache()
    if cache_baseline:
        print(f"[run] 実行前キャッシュ: {len(cache_baseline)}件")

    # 1. 価格収集サーバー（サブプロセス）
    print(f"[run] 価格サーバー起動中... (port {args.server_port})")
    server_proc = run_price_server(args.server_port, args.shops, args.threshold, args.shipping)
    processes.append(server_proc)
    # サーバーが port を LISTEN するまで待機（CSV読み込み完了を確認）
    _wait_server_ready(args.server_port, timeout=30)

    # 2. Streamlit UI（サブプロセス）
    streamlit_proc = None
    if not args.no_ui:
        print(f"[run] Streamlit 起動中... (port {args.ui_port})")
        streamlit_proc = run_streamlit(args.ui_port)
        processes.append(streamlit_proc)
        print(f"[run] Streamlit: http://localhost:{args.ui_port}")

    # 3. Chrome自動起動（拡張のbackground.jsをactiveにするため）
    if args.open_chrome:
        print(f"[run] Chromeを起動して拡張をactive化... ({args.chrome_landing})")
        try:
            webbrowser.open(args.chrome_landing)
        except Exception as e:
            print(f"[run] Chrome起動失敗（手動で開いてください）: {e}")

    # 4. 自動抽出（サブプロセス、Chrome拡張のキュー投入も内部で実行）
    extract_proc = None
    if args.extract:
        print("[run] 自動利益抽出を開始... (Chrome拡張の巡回キュー投入も含む)")
        extract_proc = run_auto_extract(args)
        processes.append(extract_proc)

    print("[run] 起動完了 — Ctrl+C で全停止")

    # 抽出完了を待つ → price_serverはChrome拡張巡回のために維持
    try:
        if extract_proc:
            extract_proc.wait()
            print("[run] 自動抽出完了")
            # 抽出が --wait-extension で完了を待っていない場合のフォールバック
            if not args.wait_extension:
                print("[run] Chrome拡張の巡回が完了するまでprice_serverを維持します（Ctrl+Cで停止）")
            else:
                # 完了時サマリ（baseline との差分で Chrome拡張の成果を計測）
                _print_summary(args, baseline=cache_baseline)

        # price_serverは常に維持（ユーザーが閲覧中のChrome拡張巡回を処理）
        if not args.no_ui:
            print(f"[run] Streamlitで結果を確認: http://localhost:{args.ui_port}")
        server_proc.wait()
    except KeyboardInterrupt:
        shutdown()


def _wait_server_ready(port: int, timeout: int = 30) -> bool:
    """price_server がリクエストを受け付けられる状態になるまで待機"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as r:
                r.read()
                print("[run] 価格サーバー準備完了")
                return True
        except Exception:
            time.sleep(1)
    print(f"[run] 価格サーバー応答なし（{timeout}秒）— 起動を継続")
    return False


def _print_summary(args: argparse.Namespace, baseline: dict | None = None) -> None:
    """Chrome拡張完了後のキャッシュ結果サマリを表示

    Args:
        baseline: run.py 開始時のキャッシュ状態（JAN→EC最安値 dict）。
                  None の場合、Chrome拡張で「更新された」件数は計測できない。
    """
    import json
    from collections import Counter
    cache_file = Path.home() / ".kaitori-viewer" / "cache_results.json"
    if not cache_file.exists():
        print("[run] キャッシュファイルなし")
        return
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        print("[run] キャッシュ読み込み失敗")
        return
    if not data:
        print("[run] キャッシュは空")
        return

    profitable = [r for r in data if r.get("現金利益", 0) > 0]
    sources = Counter(r.get("ECソース", "?") for r in data)

    # 経路別（origin マーカー）
    origins = Counter(r.get("origin", "unknown") for r in data)
    chrome_entries = [r for r in data if r.get("origin") == "chrome_extension"]
    api_entries = [r for r in data if r.get("origin") == "api"]
    scraper_entries = [r for r in data if r.get("origin") == "scraper"]
    unknown_entries = [r for r in data if not r.get("origin")]

    # Chrome拡張の更新数（baselineから価格が安くなったものをカウント）
    chrome_updated = []
    chrome_new = []
    if baseline is not None:
        for r in chrome_entries:
            jan = r.get("JAN")
            prev_price = baseline.get(jan)
            if prev_price is None:
                chrome_new.append(r)
            elif r.get("EC最安値", 0) < prev_price:
                chrome_updated.append((r, prev_price))

    print("=" * 60)
    print(f"[run] サマリ: キャッシュ {len(data)}件 (利益商品 {len(profitable)}件)")
    print()
    print("  収集経路別:")
    print(f"    - API (楽天/Yahoo):         {len(api_entries)}件")
    print(f"    - スクレイパー (直接):      {len(scraper_entries)}件")
    print(f"    - Chrome拡張:               {len(chrome_entries)}件"
          + (" ← 取得できています ✅" if chrome_entries else " ← 取得できていません ⚠"))
    if unknown_entries:
        print(f"    - 旧データ(未分類):         {len(unknown_entries)}件")

    # Chrome拡張の効果
    if baseline is not None:
        if chrome_new:
            print(f"\n  Chrome拡張の新規取得: {len(chrome_new)}件（APIで取れなかったJANを補完）")
            for r in chrome_new[:3]:
                print(f"    + JAN={r['JAN']} EC={r.get('EC最安値'):,}円 "
                      f"[{r.get('ECソース','?')}] {r.get('商品名','')[:30]}")
        if chrome_updated:
            total_saved = sum(prev - r.get("EC最安値", 0) for r, prev in chrome_updated)
            print(f"\n  Chrome拡張で最安値更新: {len(chrome_updated)}件 "
                  f"(累計 -{total_saved:,}円)")
            for r, prev in sorted(chrome_updated, key=lambda x: x[1] - x[0].get("EC最安値", 0), reverse=True)[:5]:
                saved = prev - r.get("EC最安値", 0)
                print(f"    ↓ JAN={r['JAN']} {prev:,}円→{r.get('EC最安値'):,}円 "
                      f"(-{saved:,}) [{r.get('ECソース','?')}]")
        if not chrome_new and not chrome_updated and chrome_entries:
            print("\n  Chrome拡張: 新規取得・最安値更新ともに0件（既存データと同等）")

    print()
    print("  ECソース別（詳細）:")
    for src, cnt in sources.most_common():
        print(f"    - {src}: {cnt}件")

    top_profit = []
    if profitable:
        top_profit = sorted(profitable, key=lambda r: r.get("PT込利益", 0), reverse=True)[:5]
        print()
        print("  利益 TOP 5:")
        for r in top_profit:
            print(f"    {r.get('現金利益', 0):+8,}円 {r.get('商品名','')[:40]} "
                  f"[{r.get('ECソース','?')}/{r.get('origin','?')}]")
    print("=" * 60)

    # サマリ JSON を保存（後から集計・検証できる）
    try:
        from log_utils import save_summary
        summary_data = {
            "timestamp": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "total_entries": len(data),
            "profitable_count": len(profitable),
            "by_origin": dict(origins),
            "by_source": dict(sources),
            "chrome_extension": {
                "total": len(chrome_entries),
                "new_fetched": len(chrome_new),
                "price_updated": len(chrome_updated),
                "total_savings": sum(prev - r.get("EC最安値", 0) for r, prev in chrome_updated) if chrome_updated else 0,
            },
            "top_profit": [
                {
                    "JAN": r.get("JAN"),
                    "商品名": r.get("商品名", "")[:60],
                    "現金利益": r.get("現金利益", 0),
                    "PT込利益": r.get("PT込利益", 0),
                    "買取価格": r.get("最高買取価格", 0),
                    "EC最安値": r.get("EC最安値", 0),
                    "ECソース": r.get("ECソース"),
                    "origin": r.get("origin"),
                }
                for r in top_profit
            ],
        }
        saved = save_summary(summary_data)
        if saved:
            print(f"[run] サマリ保存: {saved}")
    except Exception as _e:
        print(f"[run] サマリ保存失敗: {_e}")


def _snapshot_cache() -> dict:
    """現在のキャッシュ状態のスナップショットを返す（JAN→EC最安値）"""
    import json
    cache_file = Path.home() / ".kaitori-viewer" / "cache_results.json"
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {r["JAN"]: r.get("EC最安値", 0) for r in data if r.get("JAN")}


def _inspect_post_history(filter_keyword: str | None = None) -> None:
    """POST履歴ファイル (~/.kaitori-viewer/logs/post_history.jsonl) を集計表示

    「Chrome拡張が送信したけどキャッシュに入らなかった」ケースを明確に識別する。
    """
    import json as _json
    from collections import Counter
    history = Path.home() / ".kaitori-viewer" / "logs" / "post_history.jsonl"
    if not history.exists():
        print(f"POST履歴ファイルなし: {history}")
        print("（price_server を起動して拡張/APIからPOSTが入ると自動生成されます）")
        return
    try:
        lines = history.read_text(encoding="utf-8").strip().split("\n")
    except OSError as e:
        print(f"読み込み失敗: {e}")
        return

    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        if filter_keyword:
            hay = f"{rec.get('action','')} {rec.get('source','')} {rec.get('reason','')}"
            if filter_keyword.lower() not in hay.lower():
                continue
        records.append(rec)

    print(f"POST履歴: {len(records)}件" + (f" (filter={filter_keyword})" if filter_keyword else ""))
    if not records:
        print("（条件に該当するPOSTがありません）")
        return

    # action別集計
    by_action = Counter(r.get("action", "?") for r in records)
    by_source = Counter(r.get("source", "?") for r in records)
    print()
    print("=== action 別 ===")
    for a, c in by_action.most_common():
        label = {
            "added": "✅ 新規キャッシュ追加",
            "updated": "✅ 価格更新（より安くなった）",
            "skipped_existing_cheaper": "⏭ 既存価格のほうが安いためスキップ",
            "skipped_ratio": "❌ 価格比率却下（EC価格が買取に対し低すぎ）",
            "skipped_excluded": "❌ 除外対象商品",
            "jan_not_in_csv": "❌ JANがCSV未登録",
            "invalid_jan": "❌ JAN形式不正",
            "error": "❌ エラー",
        }.get(a, a)
        print(f"  {label}: {c}件")

    print()
    print("=== ソース別 ===")
    for s, c in by_source.most_common(15):
        print(f"  {s}: {c}件")

    # Chrome拡張特化分析
    chrome_records = [r for r in records if any(
        d in (r.get("origin_header", "") or r.get("url", ""))
        for d in ("biccamera", "kojima.net", "sofmap", "ksdenki", "joshinweb",
                 "nojima", "edion", "yodobashi", "amazon.co.jp",
                 "wowma", "omni7", "fujiya-camera", "books.rakuten")
    )]
    if chrome_records:
        chrome_actions = Counter(r.get("action", "?") for r in chrome_records)
        added_or_updated = chrome_actions.get("added", 0) + chrome_actions.get("updated", 0)
        total = len(chrome_records)
        print()
        print(f"=== Chrome拡張 POST 分析 ({total}件) ===")
        for a, c in chrome_actions.most_common():
            print(f"  {a}: {c}件 ({100*c/total:.1f}%)")
        print(f"  → 反映率: {added_or_updated}/{total} ({100*added_or_updated/total:.1f}%)")
        if chrome_actions.get("skipped_existing_cheaper", 0) > added_or_updated:
            print("  💡 多くが「既存が安い」でスキップ → APIの価格がChrome拡張より安いため正常動作")
        if chrome_actions.get("skipped_ratio", 0):
            print("  ⚠ 価格比率却下あり → 楽天ショップのJAN流用などを正しく除外")
        if chrome_actions.get("jan_not_in_csv", 0):
            print("  ⚠ CSV未登録JANあり → CSV最新化で検討")

    # 最新10件
    print()
    print("=== 最新 10 件 ===")
    for rec in records[-10:]:
        ts = rec.get("ts", "?")[-8:]
        action = rec.get("action", "?")
        src = rec.get("source", "?")
        jan = rec.get("jan", "?")
        price = rec.get("price", 0)
        reason = rec.get("reason", "")[:50]
        print(f"  [{ts}] {action:30} {jan} {price:>9,}円 [{src}] {reason}")


def _print_past_runs(limit: int = 20) -> None:
    """過去の実行サマリ一覧を出力する"""
    try:
        from log_utils import list_past_runs, LOG_DIR
    except Exception as e:
        print(f"log_utils インポート失敗: {e}")
        return
    runs = list_past_runs(limit=limit)
    if not runs:
        print(f"過去の実行サマリはありません ({LOG_DIR})")
        return
    print(f"過去の実行サマリ (最新{len(runs)}件 / {LOG_DIR})")
    print("-" * 80)
    for r in runs:
        ts = r.get("timestamp", "?")
        total = r.get("total_entries", 0)
        prof = r.get("profitable_count", 0)
        chrome = r.get("chrome_extension", {})
        chrome_total = chrome.get("total", 0)
        chrome_new = chrome.get("new_fetched", 0)
        chrome_upd = chrome.get("price_updated", 0)
        savings = chrome.get("total_savings", 0)
        print(f"[{ts}] 総{total}件 利益{prof}件 "
              f"| Chrome拡張 {chrome_total}件 (新規{chrome_new}/更新{chrome_upd} "
              f"-{savings:,}円)")
        top = r.get("top_profit", [])
        for t in top[:3]:
            print(f"    {t.get('現金利益', 0):+8,}円 {t.get('商品名','')[:40]} "
                  f"[{t.get('ECソース','?')}/{t.get('origin','?')}]")
    print("-" * 80)


if __name__ == "__main__":
    main()
