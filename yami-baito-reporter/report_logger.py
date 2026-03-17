"""闇バイト通報支援ツール — 通報記録の保存・読込"""

import json
import os
from datetime import datetime


REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def save_report(checked_ids, risk_level, source_url="", notes="", reported_to=None):
    """チェック結果をJSONファイルとして保存する。

    Returns:
        保存したファイルのパス
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "checked_items": checked_ids,
        "risk_level": risk_level,
        "source_url": source_url,
        "notes": notes,
        "reported_to": reported_to or [],
    }

    filename = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".json"
    filepath = os.path.join(REPORTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return filepath


def load_reports():
    """保存済みの通報記録を一覧で取得する（新しい順）。

    Returns:
        list[dict]: 記録のリスト
    """
    if not os.path.isdir(REPORTS_DIR):
        return []

    reports = []
    for name in sorted(os.listdir(REPORTS_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        filepath = os.path.join(REPORTS_DIR, name)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_filename"] = name
                reports.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return reports
