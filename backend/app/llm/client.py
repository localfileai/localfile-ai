"""Ollama 생성(generate) 클라이언트.

임베딩 어댑터(`rag/embedding.py`)와 같은 이유로 커넥션을 재사용하고
`keep_alive`를 보낸다 — 요청당 고정 오버헤드가 지연의 대부분이다 (ADR-0002 §5).
"""

from __future__ import annotations

import requests

from ..core import config

_session = requests.Session()


class LLMUnavailable(RuntimeError):
    """Ollama 서버나 생성 모델이 준비되지 않았다. 사용자에게 이유를 그대로 보여 준다."""


class LLMRequestError(RuntimeError):
    """호출 자체가 실패했다 (타임아웃, 연결 끊김 등). 파일 단위로 실패 처리한다."""


def check_generate_model(model: str = config.OLLAMA_GENERATE_MODEL) -> tuple[bool, str]:
    """Ollama 서버와 생성 모델이 준비됐는지 확인한다. (준비됨, 안내문)"""
    try:
        response = _session.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return False, (
            f"Ollama 서버에 연결할 수 없습니다 ({config.OLLAMA_BASE_URL}). "
            "`ollama serve` 로 서버를 띄우세요."
        )

    installed = {m["name"] for m in response.json().get("models", [])}
    tag = model if ":" in model else f"{model}:latest"
    if tag not in installed:
        return False, f"생성 모델이 없습니다: {model}. `ollama pull {model}` 로 받으세요."

    return True, ""


def probe_generation_seconds(model: str = config.OLLAMA_GENERATE_MODEL,
                             tokens: int = 16, timeout: int = 300) -> float:
    """워밍업 후 `tokens`개 생성에 걸리는 시간을 잰다 (auto 모드의 저사양 판정용).

    첫 호출은 모델 로딩이 섞이므로 버리고 두 번째 호출을 측정한다.
    """
    import time

    payload = {
        "model": model,
        "prompt": "다음 단어를 이어서 쓰세요: 가나다",
        "stream": False,
        "options": {"num_predict": tokens, "temperature": 0.0},
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
    }
    try:
        _session.post(f"{config.OLLAMA_BASE_URL}/api/generate",
                      json=payload, timeout=timeout).raise_for_status()  # 워밍업
        started = time.perf_counter()
        response = _session.post(f"{config.OLLAMA_BASE_URL}/api/generate",
                                 json=payload, timeout=timeout)
        response.raise_for_status()
        return time.perf_counter() - started
    except requests.exceptions.RequestException as exc:
        raise LLMRequestError(f"probe_error: {type(exc).__name__}") from exc


def generate(
    system: str,
    prompt: str,
    *,
    model: str = config.OLLAMA_GENERATE_MODEL,
    timeout: int = config.GENERATE_TIMEOUT_SEC,
) -> str:
    """JSON 형식을 강제해 한 번 생성한다. 실패는 LLMRequestError로 올린다."""
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        # 실험(test_models.py)과 같은 조건이어야 ADR-0002 수치와 비교할 수 있다.
        "format": "json",
        "stream": False,
        "options": {"temperature": config.GENERATE_TEMPERATURE},
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
    }
    try:
        response = _session.post(
            f"{config.OLLAMA_BASE_URL}/api/generate", json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise LLMRequestError(f"timeout({timeout}s)") from exc
    except requests.exceptions.RequestException as exc:
        raise LLMRequestError(f"request_error: {type(exc).__name__}") from exc

    return response.json().get("response", "")
