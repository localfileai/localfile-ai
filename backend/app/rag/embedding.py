"""Ollama 임베딩 어댑터.

BE1이 `scripts/embed_dataset.py`에서 쓴 것과 **같은 모델·같은 방식**이다.
색인과 검색이 다른 임베딩을 쓰면 거리 계산이 의미를 잃으므로 반드시 일치해야 한다.

실험 스크립트(`scripts/`)를 `app/`에서 import하지 않는 규칙이 있어
(프로덕션이 탐색용 코드에 의존하지 않도록) 어댑터를 이쪽에 따로 둔다.
"""

from __future__ import annotations

import os

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

# BE1 1주차 선정 모델. ADR-0002 참고.
# 영어 전용 기본값(all-MiniLM-L6-v2)은 한국어에서 거리 변별이 되지 않는다.
DEFAULT_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 색인 시 컬렉션 이름. `scripts/embed_dataset.py`의 COLLECTION_NAME과 같아야 한다.
COLLECTION_NAME = os.getenv("LOCAL_FILE_AI_COLLECTION", "file_documents")


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Ollama의 다국어 임베딩 모델을 ChromaDB에 물리는 어댑터."""

    def __init__(self, model: str = DEFAULT_EMBED_MODEL, timeout: int = 600) -> None:
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        # ChromaDB가 컬렉션 메타데이터에 저장한다. 색인/검색이 같아야 한다.
        return f"ollama-{self._model}"

    def __call__(self, input: Documents) -> Embeddings:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": self._model, "input": list(input)},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["embeddings"]


def check_ollama(model: str = DEFAULT_EMBED_MODEL) -> tuple[bool, str]:
    """Ollama 서버와 모델이 준비됐는지 확인한다. (준비됨, 안내문)"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
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
