"""PC 사양 감지 — 어떤 모델을 권할지 정하기 위한 최소한의 정보만 본다 (5주차).

왜 필요한가: 같은 모델도 GPU가 있으면 4.3초, CPU만 있으면 81초가 걸린다
(3주차 실측, ADR-0002 §5). 사용자가 자기 PC에 안 맞는 모델을 골라 받으면
6GB를 내려받고도 못 쓰게 된다. 그래서 받기 **전에** 판단 근거를 준다.

외부 라이브러리를 쓰지 않는다 — 배포본 크기를 키우지 않기 위해 표준 라이브러리와
OS 기본 도구(nvidia-smi)만 쓴다. 감지에 실패하면 조용히 "모름"으로 두고,
그 경우에는 안전한 쪽(경량 모델)을 권한다.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess


def _total_ram_gb() -> float:
    """설치된 물리 메모리(GB). 알 수 없으면 0."""
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.ullTotalPhys / 1024 ** 3, 1)

        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if pages > 0:
                return round(pages * page_size / 1024 ** 3, 1)
    except Exception:
        pass
    return 0.0


def _gpu() -> tuple[str, float]:
    """(GPU 이름, VRAM GB). 없거나 못 찾으면 ("", 0)."""
    if not shutil.which("nvidia-smi"):
        return "", 0.0
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except Exception:
        return "", 0.0

    first = output.splitlines()[0] if output else ""
    if "," not in first:
        return "", 0.0
    name, _, memory = first.partition(",")
    try:
        return name.strip(), round(float(memory.strip()) / 1024, 1)
    except ValueError:
        return name.strip(), 0.0


def detect() -> dict:
    """이 PC의 사양 요약. 실패한 항목은 0이나 빈 문자열로 남는다."""
    gpu_name, vram_gb = _gpu()
    return {
        "os": f"{platform.system()} {platform.release()}".strip(),
        "cpu_cores": os.cpu_count() or 0,
        "ram_gb": _total_ram_gb(),
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        # 이 값이 모델 추천을 가른다. GPU 없이 7.8b를 돌리면 파일당 81초라
        # 사실상 못 쓴다 (3주차 실측).
        "has_usable_gpu": vram_gb >= 6.0,
    }


def summary(hardware: dict) -> str:
    """화면에 한 줄로 보여 줄 사양 설명."""
    parts = []
    if hardware.get("gpu_name"):
        vram = hardware.get("vram_gb") or 0
        parts.append(f"{hardware['gpu_name']}" + (f" ({vram:g}GB)" if vram else ""))
    else:
        parts.append("그래픽카드 없음")
    if hardware.get("ram_gb"):
        parts.append(f"메모리 {hardware['ram_gb']:g}GB")
    return " · ".join(parts)
