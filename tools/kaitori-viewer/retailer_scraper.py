"""EC価格スクレイピング（サブプロセスで実行）

Streamlitのイベントループと競合するため、Playwrightは全てサブプロセスで実行する。

直接起動モード（Playwright headless）:
- Amazon: _amazon_worker.py (Chromium)
- ヨドバシ: _yodobashi_worker.py (Firefox)
- 価格.com: _kakaku_worker.py (Chromium) → 実店舗ページ検証
- Qoo10: _qoo10_worker.py (Chromium)

CDP接続モード（実Chrome経由でTLS検知回避）:
- ビックカメラ: _biccamera_worker.py
- ジョーシン: _joshin_worker.py
- ノジマ: _nojima_worker.py
- ケーズデンキ: _ksdenki_worker.py
- ソフマップ: _sofmap_worker.py
- エディオン: _edion_worker.py
- コジマ: _kojima_worker.py
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_WORKER_DIR = Path(__file__).resolve().parent
_AMAZON_WORKER = str(_WORKER_DIR / "_amazon_worker.py")
_YODOBASHI_WORKER = str(_WORKER_DIR / "_yodobashi_worker.py")
_KAKAKU_WORKER = str(_WORKER_DIR / "_kakaku_worker.py")
_QOO10_WORKER = str(_WORKER_DIR / "_qoo10_worker.py")
_HARDOFF_WORKER = str(_WORKER_DIR / "_hardoff_worker.py")
_DOSPARA_WORKER = str(_WORKER_DIR / "_dospara_worker.py")
_TSUKUMO_WORKER = str(_WORKER_DIR / "_tsukumo_worker.py")
_PC_KOUBOU_WORKER = str(_WORKER_DIR / "_pc_koubou_worker.py")
_MAPCAMERA_WORKER = str(_WORKER_DIR / "_mapcamera_worker.py")
_KITAMURA_WORKER = str(_WORKER_DIR / "_kitamura_worker.py")
_SURUGA_YA_NEW_WORKER = str(_WORKER_DIR / "_suruga_ya_new_worker.py")
_SOUNDHOUSE_WORKER = str(_WORKER_DIR / "_soundhouse_worker.py")
_E_EARPHONE_WORKER = str(_WORKER_DIR / "_e_earphone_worker.py")
_MURAUCHI_WORKER = str(_WORKER_DIR / "_murauchi_worker.py")

import time as _time
import threading as _threading

_cb_lock = _threading.Lock()
_failure_counts: dict[str, int] = {}
_failure_timestamps: dict[str, float] = {}
# 1回の失敗でトリップ（以前の 2 は並列で重複発動、かつ応答遅延が長引く）
CIRCUIT_BREAKER_THRESHOLD = 1
CIRCUIT_BREAKER_COOLDOWN = 300  # 5分
# 既に発動済みログを出したか（重複発動ログの抑制）
_cb_tripped_logged: set[str] = set()


def _is_circuit_open(source: str) -> bool:
    with _cb_lock:
        count = _failure_counts.get(source, 0)
        if count < CIRCUIT_BREAKER_THRESHOLD:
            return False
        # クールダウン経過後に自動リセット
        last_fail = _failure_timestamps.get(source, 0)
        if _time.time() - last_fail >= CIRCUIT_BREAKER_COOLDOWN:
            _failure_counts[source] = 0
            _cb_tripped_logged.discard(source)
            logger.info("%s: サーキットブレーカーリセット（%d秒経過）", source, CIRCUIT_BREAKER_COOLDOWN)
            return False
        return True


def _record_failure(source: str):
    with _cb_lock:
        _failure_counts[source] = _failure_counts.get(source, 0) + 1
        _failure_timestamps[source] = _time.time()
        # 発動ログは1回だけ（並列スレッドから同時にこの関数が呼ばれても重複しない）
        if _failure_counts[source] >= CIRCUIT_BREAKER_THRESHOLD and source not in _cb_tripped_logged:
            _cb_tripped_logged.add(source)
            logger.warning("%s: サーキットブレーカー発動（%d回失敗、%d秒後にリセット）",
                           source, _failure_counts[source], CIRCUIT_BREAKER_COOLDOWN)


def _record_success(source: str):
    with _cb_lock:
        _failure_counts[source] = 0
        _cb_tripped_logged.discard(source)


def _kill_process_tree(proc):
    """プロセスとその子プロセス（ブラウザ等）を全て終了する"""
    try:
        import signal
        if sys.platform == "win32":
            # Windowsではtaskkillでプロセスツリーを強制終了
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        proc.kill()


def _run_worker(worker_path: str, args: list[str], source: str, timeout: int = 30) -> dict | None:
    """ワーカースクリプトをサブプロセスで実行し、JSON結果を返す"""
    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", worker_path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(_WORKER_DIR),
        )
        try:
            raw_out, raw_err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            try:
                proc.communicate(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass
            logger.warning("%s検索タイムアウト", source)
            _record_failure(source)
            return None

        stdout = raw_out.decode("utf-8", errors="replace")
        stderr = raw_err.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            logger.warning("%s検索エラー: %s", source, stderr[:200])
            _record_failure(source)
            return None

        output = stdout.strip()
        if not output or output == "null":
            _record_success(source)  # 正常な空結果（商品なし）
            return None

        data = json.loads(output)
        _record_success(source)
        return data

    except Exception as e:
        logger.warning("%s検索エラー: %s", source, e)
        _record_failure(source)
        return None


def search_amazon(jan_code: str, product_name: str = "") -> dict | None:
    """AmazonでJAN検索し、最安値の新品を返す"""
    if _is_circuit_open("Amazon"):
        return None
    return _run_worker(_AMAZON_WORKER, [jan_code], "Amazon")


def search_yodobashi(jan_code: str, product_name: str = "") -> dict | None:
    """ヨドバシで商品名検索し、最安値を返す"""
    if _is_circuit_open("ヨドバシ"):
        return None
    if not product_name:
        return None
    return _run_worker(_YODOBASHI_WORKER, [product_name], "ヨドバシ", timeout=25)


def search_kakaku(jan_code: str, product_name: str = "") -> list[dict] | dict | None:
    """価格.comで複数ショップの価格を取得し、実店舗ページで検証する。

    Returns:
        検証成功した結果のリスト（最大3件）、または後方互換のためdict/None。
    """
    if _is_circuit_open("価格.com"):
        return None
    result = _run_worker(_KAKAKU_WORKER, [jan_code], "価格.com", timeout=40)
    # ワーカーがJSON配列を返す場合はそのまま返す
    if isinstance(result, list):
        return result
    return result


_VERIFY_WORKER = str(_WORKER_DIR / "_verify_worker.py")


def verify_ec_page(url: str, expected_price: int = 0) -> dict | None:
    """任意のEC商品URLを訪問して価格・除外条件・在庫を検証する

    Returns:
        検証結果の辞書。検証失敗時は None。
        {"excluded": bool, "price": int|None, "stock_status": str,
         "name": str, "points": int, "url": str, "price_consistent": bool}
    """
    args = [url, str(expected_price)]
    return _run_worker(_VERIFY_WORKER, args, "検証", timeout=20)


def close_browser():
    """互換性のためのスタブ（サブプロセス方式では不要）"""
    pass


def search_qoo10(jan_code: str, product_name: str = "") -> dict | None:
    """Qoo10でJAN検索し、最安値を返す"""
    if _is_circuit_open("Qoo10"):
        return None
    return _run_worker(_QOO10_WORKER, [jan_code], "Qoo10", timeout=25)


def search_hardoff(jan_code: str, product_name: str = "") -> dict | None:
    """ハードオフネットモール（中古特化）でJAN検索し、最安値を返す。

    中古品なのでユニーク在庫。注文時の在庫切れリスクが低く、無在庫転売向け。
    `condition: "used"` フィールドで結果を区別する。
    """
    if _is_circuit_open("ハードオフ"):
        return None
    return _run_worker(_HARDOFF_WORKER, [jan_code], "ハードオフ", timeout=30)


def search_dospara(jan_code: str, product_name: str = "") -> dict | None:
    """ドスパラ（PC専門）で商品名検索

    ドスパラはJAN検索をサポートしないため、商品名が必須。
    商品名が空の場合はスキップ。
    """
    if _is_circuit_open("ドスパラ"):
        return None
    if not product_name:
        return None
    return _run_worker(_DOSPARA_WORKER, [jan_code, product_name], "ドスパラ", timeout=30)


def search_tsukumo(jan_code: str, product_name: str = "") -> dict | None:
    """ツクモ（PC専門）でJAN検索

    /goods/{JAN}/ 直URL方式。JAN一致保証。
    """
    if _is_circuit_open("ツクモ"):
        return None
    return _run_worker(_TSUKUMO_WORKER, [jan_code], "ツクモ", timeout=20)


def search_pc_koubou(jan_code: str, product_name: str = "") -> dict | None:
    """パソコン工房（PC専門）でJAN検索（一時無効化中）"""
    if _is_circuit_open("パソコン工房"):
        return None
    return _run_worker(_PC_KOUBOU_WORKER, [jan_code], "パソコン工房", timeout=30)


def search_mapcamera(jan_code: str, product_name: str = "") -> dict | None:
    """マップカメラ（カメラ専門、新品のみ、Firefox使用）でJAN検索（一時無効化中）"""
    if _is_circuit_open("マップカメラ"):
        return None
    return _run_worker(_MAPCAMERA_WORKER, [jan_code, product_name or ""], "マップカメラ", timeout=45)


def search_kitamura(jan_code: str, product_name: str = "") -> dict | None:
    """カメラのキタムラ（カメラ専門）でJAN検索"""
    if _is_circuit_open("キタムラ"):
        return None
    return _run_worker(_KITAMURA_WORKER, [jan_code], "キタムラ", timeout=30)


def search_suruga_ya_new(jan_code: str, product_name: str = "") -> dict | None:
    """駿河屋（新品のみ、中古厳格除外）でJAN検索

    JAN検索の検索結果カードから「新品：￥XXX」マーカーのみ抽出。
    中古品・品切れ・ジャンク品は全て null を返す。
    新品在庫は品切れ率が高いためヒット率は低めだが、誤検出ゼロ設計。
    """
    if _is_circuit_open("駿河屋"):
        return None
    return _run_worker(_SURUGA_YA_NEW_WORKER, [jan_code], "駿河屋", timeout=25)


def search_soundhouse(jan_code: str, product_name: str = "") -> dict | None:
    """サウンドハウス（楽器・PA機器・オーディオ）でJAN検索"""
    if _is_circuit_open("サウンドハウス"):
        return None
    return _run_worker(_SOUNDHOUSE_WORKER, [jan_code], "サウンドハウス", timeout=40)


def search_e_earphone(jan_code: str, product_name: str = "") -> dict | None:
    """e☆イヤホン（イヤホン・ヘッドホン、新品のみ）でJAN検索"""
    if _is_circuit_open("e☆イヤホン"):
        return None
    return _run_worker(_E_EARPHONE_WORKER, [jan_code], "e☆イヤホン", timeout=40)


def search_murauchi(jan_code: str, product_name: str = "") -> dict | None:
    """ムラウチドットコム（家電）でJAN検索"""
    if _is_circuit_open("ムラウチ"):
        return None
    return _run_worker(_MURAUCHI_WORKER, [jan_code], "ムラウチ", timeout=40)


# --- 全スクレイパー一覧 ---
# ビックカメラ/ジョーシン/ノジマ/ケーズデンキ/ソフマップ/エディオン/コジマ は
# CDP/Playwright いずれでも100%失敗するため含めない。
# Chrome拡張の自動巡回（auto_extract.py → price_server.py → background.js）で対応。

# 通常の買取店向け利益判定で使うスクレイパー（新品のみ）
# ハードオフは中古特化のため AVAILABLE_SCRAPERS には含めず、
# `mercari_resale_finder.py` から `search_hardoff` を直接呼び出す。
AVAILABLE_SCRAPERS = {
    "Amazon": search_amazon,
    "ヨドバシ": search_yodobashi,
    "価格.com": search_kakaku,
    "Qoo10": search_qoo10,
    "ツクモ": search_tsukumo,  # JAN直URL方式、実機検証済み（RTX5090 正、ポケカ null）
    "駿河屋": search_suruga_ya_new,  # 新品のみ、「新品：」マーカー存在確認、中古厳格除外
    # 以下は一時無効化（誤検出リスクあり、またはanti-bot）
    # "ドスパラ": search_dospara,          # GPU単体 vs PC本体（GALLERIA）の価格桁違い誤マッチ懸念
    # "サウンドハウス": search_soundhouse,  # HTTP2エラー、requestsもタイムアウト（anti-bot極強）
    # "e☆イヤホン": search_e_earphone,     # SPA挙動でURLパラメータ検索が機能しない
    # "ムラウチ": search_murauchi,          # Human Verification CAPTCHA
    # "パソコン工房": search_pc_koubou,
    # "マップカメラ": search_mapcamera,
    # "キタムラ": search_kitamura,
}
