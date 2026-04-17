"""統合ランチャー — サーバー・Streamlit・自動抽出を1コマンドで起動

使い方:
    python run.py                             # サーバー + Streamlit
    python run.py --extract                   # + 自動利益抽出
    python run.py --extract --open-browser 5  # + ブラウザで上位5件を開く
    python run.py --no-ui                     # Streamlitなし（CLIのみ）
    python run.py --extract --top 100 --threshold 5000
"""

import argparse
import signal
import subprocess
import sys
import time
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
    return subprocess.Popen(cmd, cwd=str(TOOL_DIR))


def main():
    parser = argparse.ArgumentParser(
        description="買取価格ツール統合ランチャー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python run.py                             サーバー + Streamlit
  python run.py --extract                   + 自動利益抽出
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

    args = parser.parse_args()

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

    # 1. 価格収集サーバー（サブプロセス）
    print(f"[run] 価格サーバー起動中... (port {args.server_port})")
    server_proc = run_price_server(args.server_port, args.shops, args.threshold, args.shipping)
    processes.append(server_proc)
    time.sleep(1)  # サーバー起動待ち

    # 2. Streamlit UI（サブプロセス）
    streamlit_proc = None
    if not args.no_ui:
        print(f"[run] Streamlit 起動中... (port {args.ui_port})")
        streamlit_proc = run_streamlit(args.ui_port)
        processes.append(streamlit_proc)
        print(f"[run] Streamlit: http://localhost:{args.ui_port}")

    # 3. 自動抽出（サブプロセス）
    extract_proc = None
    if args.extract:
        print("[run] 自動利益抽出を開始...")
        extract_proc = run_auto_extract(args)
        processes.append(extract_proc)

    print("[run] 起動完了 — Ctrl+C で全停止")

    # 抽出完了を待つ → price_serverはChrome拡張巡回のために維持
    try:
        if extract_proc:
            extract_proc.wait()
            print("[run] 自動抽出完了")
            print("[run] Chrome拡張の巡回が完了するまでprice_serverを維持します（Ctrl+Cで停止）")

        # price_serverは常に維持（Chrome拡張の巡回キュー処理のため）
        server_proc.wait()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
