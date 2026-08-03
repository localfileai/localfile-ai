"""Ollama 임베딩 어댑터.

BE1이 `scripts/embed_dataset.py`에서 쓴 것과 **같은 모델·같은 방식**이다.
색인과 검색이 다른 임베딩을 쓰면 거리 계산이 의미를 잃으므로 반드시 일치해야 한다.

실험 스크립트(`scripts/`)를 `app/`에서 import하지 않는 규칙이 있어
(프로덕션이 탐색용 코드에 의존하지 않도록) 어댑터를 이쪽에 따로 둔다.

3주차 최적화 (ADR-0002 §5): 질의 지연의 96%가 요청당 고정 오버헤드로 측정됐고,
GPU나 작은 모델로는 줄지 않는다. 실효 대책으로 두 가지를 적용한다.
  - `requests.Session` 재사용: TCP 커넥션을 요청마다 새로 맺지 않는다.
  - `keep_alive`: 요청이 끝나도 모델을 메모리에 유지해 재로딩을 피한다.
"""

from __future__ import annotations

import os

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from ..core import config

# 1주차 bge-m3 → 3주차 qwen3-embedding:0.6b로 개정 (ADR-0002 §2 개정 참고).
# 어려운 평가셋 실측: paraphrase Top-1 90%(bge-m3 70%) · k-NN 89.8% · 크기 절반.
DEFAULT_EMBED_MODEL = config.OLLAMA_EMBED_MODEL
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL

# 색인 시 컬렉션 이름. `scripts/embed_dataset.py`의 COLLECTION_NAME과 같아야 한다.
COLLECTION_NAME = os.getenv("LOCAL_FILE_AI_COLLECTION", "file_documents")

# 프로세스당 한 개의 커넥션 풀을 공유한다. 검색·색인 상태 조회·추천이
# 전부 이 세션을 거치므로 요청마다 커넥션을 다시 맺지 않는다.
_session = requests.Session()


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Ollama의 다국어 임베딩 모델을 ChromaDB에 물리는 어댑터."""

    def __init__(self, model: str = DEFAULT_EMBED_MODEL,
                 timeout: int = config.EMBED_TIMEOUT_SEC) -> None:
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        # ChromaDB가 컬렉션 메타데이터에 저장한다. 색인/검색이 같아야 한다.
        return f"ollama-{self._model}"

    def __call__(self, input: Documents) -> Embeddings:
        response = _session.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={
                "model": self._model,
                "input": list(input),
                # 검색이 뜸한 시간대에도 모델이 내려가지 않게 유지한다.
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["embeddings"]


def check_ollama(model: str = DEFAULT_EMBED_MODEL) -> tuple[bool, str]:
    """Ollama 서버와 모델이 준비됐는지 확인한다. (준비됨, 안내문)"""
    try:
        response = _session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return False, (
            f"Ollama 서버에 연결할 수 없습니다 ({OLLAMA_BASE_URL}). "
            "`ollama serve` 로 서버를 띄우세요."
        )

    installed = {m["name"].split(":")[0] for m in response.json().get("models", [])}
    if model.split(":")[0] not in installed:
        return False, f"임베딩 모델이 없습니다: {model}. `ollama pull {model}` 로 받으세요."

    return True, ""
