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

import time as _time

_failure_counts: dict[str, int] = {}
_failure_timestamps: dict[str, float] = {}
CIRCUIT_BREAKER_THRESHOLD = 2   # 2回連続失敗でサーキットオープン（OOM連鎖を早期検知）
CIRCUIT_BREAKER_COOLDOWN = 300  # 5分


def _is_circuit_open(source: str) -> bool:
    count = _failure_counts.get(source, 0)
    if count < CIRCUIT_BREAKER_THRESHOLD:
        return False
    # クールダウン経過後に自動リセット
    last_fail = _failure_timestamps.get(source, 0)
    if _time.time() - last_fail >= CIRCUIT_BREAKER_COOLDOWN:
        _failure_counts[source] = 0
        logger.info("%s: サーキットブレーカーリセット（%d秒経過）", source, CIRCUIT_BREAKER_COOLDOWN)
        return False
    return True


def _record_failure(source: str):
    _failure_counts[source] = _failure_counts.get(source, 0) + 1
    _failure_timestamps[source] = _time.time()
    if _failure_counts[source] >= CIRCUIT_BREAKER_THRESHOLD:
        logger.warning("%s: サーキットブレーカー発動（%d回連続失敗、%d秒後にリセット）",
                       source, CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN)


def _record_success(source: str):
    _failure_counts[source] = 0


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
    return _run_worker(_YODOBASHI_WORKER, [product_name], "ヨドバシ", timeout=45)


def search_kakaku(jan_code: str, product_name: str = "") -> list[dict] | dict | None:
    """価格.comで複数ショップの価格を取得し、実店舗ページで検証する。

    Returns:
        検証成功した結果のリスト（最大3件）、または後方互換のためdict/None。
    """
    if _is_circuit_open("価格.com"):
        return None
    result = _run_worker(_KAKAKU_WORKER, [jan_code], "価格.com", timeout=60)
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
    return _run_worker(_VERIFY_WORKER, args, "検証", timeout=30)


def close_browser():
    """互換性のためのスタブ（サブプロセス方式では不要）"""
    pass


def search_qoo10(jan_code: str, product_name: str = "") -> dict | None:
    """Qoo10でJAN検索し、最安値を返す"""
    if _is_circuit_open("Qoo10"):
        return None
    return _run_worker(_QOO10_WORKER, [jan_code], "Qoo10", timeout=45)


# --- 全スクレイパー一覧 ---
# ビックカメラ/ジョーシン/ノジマ/ケーズデンキ/ソフマップ/エディオン/コジマ は
# CDP/Playwright いずれでも100%失敗するため含めない。
# Chrome拡張の自動巡回（auto_extract.py → price_server.py → background.js）で対応。

AVAILABLE_SCRAPERS = {
    "Amazon": search_amazon,
    "ヨドバシ": search_yodobashi,
    "価格.com": search_kakaku,
    "Qoo10": search_qoo10,
}
