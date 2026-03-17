"""netkeiba.comスクレイパー — レース結果・出馬表の自動取得"""

import re
import time
import warnings

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


# 競馬場コード → 日本語名
VENUE_CODES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}

# グレード判定用パターン
GRADE_PATTERNS = [
    (re.compile(r"G1|GI|Ｇ１"), "G1"),
    (re.compile(r"G2|GII|Ｇ２"), "G2"),
    (re.compile(r"G3|GIII|Ｇ３"), "G3"),
    (re.compile(r"オープン|OP|L"), "OP"),
    (re.compile(r"3勝|1600万"), "3勝"),
    (re.compile(r"2勝|1000万"), "2勝"),
    (re.compile(r"1勝|500万"), "1勝"),
    (re.compile(r"未勝利"), "未勝利"),
    (re.compile(r"新馬"), "新馬"),
]

# レート制限用
_last_request_time = 0.0
_REQUEST_INTERVAL = 1.0  # 秒


def _check_dependencies():
    """依存パッケージの確認"""
    if requests is None:
        raise ImportError("requests")
    if BeautifulSoup is None:
        raise ImportError("bs4")


def _request_with_retry(url, max_retries=3, delay=1.0):
    """リトライ付きHTTPリクエスト（レート制限対応）"""
    _check_dependencies()

    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - elapsed)

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; keiba-predictor/1.0)",
    }

    for attempt in range(max_retries):
        try:
            _last_request_time = time.time()
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                print(f"  リクエスト失敗（リトライ {attempt + 1}/{max_retries}）: {e}")
                time.sleep(wait)
            else:
                raise


def _parse_venue_from_race_id(race_id):
    """レースIDから競馬場名を取得"""
    if len(race_id) >= 6:
        code = race_id[4:6]
        return VENUE_CODES.get(code, f"不明({code})")
    return "不明"


def _parse_grade(text):
    """テキストからグレードを判定"""
    for pattern, grade in GRADE_PATTERNS:
        if pattern.search(text):
            return grade
    return "不明"


def _parse_time_to_seconds(time_str):
    """タイム文字列を秒に変換（例: '1:34.5' → 94.5）"""
    time_str = time_str.strip()
    if not time_str or time_str == "-":
        return 0.0
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        return float(time_str)
    except (ValueError, IndexError):
        return 0.0


def _clean_text(text):
    """テキストのクリーニング"""
    if not text:
        return ""
    return re.sub(r'\s+', '', text.strip())


def fetch_race_result(race_id):
    """過去レース結果を取得

    Args:
        race_id: レースID（例: '202505021211'）

    Returns:
        list[dict]: 各馬のレース結果（CSVカラム形式）
    """
    _check_dependencies()
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    resp = _request_with_retry(url)

    # netkeiba.comはEUC-JPの場合があるが、race.netkeiba.comはUTF-8
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    # レース情報取得
    race_info = _parse_race_header(soup, race_id)

    # 結果テーブル取得
    result_table = soup.select_one("table.RaceTable01, table.Shutuba_Table, table.HorseList")
    if not result_table:
        # 旧フォーマットを試行
        result_table = soup.select_one("table")

    if not result_table:
        warnings.warn(f"レース結果テーブルが見つかりません: {race_id}")
        return []

    rows = []
    for tr in result_table.select("tbody tr, tr.HorseList"):
        tds = tr.select("td")
        if len(tds) < 8:
            continue

        try:
            row = _parse_result_row(tds, race_id, race_info)
            if row:
                rows.append(row)
        except Exception as e:
            warnings.warn(f"行のパースに失敗（スキップ）: {e}")
            continue

    return rows


def _parse_race_header(soup, race_id):
    """レースヘッダー情報をパース"""
    info = {
        "race_id": race_id,
        "race_date": "",
        "venue": _parse_venue_from_race_id(race_id),
        "race_number": 0,
        "race_name": "",
        "grade": "",
        "distance": 0,
        "surface": "",
        "track_condition": "",
        "weather": "",
    }

    # レース番号（IDの末尾2桁）
    if len(race_id) >= 12:
        try:
            info["race_number"] = int(race_id[10:12])
        except ValueError:
            pass

    # レース名
    name_el = soup.select_one(".RaceName, .racedata h1, h1")
    if name_el:
        info["race_name"] = _clean_text(name_el.get_text())
        info["grade"] = _parse_grade(info["race_name"])

    # レース詳細（距離・馬場など）
    detail_el = soup.select_one(".RaceData01, .racedata span, .RaceData")
    if detail_el:
        detail_text = detail_el.get_text()
        # 芝/ダート
        if "芝" in detail_text:
            info["surface"] = "芝"
        elif "ダ" in detail_text or "ダート" in detail_text:
            info["surface"] = "ダート"
        # 距離
        dist_match = re.search(r'(\d{3,4})m', detail_text)
        if dist_match:
            info["distance"] = int(dist_match.group(1))
        # 馬場状態
        for cond in ["不良", "重", "稍重", "良"]:
            if cond in detail_text:
                info["track_condition"] = cond
                break
        # 天候
        for w in ["雪", "雨", "小雨", "曇", "晴"]:
            if w in detail_text:
                info["weather"] = w
                break

    # 日付
    date_el = soup.select_one(".RaceData02 .smalltxt, .racedata dd, #RaceList_DateList")
    if date_el:
        date_match = re.search(r'(\d{4})[/年](\d{1,2})[/月](\d{1,2})', date_el.get_text())
        if date_match:
            info["race_date"] = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    # 日付がヘッダーから取れない場合、レースIDから推定
    if not info["race_date"] and len(race_id) >= 4:
        info["race_date"] = f"{race_id[:4]}-01-01"

    return info


def _parse_result_row(tds, race_id, race_info):
    """結果テーブルの1行をパース"""
    row = dict(race_info)

    # 着順
    finish_text = _clean_text(tds[0].get_text())
    try:
        row["finish_position"] = int(finish_text)
    except ValueError:
        row["finish_position"] = 0

    # 枠番
    row["gate_number"] = 0
    if len(tds) > 1:
        try:
            row["gate_number"] = int(_clean_text(tds[1].get_text()))
        except ValueError:
            pass

    # 馬番
    row["horse_number"] = 0
    if len(tds) > 2:
        try:
            row["horse_number"] = int(_clean_text(tds[2].get_text()))
        except ValueError:
            pass

    # 馬名
    row["horse_name"] = ""
    row["horse_id"] = ""
    if len(tds) > 3:
        name_el = tds[3].select_one("a")
        if name_el:
            row["horse_name"] = _clean_text(name_el.get_text())
            href = name_el.get("href", "")
            id_match = re.search(r'/horse/(\w+)', href)
            if id_match:
                row["horse_id"] = id_match.group(1)
        else:
            row["horse_name"] = _clean_text(tds[3].get_text())

    # 性齢
    row["sex_age"] = ""
    if len(tds) > 4:
        row["sex_age"] = _clean_text(tds[4].get_text())

    # 斤量
    row["weight"] = 0.0
    if len(tds) > 5:
        try:
            row["weight"] = float(_clean_text(tds[5].get_text()))
        except ValueError:
            pass

    # 騎手
    row["jockey_name"] = ""
    row["jockey_id"] = ""
    if len(tds) > 6:
        jockey_el = tds[6].select_one("a")
        if jockey_el:
            row["jockey_name"] = _clean_text(jockey_el.get_text())
            href = jockey_el.get("href", "")
            id_match = re.search(r'/jockey/(?:result/recent/)?(\w+)', href)
            if id_match:
                row["jockey_id"] = id_match.group(1)
        else:
            row["jockey_name"] = _clean_text(tds[6].get_text())

    # タイム
    row["finish_time"] = 0.0
    if len(tds) > 7:
        row["finish_time"] = _parse_time_to_seconds(_clean_text(tds[7].get_text()))

    # 着差（タイムの次のカラム）
    # 上がり3F
    row["last_3f"] = 0.0
    for i in range(8, min(len(tds), 14)):
        text = _clean_text(tds[i].get_text())
        try:
            val = float(text)
            if 30.0 <= val <= 45.0:
                row["last_3f"] = val
                break
        except ValueError:
            continue

    # 人気
    row["popularity"] = 0
    row["odds"] = 0.0
    for i in range(8, min(len(tds), 16)):
        text = _clean_text(tds[i].get_text())
        try:
            val = float(text)
            if 1.0 <= val <= 999.9 and val != row["last_3f"]:
                if row["odds"] == 0.0:
                    row["odds"] = val
                elif row["popularity"] == 0 and val == int(val):
                    row["popularity"] = int(val)
        except ValueError:
            continue

    # 馬体重
    row["horse_weight"] = 0
    row["horse_weight_diff"] = 0
    for i in range(8, len(tds)):
        text = tds[i].get_text().strip()
        wt_match = re.search(r'(\d{3,4})\s*\(([+\-]?\d+)\)', text)
        if wt_match:
            row["horse_weight"] = int(wt_match.group(1))
            row["horse_weight_diff"] = int(wt_match.group(2))
            break

    # コーナー通過順
    row["corner_positions"] = ""
    for i in range(8, len(tds)):
        text = _clean_text(tds[i].get_text())
        if re.match(r'^\d+-\d+', text):
            row["corner_positions"] = text
            break

    # 調教師
    row["trainer_name"] = ""
    for i in range(8, len(tds)):
        el = tds[i].select_one("a[href*='/trainer/']")
        if el:
            row["trainer_name"] = _clean_text(el.get_text())
            break

    return row


def fetch_race_card(race_id):
    """出馬表（未来レース）を取得

    Args:
        race_id: レースID

    Returns:
        list[dict]: 各馬のエントリ情報（結果カラムは空）
    """
    _check_dependencies()
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    resp = _request_with_retry(url)
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    race_info = _parse_race_header(soup, race_id)

    table = soup.select_one("table.Shutuba_Table, table.RaceTable01, table.HorseList")
    if not table:
        table = soup.select_one("table")
    if not table:
        warnings.warn(f"出馬表テーブルが見つかりません: {race_id}")
        return []

    rows = []
    for tr in table.select("tbody tr, tr.HorseList"):
        tds = tr.select("td")
        if len(tds) < 5:
            continue

        try:
            row = dict(race_info)

            # 枠番
            row["gate_number"] = 0
            try:
                row["gate_number"] = int(_clean_text(tds[0].get_text()))
            except ValueError:
                pass

            # 馬番
            row["horse_number"] = 0
            try:
                row["horse_number"] = int(_clean_text(tds[1].get_text()))
            except ValueError:
                pass

            # 馬名
            row["horse_name"] = ""
            row["horse_id"] = ""
            name_td = tds[3] if len(tds) > 3 else tds[2]
            name_el = name_td.select_one("a")
            if name_el:
                row["horse_name"] = _clean_text(name_el.get_text())
                href = name_el.get("href", "")
                id_match = re.search(r'/horse/(\w+)', href)
                if id_match:
                    row["horse_id"] = id_match.group(1)
            else:
                row["horse_name"] = _clean_text(name_td.get_text())

            # 性齢
            row["sex_age"] = ""
            if len(tds) > 4:
                row["sex_age"] = _clean_text(tds[4].get_text())

            # 斤量
            row["weight"] = 0.0
            if len(tds) > 5:
                try:
                    row["weight"] = float(_clean_text(tds[5].get_text()))
                except ValueError:
                    pass

            # 騎手
            row["jockey_name"] = ""
            row["jockey_id"] = ""
            if len(tds) > 6:
                jockey_el = tds[6].select_one("a")
                if jockey_el:
                    row["jockey_name"] = _clean_text(jockey_el.get_text())
                    href = jockey_el.get("href", "")
                    id_match = re.search(r'/jockey/(?:result/recent/)?(\w+)', href)
                    if id_match:
                        row["jockey_id"] = id_match.group(1)

            # 調教師
            row["trainer_name"] = ""
            for td in tds:
                el = td.select_one("a[href*='/trainer/']")
                if el:
                    row["trainer_name"] = _clean_text(el.get_text())
                    break

            # 馬体重
            row["horse_weight"] = 0
            row["horse_weight_diff"] = 0

            # 結果系は空
            row["odds"] = 0.0
            row["popularity"] = 0
            row["finish_position"] = 0
            row["finish_time"] = 0.0
            row["last_3f"] = 0.0
            row["corner_positions"] = ""

            if row["horse_name"]:
                rows.append(row)

        except Exception as e:
            warnings.warn(f"出馬表行のパースに失敗（スキップ）: {e}")
            continue

    return rows


def fetch_race_list(date_str):
    """指定日のレース一覧を取得

    Args:
        date_str: 日付（'YYYY-MM-DD' または 'YYYYMMDD'）

    Returns:
        list[dict]: レース情報リスト [{race_id, venue, race_number, race_name}, ...]
    """
    _check_dependencies()
    date_clean = date_str.replace("-", "")
    url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={date_clean}"
    resp = _request_with_retry(url)
    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    races = []
    for a_tag in soup.select("a[href*='race_id=']"):
        href = a_tag.get("href", "")
        id_match = re.search(r'race_id=(\d+)', href)
        if not id_match:
            continue

        race_id = id_match.group(1)
        race_name = _clean_text(a_tag.get_text())

        # 重複チェック
        if any(r["race_id"] == race_id for r in races):
            continue

        venue = _parse_venue_from_race_id(race_id)
        race_number = 0
        if len(race_id) >= 12:
            try:
                race_number = int(race_id[10:12])
            except ValueError:
                pass

        races.append({
            "race_id": race_id,
            "venue": venue,
            "race_number": race_number,
            "race_name": race_name,
        })

    races.sort(key=lambda x: (x["venue"], x["race_number"]))
    return races
