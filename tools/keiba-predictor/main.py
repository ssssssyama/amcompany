"""JRA競馬予想ツール — 過去データから馬券予想を生成"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from common.error_handler import friendly_error_handler
from data_manager import load_races, load_upcoming, get_race_info, get_data_summary
from feature_engine import compute_all_features
from predictor import StatisticalPredictor, MLPredictor, train_ml_model
from formatter import format_full_prediction


def cmd_predict(args):
    """レース予想を実行"""
    data_dir = args.data_dir
    race_path = args.race

    print("データを読み込んでいます...")
    races = load_races(data_dir)
    upcoming = load_upcoming(race_path)
    race_info = get_race_info(upcoming)

    print("特徴量を計算しています...")
    features = compute_all_features(races, upcoming, race_info)

    print("予想を計算しています...")
    if args.method == "ml":
        predictor = MLPredictor()
        model_path = os.path.join(data_dir, "..", "models", "model.pkl")
        model_path = os.path.normpath(model_path)
        predictor.load(model_path)
        ranked = predictor.predict(features)
        method = "ml"
    else:
        predictor = StatisticalPredictor()
        ranked = predictor.predict(features)
        method = "stat"

    output = format_full_prediction(ranked, race_info, top_n=args.top, method=method)
    print(output)


def cmd_train(args):
    """MLモデルを学習"""
    data_dir = args.data_dir

    print("学習データを読み込んでいます...")
    races = load_races(data_dir)

    print("モデルを学習しています...")
    predictor = train_ml_model(races, data_dir)

    output_path = args.output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    predictor.save(output_path)
    print(f"\nモデルを保存しました: {output_path}")
    print("predict コマンドで --method ml を指定すると使用できます。")


def cmd_info(args):
    """データ概要を表示"""
    data_dir = args.data_dir
    races = load_races(data_dir)
    summary = get_data_summary(races)

    print("")
    print("=" * 50)
    print("  JRA競馬予想ツール — データ概要")
    print("=" * 50)
    print(f"  データディレクトリ: {os.path.abspath(data_dir)}")
    print(f"  レコード数: {summary['total_rows']}件")
    print(f"  レース数: {summary['total_races']}レース")
    print(f"  馬数: {summary['total_horses']}頭")
    print(f"  騎手数: {summary['total_jockeys']}名")
    print(f"  期間: {summary['date_range']}")
    print(f"  競馬場: {', '.join(summary['venues'])}")
    print(f"  グレード: {', '.join(summary['grades'])}")
    print("=" * 50)
    print("")


def cmd_sample(args):
    """サンプルデータの使い方を表示"""
    sample_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    print("")
    print("=" * 50)
    print("  JRA競馬予想ツール — 使い方ガイド")
    print("=" * 50)
    print("")
    print("■ サンプルデータで予想を試す:")
    print(f"  python main.py predict --race {os.path.join(sample_dir, 'upcoming.csv')}")
    print("")
    print("■ データの概要を確認:")
    print(f"  python main.py info --data-dir {sample_dir}")
    print("")
    print("■ MLモデルを学習:")
    print(f"  python main.py train --data-dir {sample_dir}")
    print("")
    print("■ MLモデルで予想:")
    print(f"  python main.py predict --race {os.path.join(sample_dir, 'upcoming.csv')} --method ml")
    print("")
    print("■ 自分のデータを使う:")
    print("  1. sample_data/races.csv と同じ形式で過去レースデータCSVを用意")
    print("  2. sample_data/upcoming.csv と同じ形式で予測対象レースCSVを用意")
    print("  3. python main.py predict --race <予測CSV> --data-dir <データディレクトリ>")
    print("")
    print("=" * 50)
    print("")


@friendly_error_handler("JRA競馬予想ツール")
def main():
    parser = argparse.ArgumentParser(
        description="JRA競馬予想ツール — 過去データから馬券予想を生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用例:\n"
            "  python main.py predict --race sample_data/upcoming.csv\n"
            "  python main.py train --data-dir sample_data\n"
            "  python main.py info --data-dir sample_data\n"
            "  python main.py sample"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    # predict コマンド
    p_predict = subparsers.add_parser("predict", help="レース予想を実行")
    p_predict.add_argument("--race", required=True, help="予測対象レースCSVファイル")
    p_predict.add_argument(
        "--data-dir",
        default=os.path.join(os.path.dirname(__file__), "sample_data"),
        help="過去レースデータのディレクトリ (default: sample_data)",
    )
    p_predict.add_argument("--method", choices=["stat", "ml"], default="stat", help="予測手法 (default: stat)")
    p_predict.add_argument("--top", type=int, default=5, help="上位何頭を表示するか (default: 5)")

    # train コマンド
    p_train = subparsers.add_parser("train", help="MLモデルを学習")
    p_train.add_argument(
        "--data-dir",
        default=os.path.join(os.path.dirname(__file__), "sample_data"),
        help="学習データのディレクトリ (default: sample_data)",
    )
    p_train.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "models", "model.pkl"),
        help="モデル保存先 (default: models/model.pkl)",
    )

    # info コマンド
    p_info = subparsers.add_parser("info", help="データ概要を表示")
    p_info.add_argument(
        "--data-dir",
        default=os.path.join(os.path.dirname(__file__), "sample_data"),
        help="データディレクトリ (default: sample_data)",
    )

    # sample コマンド
    subparsers.add_parser("sample", help="サンプルデータの使い方を表示")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "predict":
        cmd_predict(args)
    elif args.command == "train":
        cmd_train(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "sample":
        cmd_sample(args)


if __name__ == "__main__":
    main()
