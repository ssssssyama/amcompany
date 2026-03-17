"""SQLiteデータベース管理 — レースデータの永続化・検索"""

import os
import csv
import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS races (
    race_id TEXT,
    race_date TEXT,
    venue TEXT,
    race_number INTEGER,
    race_name TEXT,
    grade TEXT,
    distance INTEGER,
    surface TEXT,
    track_condition TEXT,
    weather TEXT,
    horse_number INTEGER,
    gate_number INTEGER,
    horse_name TEXT,
    horse_id TEXT,
    sex_age TEXT,
    weight REAL,
    jockey_name TEXT,
    jockey_id TEXT,
    trainer_name TEXT,
    odds REAL,
    popularity INTEGER,
    finish_position INTEGER,
    finish_time REAL,
    last_3f REAL,
    horse_weight INTEGER,
    horse_weight_diff INTEGER,
    corner_positions TEXT,
    PRIMARY KEY (race_id, horse_number)
);

CREATE INDEX IF NOT EXISTS idx_horse ON races(horse_id, race_date);
CREATE INDEX IF NOT EXISTS idx_jockey ON races(jockey_id, race_date);
CREATE INDEX IF NOT EXISTS idx_race_date ON races(race_date);
"""

COLUMNS = [
    "race_id", "race_date", "venue", "race_number", "race_name", "grade",
    "distance", "surface", "track_condition", "weather",
    "horse_number", "gate_number", "horse_name", "horse_id", "sex_age",
    "weight", "jockey_name", "jockey_id", "trainer_name",
    "odds", "popularity", "finish_position", "finish_time", "last_3f",
    "horse_weight", "horse_weight_diff", "corner_positions",
]

INT_COLUMNS = {"race_number", "distance", "horse_number", "gate_number",
               "popularity", "finish_position", "horse_weight", "horse_weight_diff"}
FLOAT_COLUMNS = {"weight", "odds", "finish_time", "last_3f"}


def _parse_val(col, val):
    """カラムに応じた型変換"""
    if val is None or val == "":
        if col in INT_COLUMNS:
            return 0
        if col in FLOAT_COLUMNS:
            return 0.0
        return ""
    if col in INT_COLUMNS:
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0
    if col in FLOAT_COLUMNS:
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0
    return str(val)


class Database:
    """SQLiteデータベース"""

    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def insert_race_results(self, rows):
        """レース結果をUPSERT（既存データがあれば上書き）"""
        if not rows:
            return 0

        placeholders = ", ".join(["?"] * len(COLUMNS))
        col_names = ", ".join(COLUMNS)
        sql = f"INSERT OR REPLACE INTO races ({col_names}) VALUES ({placeholders})"

        data = []
        for row in rows:
            vals = tuple(_parse_val(c, row.get(c)) for c in COLUMNS)
            data.append(vals)

        self.conn.executemany(sql, data)
        self.conn.commit()
        return len(data)

    def load_all_races(self):
        """全レースデータを辞書リストで返す（既存のload_racesと互換）"""
        cursor = self.conn.execute(
            "SELECT * FROM races WHERE finish_position > 0 ORDER BY race_date"
        )
        return [self._row_to_dict(r) for r in cursor.fetchall()]

    def has_race(self, race_id):
        """指定レースIDのデータが存在するか"""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM races WHERE race_id = ?", (race_id,)
        )
        return cursor.fetchone()[0] > 0

    def get_summary(self):
        """データの概要を返す"""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT race_id) as total_races,
                COUNT(DISTINCT horse_id) as total_horses,
                COUNT(DISTINCT jockey_id) as total_jockeys,
                MIN(race_date) as min_date,
                MAX(race_date) as max_date
            FROM races
        """)
        row = cursor.fetchone()
        if row["total_rows"] == 0:
            return {"total_rows": 0}

        venues = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT venue FROM races ORDER BY venue"
        ).fetchall()]
        grades = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT grade FROM races ORDER BY grade"
        ).fetchall()]

        return {
            "total_rows": row["total_rows"],
            "total_races": row["total_races"],
            "total_horses": row["total_horses"],
            "total_jockeys": row["total_jockeys"],
            "venues": venues,
            "date_range": f"{row['min_date']} 〜 {row['max_date']}",
            "grades": grades,
        }

    def import_csv(self, csv_path):
        """CSVファイルからデータをインポート"""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSVファイルが見つかりません: {csv_path}")

        rows = []
        with open(csv_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        count = self.insert_race_results(rows)
        return count

    def _row_to_dict(self, row):
        """sqlite3.Rowを型変換済みdictに変換"""
        d = dict(row)
        for col in INT_COLUMNS:
            d[col] = _parse_val(col, d.get(col))
        for col in FLOAT_COLUMNS:
            d[col] = _parse_val(col, d.get(col))
        return d
