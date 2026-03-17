"""JRA競馬予想ツール — 過去データから馬券予想を生成"""

import sys
import os
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from common.error_handler import friendly_error_handler
from data_manager import (
    load_races, load_upcoming, load_races_from_db, load_upcoming_from_scraper,
    get_race_info, get_data_summary,
)
from feature_engine import compute_all_features
from predictor import StatisticalPredictor, MLPredictor, train_ml_model
from formatter import format_full_prediction, format_backtest_results

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data", "keiba.db")
DEFAULT_SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_data")


def _load_races_auto(args):
    """--db または --data-dir に応じてレースデータを読み込む"""
    db_path = getattr(args, "db", None)
    data_dir = getattr(args, "data_dir", None)

    if db_path and os.path.exists(db_path):
        print(f"データベースから読み込んでいます: {db_path}")
        return load_races_from_db(db_path)
    elif data_dir:
        csv_path = os.path.join(data_dir, "races.csv")
        if os.path.exists(csv_path):
            print(f"CSVから読み込んでいます: {csv_path}")
            return load_races(data_dir)
    # DBがデフォルトパスに存在すればそちらを使う
    if os.path.exists(DEFAULT_DB):
        print(f"データベースから読み込んでいます: {DEFAULT_DB}")
        return load_races_from_db(DEFAULT_DB)
    # フォールバック: サンプルデータ
    print(f"サンプルデータから読み込んでいます: {DEFAULT_SAMPLE_DIR}")
    return load_races(DEFAULT_SAMPLE_DIR)


def cmd_predict(args):
    """レース予想を実行"""
    print("データを読み込んでいます...")
    races = _load_races_auto(args)

    # 出馬表の取得
    if args.race_id:
        print(f"出馬表を取得しています: {args.race_id}")
        upcoming = load_upcoming_from_scraper(args.race_id)
    else:
        upcoming = load_upcoming(args.race)
    race_info = get_race_info(upcoming)

    print("特徴量を計算しています...")
    features = compute_all_features(races, upcoming, race_info)

    print("予想を計算しています...")
    if args.method == "ml":
        predictor = MLPredictor()
        model_path = os.path.join(os.path.dirname(__file__), "models", "model.pkl")
        predictor.load(model_path)
        ranked = predictor.predict(features)
        method = "ml"
    else:
        predictor = StatisticalPredictor()
        ranked = predictor.predict(features)
        method = "stat"

    # 資金配分の計算
    allocation = None
    if args.budget > 0:
        from bet_optimizer import optimize_allocation
        allocation = optimize_allocation(
            ranked, upcoming, budget=args.budget, kelly_fraction=args.kelly
        )

    output = format_full_prediction(ranked, race_info, top_n=args.top, method=method, allocation=allocation)
    print(output)


def cmd_train(args):
    """MLモデルを学習"""
    print("学習データを読み込んでいます...")
    races = _load_races_auto(args)

    print("モデルを学習しています...")
    predictor = train_ml_model(races, getattr(args, "data_dir", DEFAULT_SAMPLE_DIR))

    output_path = args.output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    predictor.save(output_path)
    print(f"\nモデルを保存しました: {output_path}")
    print("predict コマンドで --method ml を指定すると使用できます。")


def cmd_info(args):
    """データ概要を表示"""
    races = _load_races_auto(args)
    summary = get_data_summary(races)

    source = "データベース" if os.path.exists(getattr(args, "db", "") or DEFAULT_DB) else "CSV"
    print("")
    print("=" * 50)
    print("  JRA競馬予想ツール — データ概要")
    print("=" * 50)
    print(f"  データソース: {source}")
    print(f"  レコード数: {summary['total_rows']}件")
    if summary['total_rows'] == 0:
        print("  （データがありません）")
    else:
        print(f"  レース数: {summary['total_races']}レース")
        print(f"  馬数: {summary['total_horses']}頭")
        print(f"  騎手数: {summary['total_jockeys']}名")
        print(f"  期間: {summary['date_range']}")
        print(f"  競馬場: {', '.join(summary['venues'])}")
        print(f"  グレード: {', '.join(summary['grades'])}")
    print("=" * 50)
    print("")


def cmd_fetch(args):
    """netkeiba.comからレースデータを取得してDBに保存"""
    from scraper import fetch_race_result, fetch_race_list
    from database import Database

    db = Database(args.db)
    total_saved = 0

    if args.race_id:
        # 単一レース取得
        print(f"レース結果を取得しています: {args.race_id}")
        rows = fetch_race_result(args.race_id)
        if rows:
            count = db.insert_race_results(rows)
            print(f"  {count}件のデータを保存しました")
            total_saved += count
        else:
            print("  データを取得できませんでした")

    elif args.date:
        # 指定日の全レース取得
        print(f"レース一覧を取得しています: {args.date}")
        race_list = fetch_race_list(args.date)
        if not race_list:
            print("  レースが見つかりませんでした")
        else:
            print(f"  {len(race_list)}レースが見つかりました")
            for race in race_list:
                rid = race["race_id"]
                if db.has_race(rid) and not args.force:
                    print(f"  [{race['venue']}{race['race_number']}R] スキップ（取得済み）")
                    continue
                print(f"  [{race['venue']}{race['race_number']}R] {race.get('race_name', '')} 取得中...")
                rows = fetch_race_result(rid)
                if rows:
                    count = db.insert_race_results(rows)
                    total_saved += count
                    print(f"    → {count}件保存")

    elif args.date_range:
        # 日付範囲で取得
        start_str, end_str = args.date_range
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            print(f"\n--- {date_str} ---")
            race_list = fetch_race_list(date_str)
            if race_list:
                print(f"  {len(race_list)}レースが見つかりました")
                for race in race_list:
                    rid = race["race_id"]
                    if db.has_race(rid) and not args.force:
                        print(f"  [{race['venue']}{race['race_number']}R] スキップ（取得済み）")
                        continue
                    print(f"  [{race['venue']}{race['race_number']}R] 取得中...")
                    rows = fetch_race_result(rid)
                    if rows:
                        count = db.insert_race_results(rows)
                        total_saved += count
            current += timedelta(days=1)

    db.close()
    print(f"\n合計 {total_saved}件のデータを保存しました → {args.db}")


def cmd_list(args):
    """指定日のレース一覧を表示"""
    from scraper import fetch_race_list

    date_str = args.date
    print(f"\n{date_str} のレース一覧を取得しています...")
    race_list = fetch_race_list(date_str)

    if not race_list:
        print("レースが見つかりませんでした")
        return

    print("")
    print("=" * 55)
    print(f"  {date_str} のレース一覧（{len(race_list)}レース）")
    print("=" * 55)

    current_venue = ""
    for race in race_list:
        if race["venue"] != current_venue:
            current_venue = race["venue"]
            print(f"\n  【{current_venue}】")
        name = race.get("race_name", "")
        print(f"    {race['race_number']:>2}R  {name:<20}  ID: {race['race_id']}")

    print("")
    print("  予想するには:")
    print("    python main.py predict --race-id <レースID>")
    print("=" * 55)
    print("")


def cmd_import_csv(args):
    """CSVファイルをDBにインポート"""
    from database import Database

    db = Database(args.db)
    print(f"CSVをインポートしています: {args.file}")
    count = db.import_csv(args.file)
    db.close()
    print(f"{count}件のデータをインポートしました → {args.db}")


def cmd_backtest(args):
    """バックテストを実行"""
    from backtester import run_backtest

    print("データを読み込んでいます...")
    races = _load_races_auto(args)

    if not races:
        print("データがありません。先に fetch または import-csv でデータを準備してください。")
        return

    method = args.method
    model_path = None
    if method == "ml":
        model_path = os.path.join(os.path.dirname(__file__), "models", "model.pkl")

    print(f"バックテストを実行しています（手法: {'統計モデル' if method == 'stat' else '機械学習モデル'}）...")
    result = run_backtest(
        races,
        method=method,
        model_path=model_path,
        min_history_races=args.min_history,
    )

    output = format_backtest_results(result)
    print(output)


def cmd_sample(args):
    """使い方ガイドを表示"""
    print("")
    print("=" * 60)
    print("  JRA競馬予想ツール — 使い方ガイド")
    print("=" * 60)
    print("")
    print("■ データ自動取得（推奨）:")
    print("  1. 過去データを蓄積:")
    print("     python main.py fetch --date 2025-03-16")
    print("     python main.py fetch --date-range 2025-01-01 2025-03-16")
    print("")
    print("  2. レース一覧を確認:")
    print("     python main.py list --date 2025-03-17")
    print("")
    print("  3. レースIDを指定して予想:")
    print("     python main.py predict --race-id 202503170511")
    print("")
    print("■ サンプルデータで予想を試す:")
    sample_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    print(f"  python main.py predict --race {os.path.join(sample_dir, 'upcoming.csv')}")
    print(f"    --data-dir {sample_dir}")
    print("")
    print("■ 既存CSVをDBにインポート:")
    print("  python main.py import-csv --file races.csv")
    print("")
    print("■ MLモデルを学習して使う:")
    print("  python main.py train")
    print("  python main.py predict --race-id <ID> --method ml")
    print("")
    print("=" * 60)
    print("")


@friendly_error_handler("JRA競馬予想ツール")
def main():
    parser = argparse.ArgumentParser(
        description="JRA競馬予想ツール — 過去データから馬券予想を生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用例:\n"
            "  python main.py fetch --date 2025-03-16        # 過去データ取得\n"
            "  python main.py list --date 2025-03-17         # レース一覧\n"
            "  python main.py predict --race-id 202503170511 # レースID指定で予想\n"
            "  python main.py predict --race upcoming.csv    # CSV指定で予想\n"
            "  python main.py backtest                       # バックテスト\n"
            "  python main.py train                          # MLモデル学習\n"
            "  python main.py info                           # データ概要\n"
            "  python main.py sample                         # 使い方ガイド"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    # === predict コマンド ===
    p_predict = subparsers.add_parser("predict", help="レース予想を実行")
    p_predict_group = p_predict.add_mutually_exclusive_group(required=True)
    p_predict_group.add_argument("--race", help="予測対象レースCSVファイル")
    p_predict_group.add_argument("--race-id", help="予測対象レースID（出馬表を自動取得）")
    p_predict.add_argument("--db", default=DEFAULT_DB, help="データベースファイル (default: data/keiba.db)")
    p_predict.add_argument("--data-dir", help="過去レースデータCSVのディレクトリ")
    p_predict.add_argument("--method", choices=["stat", "ml"], default="stat", help="予測手法 (default: stat)")
    p_predict.add_argument("--top", type=int, default=5, help="上位何頭を表示するか (default: 5)")
    p_predict.add_argument("--budget", type=int, default=10000, help="資金配分の予算（円、default: 10000、0で無効）")
    p_predict.add_argument("--kelly", type=float, default=0.5, help="Kelly倍率（default: 0.5 = Half Kelly）")

    # === fetch コマンド ===
    p_fetch = subparsers.add_parser("fetch", help="netkeiba.comからレースデータを取得")
    p_fetch_group = p_fetch.add_mutually_exclusive_group(required=True)
    p_fetch_group.add_argument("--race-id", help="取得するレースID")
    p_fetch_group.add_argument("--date", help="取得する日付 (YYYY-MM-DD)")
    p_fetch_group.add_argument("--date-range", nargs=2, metavar=("START", "END"), help="日付範囲 (YYYY-MM-DD YYYY-MM-DD)")
    p_fetch.add_argument("--db", default=DEFAULT_DB, help="保存先DB (default: data/keiba.db)")
    p_fetch.add_argument("--force", action="store_true", help="取得済みデータも再取得")

    # === list コマンド ===
    p_list = subparsers.add_parser("list", help="指定日のレース一覧を表示")
    p_list.add_argument("--date", required=True, help="日付 (YYYY-MM-DD)")

    # === import-csv コマンド ===
    p_import = subparsers.add_parser("import-csv", help="CSVファイルをDBにインポート")
    p_import.add_argument("--file", required=True, help="インポートするCSVファイル")
    p_import.add_argument("--db", default=DEFAULT_DB, help="保存先DB (default: data/keiba.db)")

    # === backtest コマンド ===
    p_backtest = subparsers.add_parser("backtest", help="過去データでバックテスト（精度検証）")
    p_backtest.add_argument("--db", default=DEFAULT_DB, help="データベースファイル (default: data/keiba.db)")
    p_backtest.add_argument("--data-dir", help="データCSVのディレクトリ")
    p_backtest.add_argument("--method", choices=["stat", "ml"], default="stat", help="予測手法 (default: stat)")
    p_backtest.add_argument("--min-history", type=int, default=3, help="最低限必要な履歴レース数 (default: 3)")

    # === train コマンド ===
    p_train = subparsers.add_parser("train", help="MLモデルを学習")
    p_train.add_argument("--db", default=DEFAULT_DB, help="学習データDB (default: data/keiba.db)")
    p_train.add_argument("--data-dir", help="学習データCSVのディレクトリ")
    p_train.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "models", "model.pkl"),
        help="モデル保存先 (default: models/model.pkl)",
    )

    # === info コマンド ===
    p_info = subparsers.add_parser("info", help="データ概要を表示")
    p_info.add_argument("--db", default=DEFAULT_DB, help="データベースファイル (default: data/keiba.db)")
    p_info.add_argument("--data-dir", help="データCSVのディレクトリ")

    # === sample コマンド ===
    subparsers.add_parser("sample", help="使い方ガイドを表示")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "predict": cmd_predict,
        "fetch": cmd_fetch,
        "list": cmd_list,
        "import-csv": cmd_import_csv,
        "backtest": cmd_backtest,
        "train": cmd_train,
        "info": cmd_info,
        "sample": cmd_sample,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
