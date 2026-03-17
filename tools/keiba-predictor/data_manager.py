"""データ管理モジュール — CSV/SQLiteファイルの読込・検証・データ取得"""

import os
import csv
from datetime import datetime, timedelta


REQUIRED_COLUMNS = [
    "race_id", "race_date", "venue", "race_number", "race_name", "grade",
    "distance", "surface", "track_condition", "weather",
    "horse_number", "gate_number", "horse_name", "horse_id", "sex_age",
    "weight", "jockey_name", "jockey_id", "trainer_name",
    "horse_weight",
]

RESULT_COLUMNS = ["finish_position", "finish_time", "last_3f", "corner_positions"]


def _parse_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _parse_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def load_races(data_dir):
    """過去レースデータを読み込む

    Returns:
        list[dict]: 各行を辞書にしたリスト（型変換済み）
    """
    path = os.path.join(data_dir, "races.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"レースデータが見つかりません: {path}")

    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        # カラム検証
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"races.csv に必要なカラムがありません: {', '.join(sorted(missing))}")

        for row in reader:
            row["race_number"] = _parse_int(row.get("race_number"))
            row["distance"] = _parse_int(row.get("distance"))
            row["horse_number"] = _parse_int(row.get("horse_number"))
            row["gate_number"] = _parse_int(row.get("gate_number"))
            row["weight"] = _parse_float(row.get("weight"))
            row["odds"] = _parse_float(row.get("odds"))
            row["popularity"] = _parse_int(row.get("popularity"))
            row["finish_position"] = _parse_int(row.get("finish_position"))
            row["finish_time"] = _parse_float(row.get("finish_time"))
            row["last_3f"] = _parse_float(row.get("last_3f"))
            row["horse_weight"] = _parse_int(row.get("horse_weight"))
            row["horse_weight_diff"] = _parse_int(row.get("horse_weight_diff"))
            rows.append(row)

    return rows


def load_upcoming(path):
    """予測対象レースデータを読み込む

    Returns:
        list[dict]: 各行を辞書にしたリスト
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"予測対象データが見つかりません: {path}")

    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["race_number"] = _parse_int(row.get("race_number"))
            row["distance"] = _parse_int(row.get("distance"))
            row["horse_number"] = _parse_int(row.get("horse_number"))
            row["gate_number"] = _parse_int(row.get("gate_number"))
            row["weight"] = _parse_float(row.get("weight"))
            row["horse_weight"] = _parse_int(row.get("horse_weight"))
            row["horse_weight_diff"] = _parse_int(row.get("horse_weight_diff"))
            rows.append(row)

    return rows


def load_races_from_db(db_path):
    """SQLiteデータベースから過去レースデータを読み込む

    Returns:
        list[dict]: 各行を辞書にしたリスト（型変換済み）
    """
    from database import Database
    db = Database(db_path)
    rows = db.load_all_races()
    db.close()
    return rows


def load_upcoming_from_scraper(race_id):
    """スクレイパー経由で出馬表を取得

    Returns:
        list[dict]: 各馬のエントリ情報
    """
    from scraper import fetch_race_card
    rows = fetch_race_card(race_id)
    if not rows:
        raise ValueError(f"出馬表を取得できませんでした: {race_id}")
    # 型変換
    for row in rows:
        row["race_number"] = _parse_int(row.get("race_number"))
        row["distance"] = _parse_int(row.get("distance"))
        row["horse_number"] = _parse_int(row.get("horse_number"))
        row["gate_number"] = _parse_int(row.get("gate_number"))
        row["weight"] = _parse_float(row.get("weight"))
        row["horse_weight"] = _parse_int(row.get("horse_weight"))
        row["horse_weight_diff"] = _parse_int(row.get("horse_weight_diff"))
    return rows


def get_horse_history(races, horse_id, before_date=None):
    """指定馬の過去成績を取得（before_dateより前のレースのみ）"""
    results = []
    for r in races:
        if r["horse_id"] != horse_id:
            continue
        if r["finish_position"] == 0:
            continue
        if before_date and r["race_date"] >= before_date:
            continue
        results.append(r)
    results.sort(key=lambda x: x["race_date"], reverse=True)
    return results


def get_jockey_history(races, jockey_id, before_date=None):
    """指定騎手の過去成績を取得"""
    results = []
    for r in races:
        if r["jockey_id"] != jockey_id:
            continue
        if r["finish_position"] == 0:
            continue
        if before_date and r["race_date"] >= before_date:
            continue
        results.append(r)
    results.sort(key=lambda x: x["race_date"], reverse=True)
    return results


def get_race_info(upcoming_rows):
    """予測対象レースの基本情報を取得"""
    if not upcoming_rows:
        raise ValueError("予測対象データが空です")
    first = upcoming_rows[0]
    return {
        "race_id": first["race_id"],
        "race_date": first["race_date"],
        "venue": first["venue"],
        "race_number": first["race_number"],
        "race_name": first["race_name"],
        "grade": first["grade"],
        "distance": first["distance"],
        "surface": first["surface"],
        "track_condition": first["track_condition"],
        "weather": first["weather"],
    }


def get_data_summary(races):
    """データの概要を返す"""
    if not races:
        return {"total_rows": 0}

    race_ids = set(r["race_id"] for r in races)
    horse_ids = set(r["horse_id"] for r in races)
    jockey_ids = set(r["jockey_id"] for r in races)
    venues = set(r["venue"] for r in races)
    dates = sorted(set(r["race_date"] for r in races))

    return {
        "total_rows": len(races),
        "total_races": len(race_ids),
        "total_horses": len(horse_ids),
        "total_jockeys": len(jockey_ids),
        "venues": sorted(venues),
        "date_range": f"{dates[0]} 〜 {dates[-1]}" if dates else "N/A",
        "grades": sorted(set(r["grade"] for r in races)),
    }
