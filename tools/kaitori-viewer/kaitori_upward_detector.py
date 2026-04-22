"""買取価格上昇検知（戦略E）

auto_extract 起動毎にCSV要約をスナップショット保存し、
最新2スナップショットを比較して買取価格が上昇したJANを抽出する。
買取店の値上げ = 需要急増の先行指標 → ECがまだ追従していない隙が利益チャンス。

使い方:
    from kaitori_upward_detector import save_snapshot, detect_kaitori_increases
    save_snapshot(df)
    increases = detect_kaitori_increases(min_increase_pct=5.0)

    # 単体テスト
    python kaitori_upward_detector.py
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

_SNAPSHOT_DIR = Path.home() / ".kaitori-viewer" / "kaitori_snapshots"
_MAX_SNAPSHOTS = 30  # 直近30件まで保持
_CSV_DIR = Path(__file__).resolve().parent.parent.parent  # amcompany/
_CSV_TS_PATTERN = re.compile(r"all_data_(\d{12})\.csv$")


def _ensure_dir() -> None:
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def save_snapshot(df: pd.DataFrame) -> Path:
    """現在のCSV要約をスナップショット保存。

    保存内容: {jan: {"price": int, "shops": int}}

    Args:
        df: csv_loader.load_csv() の戻り値

    Returns:
        保存先パス
    """
    _ensure_dir()

    snapshot: dict[str, dict] = {}
    for _, row in df.iterrows():
        jan = str(row.get("JAN", "")).strip()
        if not jan:
            continue
        try:
            price = int(row.get("最高買取価格", 0))
            shops = int(row.get("買取店数", 0))
        except (ValueError, TypeError):
            continue
        if price <= 0:
            continue
        snapshot[jan] = {"price": price, "shops": shops}

    path = _SNAPSHOT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

    _prune_old_snapshots()
    return path


def _prune_old_snapshots() -> None:
    """直近 _MAX_SNAPSHOTS 件を超えた古いスナップショットを削除"""
    snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"), reverse=True)
    for old in snapshots[_MAX_SNAPSHOTS:]:
        try:
            old.unlink()
        except OSError:
            pass


def bootstrap_from_csv_files() -> int:
    """既存の all_data_YYYYMMDDHHMM.csv から未保存のスナップショットを生成。

    各CSVファイルのタイムスタンプをファイル名から抽出し、同名のスナップショットが
    存在しないものだけ生成する（冪等）。

    Returns:
        新規作成したスナップショット数
    """
    _ensure_dir()
    from csv_loader import load_csv  # 遅延インポート（循環回避）

    csv_files = sorted(_CSV_DIR.glob("all_data_*.csv"))
    created = 0
    for csv_path in csv_files:
        m = _CSV_TS_PATTERN.search(csv_path.name)
        if not m:
            continue
        ts = m.group(1)  # YYYYMMDDHHMM
        # JSONファイル名を YYYYMMDD_HHMMSS 形式に統一（00秒を付加）
        snapshot_name = f"{ts[:8]}_{ts[8:12]}00.json"
        snapshot_path = _SNAPSHOT_DIR / snapshot_name
        if snapshot_path.exists():
            continue

        df = load_csv(str(csv_path))
        snapshot: dict[str, dict] = {}
        for _, row in df.iterrows():
            jan = str(row.get("JAN", "")).strip()
            if not jan:
                continue
            try:
                price = int(row.get("最高買取価格", 0))
                shops = int(row.get("買取店数", 0))
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue
            snapshot[jan] = {"price": price, "shops": shops}

        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        created += 1

    if created:
        _prune_old_snapshots()
    return created


def detect_kaitori_increases(
    min_increase_pct: float = 5.0,
    min_old_price: int = 1000,
) -> list[tuple[str, float]]:
    """買取価格が上昇したJANを (jan, increase_pct) で返す（降順）。

    Args:
        min_increase_pct: この上昇率（%）未満は対象外
        min_old_price: 古い価格がこの値（円）未満のJANは対象外（ノイズ排除）

    Returns:
        [(jan, increase_pct), ...] 上昇率の大きい順
    """
    snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"), reverse=True)
    if len(snapshots) < 2:
        # CSVファイルから自動ブートストラップを試行
        bootstrap_from_csv_files()
        snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"), reverse=True)
        if len(snapshots) < 2:
            return []

    try:
        latest = json.loads(snapshots[0].read_text(encoding="utf-8"))
        prev = json.loads(snapshots[1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    results: list[tuple[str, float]] = []
    for jan, cur in latest.items():
        old = prev.get(jan)
        if not old:
            continue
        old_price = old.get("price", 0)
        cur_price = cur.get("price", 0)
        if old_price < min_old_price or cur_price <= old_price:
            continue
        pct = (cur_price - old_price) / old_price * 100
        if pct >= min_increase_pct:
            results.append((jan, pct))

    return sorted(results, key=lambda x: x[1], reverse=True)


def detect_kaitori_disappearances(min_prev_shops: int = 3) -> list[str]:
    """戦略O: 過去は買取店がいたが現在いなくなったJAN（買取上限/買取停止の疑い）。

    買取店が扱いをやめる = 需要爆発で買取上限到達 or 価格調整中のシグナル。
    誤検知回避のため過去に `min_prev_shops` 以上の店舗が扱っていたJANに限定。

    Args:
        min_prev_shops: 過去スナップショットでこの店舗数以上あったJANのみ対象

    Returns:
        消失JANのリスト（元の店舗数降順）
    """
    snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"), reverse=True)
    if len(snapshots) < 2:
        bootstrap_from_csv_files()
        snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"), reverse=True)
        if len(snapshots) < 2:
            return []

    try:
        latest = json.loads(snapshots[0].read_text(encoding="utf-8"))
        prev = json.loads(snapshots[1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    disappeared: list[tuple[str, int]] = []
    for jan, old in prev.items():
        if jan in latest:
            continue
        shops = old.get("shops", 0)
        if shops >= min_prev_shops:
            disappeared.append((jan, shops))

    return [j for j, _ in sorted(disappeared, key=lambda x: x[1], reverse=True)]


if __name__ == "__main__":
    # 既存CSVから未生成のスナップショットを作成
    created = bootstrap_from_csv_files()
    if created:
        print(f"CSV からスナップショット {created} 件を生成")

    snapshots = sorted(_SNAPSHOT_DIR.glob("*.json"))
    print(f"スナップショット数: {len(snapshots)}件")
    for s in snapshots:
        print(f"  {s.name}")

    increases = detect_kaitori_increases(min_increase_pct=5.0)
    print(f"\n=== 買取価格上昇検知 ===")
    print(f"検出数: {len(increases)}件")
    for jan, pct in increases[:20]:
        print(f"  {jan}: +{pct:.1f}%")
    if not increases and len(snapshots) >= 2:
        print("5%以上の上昇なし")
