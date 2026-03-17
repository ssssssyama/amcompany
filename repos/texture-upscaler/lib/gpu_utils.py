"""GPU検出ユーティリティ — NVIDIA / AMD (ROCm) / CPU 自動判別"""

import torch


def detect_gpu() -> dict:
    """GPUの種類を検出して情報を返す

    Returns:
        dict: {
            "available": bool,  # GPU が利用可能か
            "name": str,        # GPU名（例: "AMD Radeon RX 7900 XTX"）
            "is_amd": bool,     # AMD GPU か
        }
    """
    info = {"available": False, "name": "", "is_amd": False}
    if torch.cuda.is_available():
        info["available"] = True
        try:
            info["name"] = torch.cuda.get_device_name(0)
            info["is_amd"] = any(
                kw in info["name"].lower() for kw in ("amd", "radeon", "gfx")
            )
        except Exception:
            info["name"] = "不明なGPU"
    return info


def resolve_device(requested: str = "cuda") -> tuple[str, dict]:
    """要求されたデバイスを検証し、利用可能なデバイスを返す

    Args:
        requested: "cuda" or "cpu"

    Returns:
        (device_str, gpu_info): 実際に使うデバイス名とGPU情報
    """
    gpu_info = detect_gpu()

    if requested == "cuda":
        if not gpu_info["available"]:
            print("警告: GPUが利用できません。CPUモードで実行します（非常に遅くなります）")
            return "cpu", gpu_info
        print(f"検出されたGPU: {gpu_info['name']}")
        if gpu_info["is_amd"]:
            print("AMD GPUを検出しました（ROCm経由）")
        return "cuda", gpu_info

    return "cpu", gpu_info
