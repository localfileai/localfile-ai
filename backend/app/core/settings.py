"""사용자가 고른 설정 — 앱이 껐다 켜도 유지된다 (5주차).

`config.py`는 개발자가 정한 **기본값**의 단일 출처다. 여기는 그 위에 얹히는
**사용자 선택**을 담는다. 지금은 파일명 추천에 쓸 LLM 하나뿐이다.

왜 나눴나: 첫 실행 화면에서 사용자가 자기 PC에 맞는 모델을 고르는데, 그 선택이
환경 변수로만 바뀔 수 있으면 앱을 다시 켤 때마다 기본값으로 돌아간다.
"""

from __future__ import annotations

import json
import threading

from . import config

_lock = threading.Lock()
_cache: dict | None = None


def _path():
    return config.BASE_DIR / "settings.json"


def _load() -> dict:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                try:
                    _cache = json.loads(_path().read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    _cache = {}
    return _cache


def generate_model() -> str:
    """파일명 추천에 쓸 LLM. 사용자가 고른 값이 없으면 개발 기본값."""
    chosen = str(_load().get("generate_model", "")).strip()
    return chosen or config.OLLAMA_GENERATE_MODEL


def set_generate_model(name: str) -> None:
    global _cache
    with _lock:
        data = dict(_cache or {})
        data["generate_model"] = name
        try:
            _path().write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        except OSError:
            pass  # 저장 실패해도 이번 실행 동안은 적용된다
        _cache = data
