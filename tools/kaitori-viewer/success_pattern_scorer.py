"""過去成功パターン学習（戦略Z）

cache_results.json の過去利益商品（現金利益>0）から統計的特徴を抽出し、
新JANを類似度スコアリングする。

特徴:
- カテゴリ分布
- 買取価格帯分布
- 商品名キーワード（2-gram）頻度

使い方:
    from success_pattern_scorer import build_pattern_model, score_jan
    model = build_pattern_model()
    score = score_jan(row, model)  # 0.5〜2.0

    # 単体テスト
    python success_pattern_scorer.py
"""

import json
import re
from collections import Counter
from pathlib import Path

_CACHE_FILE = Path.home() / ".kaitori-viewer" / "cache_results.json"

# 価格帯バケット（円）
_PRICE_BUCKETS = [
    (0, 5000),
    (5000, 10000),
    (10000, 20000),
    (20000, 50000),
    (50000, 100000),
    (100000, float("inf")),
]

_MIN_SAMPLES = 5  # これ未満ならモデル構築せず全JANスコア1.0


def _bucket_index(price: int) -> int:
    for i, (lo, hi) in enumerate(_PRICE_BUCKETS):
        if lo <= price < hi:
            return i
    return len(_PRICE_BUCKETS) - 1


def _extract_keywords(name: str) -> list[str]:
    """商品名から英数字のキーワードと2-gramを抽出"""
    if not name:
        return []
    # 英数字トークン（モデル名等）
    alnum = re.findall(r"[A-Za-z0-9]{2,}", name)
    # カタカナ2-gram（ブランド・商品タイプ）
    katakana = re.findall(r"[ァ-ヶー]{2,}", name)
    return [t.upper() for t in alnum] + katakana


def build_pattern_model() -> dict:
    """cache_results.json から利益商品パターンモデルを構築。

    Returns:
        {
            "categories": Counter, "price_buckets": Counter,
            "keywords": Counter, "total": int
        }
        または空モデル {"total": 0}
    """
    if not _CACHE_FILE.exists():
        return {"total": 0}

    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"total": 0}

    categories: Counter = Counter()
    price_buckets: Counter = Counter()
    keywords: Counter = Counter()
    profitable_count = 0

    for r in data:
        if not isinstance(r, dict):
            continue
        profit = r.get("現金利益", 0)
        if not isinstance(profit, (int, float)) or profit <= 0:
            continue
        profitable_count += 1

        # カテゴリ分布
        cat = str(r.get("カテゴリ", "") or "")
        for c in cat.split("、"):
            c = c.strip()
            if c:
                categories[c] += 1

        # 価格帯分布
        try:
            price = int(r.get("最高買取価格", 0))
            if price > 0:
                price_buckets[_bucket_index(price)] += 1
        except (ValueError, TypeError):
            pass

        # キーワード分布
        name = str(r.get("商品名", "") or "")
        for kw in _extract_keywords(name):
            keywords[kw] += 1

    if profitable_count < _MIN_SAMPLES:
        return {"total": profitable_count}

    return {
        "total": profitable_count,
        "categories": categories,
        "price_buckets": price_buckets,
        "keywords": keywords,
    }


def score_jan(row: dict, model: dict) -> float:
    """JANをパターンモデルに対してスコアリング。

    Args:
        row: DataFrameの1行（カテゴリ/最高買取価格/商品名を含む）
        model: build_pattern_model() の戻り値

    Returns:
        0.5〜2.0 のスコア（1.0 = 中立、>1.0 = 過去利益パターンと類似）
    """
    if model.get("total", 0) < _MIN_SAMPLES:
        return 1.0

    total = model["total"]
    categories: Counter = model["categories"]
    price_buckets: Counter = model["price_buckets"]
    keywords: Counter = model["keywords"]

    # カテゴリ一致率
    cat_score = 0.0
    cat = str(row.get("カテゴリ", "") or "")
    for c in cat.split("、"):
        c = c.strip()
        if c and c in categories:
            cat_score = max(cat_score, categories[c] / total)

    # 価格帯一致率
    price_score = 0.0
    try:
        price = int(row.get("最高買取価格", 0))
        if price > 0:
            bi = _bucket_index(price)
            price_score = price_buckets.get(bi, 0) / total
    except (ValueError, TypeError):
        pass

    # キーワード一致率（商品名から抽出したキーワードの最高出現率）
    kw_score = 0.0
    name = str(row.get("商品名", "") or "")
    for kw in _extract_keywords(name):
        if kw in keywords:
            kw_score = max(kw_score, keywords[kw] / total)

    # 重み付け合成: カテゴリ0.4 + 価格帯0.2 + キーワード0.4
    combined = cat_score * 0.4 + price_score * 0.2 + kw_score * 0.4
    # 0.0〜1.0 を 0.5〜2.0 にマッピング
    return 0.5 + combined * 1.5


if __name__ == "__main__":
    model = build_pattern_model()
    print(f"=== パターンモデル ===")
    print(f"学習サンプル数: {model.get('total', 0)}件")
    if model.get("total", 0) < _MIN_SAMPLES:
        print(f"サンプル不足（{_MIN_SAMPLES}件以上必要）")
    else:
        print(f"\nカテゴリTOP5:")
        for c, n in model["categories"].most_common(5):
            print(f"  {c}: {n}件 ({n/model['total']*100:.1f}%)")
        print(f"\n価格帯分布:")
        for bi, n in sorted(model["price_buckets"].items()):
            lo, hi = _PRICE_BUCKETS[bi]
            hi_s = f"{hi:,}" if hi != float("inf") else "∞"
            print(f"  {lo:,}〜{hi_s}円: {n}件 ({n/model['total']*100:.1f}%)")
        print(f"\nキーワードTOP10:")
        for kw, n in model["keywords"].most_common(10):
            print(f"  {kw}: {n}件 ({n/model['total']*100:.1f}%)")
