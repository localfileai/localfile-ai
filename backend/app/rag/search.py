"""자연어 유사도 검색 (BE1 기능①).

`scripts/embed_dataset.py`가 만든 ChromaDB 컬렉션을 읽어 질의와 가까운 문서를 찾는다.
응답은 BE1의 팀 공용 계약 `app/contracts/ai.py`의 `SearchResponse`로 검증한다.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

import chromadb

from ..contracts.ai import ALLOWED_EXTENSIONS, FileRef, SearchHit, SearchResponse
from .embedding import COLLECTION_NAME, OllamaEmbeddingFunction, check_ollama

# BE1 스크립트의 기본 저장 위치(`--db ./chroma_db`)와 같아야 한다.
# server.exe로 패키징되면 실행 파일 옆 폴더가 된다 — config.BASE_DIR 참고.
from ..core.config import BASE_DIR as BACKEND_ROOT  # noqa: E402
CHROMA_PATH = Path(os.getenv("LOCAL_FILE_AI_CHROMA", BACKEND_ROOT / "chroma_db"))
# 색인된 상대 경로(`files\...`)의 기준 폴더.
DATASET_ROOT = Path(os.getenv("LOCAL_FILE_AI_DATASET", BACKEND_ROOT / "dataset"))

# matched_text 상한. 계약이 500자까지 허용한다.
MAX_MATCHED_TEXT = 500


class SearchUnavailable(RuntimeError):
    """색인이나 Ollama가 준비되지 않은 상태. 사용자에게 이유를 그대로 보여 준다."""


def _chroma_path_for_client() -> str:
    """ChromaDB에 넘길 경로 문자열.

    ⚠️ **경로에 비ASCII 문자(한글 등)가 있으면 절대 경로를 쓸 수 없습니다.**
    ChromaDB 1.5.x의 Rust HNSW 리더가 그 경로를 열지 못하고 이렇게 실패합니다.

        Error constructing hnsw segment reader: Error loading hnsw index

    같은 색인을 **상대 경로**로 열면 정상 동작합니다. 이 프로젝트 폴더 이름에
    한글이 들어갈 수 있으므로(`...\\1주차-결과물\\...`) 가능하면 상대 경로를 씁니다.

    참고: 이 우회는 프로세스의 현재 작업 디렉터리가 `backend/`라는 가정에 의존합니다.
    `uvicorn main:app` 을 `backend/`에서 실행하므로 성립합니다.
    """
    absolute = str(CHROMA_PATH)
    if not any(ord(char) > 127 for char in absolute):
        return absolute

    try:
        relative = CHROMA_PATH.relative_to(Path.cwd())
        return str(relative)
    except ValueError:
        # cwd 기준 상대 경로로 만들 수 없으면 절대 경로로 시도한다(실패할 수 있음).
        return absolute


# 사용자 폴더 색인이 저장되는 컬렉션. 합성 데이터셋(COLLECTION_NAME)과 분리한다 —
# 검색 결과에 합성 문서가 섞이면 안 되고, RAG 추천 예시는 반대로 합성 관례가 필요하다.
USER_COLLECTION_NAME = os.getenv("LOCAL_FILE_AI_USER_COLLECTION", "user_documents")

# 사용자가 승인·수정한 분류 결과(피드백)가 라벨 예시로 쌓이는 컬렉션.
# 분류(classify.py)가 라벨 정의문보다 이것을 우선 참조한다 — 쓸수록 맞춤화.
FEEDBACK_COLLECTION_NAME = os.getenv("LOCAL_FILE_AI_FEEDBACK_COLLECTION", "user_examples")

# ChromaDB는 같은 저장 경로에 대해 **클라이언트를 하나만** 두어야 한다.
# 요청마다 PersistentClient를 새로 만들면 HNSW 세그먼트를 중복으로 열게 되고
# "Error loading hnsw index" 로 실패한다. 그래서 프로세스당 한 번만 만들어 캐시한다.
_client_cache = None
_collection_cache = None
_user_collection_cache = None
_feedback_collection_cache = None
# _collection()이 락 안에서 _chroma_client()를 다시 부르므로 재진입 락이어야 한다.
_collection_lock = threading.RLock()


def _chroma_client():
    """공유 PersistentClient. 색인기(indexer)와 검색이 같은 것을 써야 한다."""
    global _client_cache
    if _client_cache is None:
        with _collection_lock:
            if _client_cache is None:
                _client_cache = chromadb.PersistentClient(path=_chroma_path_for_client())
    return _client_cache


def _collection():
    """합성 데이터셋 컬렉션 (RAG 추천 예시·시연용)."""
    global _collection_cache

    if _collection_cache is not None:
        return _collection_cache

    with _collection_lock:
        # 락을 기다리는 동안 다른 스레드가 먼저 만들었을 수 있다.
        if _collection_cache is not None:
            return _collection_cache

        ready, message = check_ollama()
        if not ready:
            raise SearchUnavailable(message)

        try:
            # 실패는 캐시하지 않는다. 색인이 나중에 준비되면 다시 시도할 수 있어야 한다.
            _collection_cache = _chroma_client().get_collection(
                COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction()
            )
        except Exception as exc:
            raise SearchUnavailable(
                "아직 검색할 문서가 없습니다. "
                "[폴더 선택]으로 정리할 폴더를 고르면 문서를 읽어 검색을 준비합니다."
            ) from exc

    return _collection_cache


def user_collection(create: bool = False):
    """사용자 폴더 색인 컬렉션. 없으면 None (create=True면 만들어서 반환).

    색인기(rag/indexer.py)는 create=True로, 검색은 create=False로 부른다.
    """
    global _user_collection_cache

    if _user_collection_cache is not None:
        return _user_collection_cache

    with _collection_lock:
        if _user_collection_cache is not None:
            return _user_collection_cache
        try:
            if create:
                _user_collection_cache = _chroma_client().get_or_create_collection(
                    USER_COLLECTION_NAME,
                    embedding_function=OllamaEmbeddingFunction(),
                    metadata={"hnsw:space": "cosine"},
                )
            else:
                _user_collection_cache = _chroma_client().get_collection(
                    USER_COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction())
        except Exception:
            return None

    return _user_collection_cache


def _resolve_path(relative_path: str, *, user_file: bool = False) -> Path:
    """색인 메타데이터의 경로를 실제 파일 경로로 바꾼다.

    합성 데이터셋은 `files\\...` 상대 경로, 사용자 색인은 절대 경로를 저장한다.
    """
    if user_file:
        return Path(relative_path)
    # 생성기가 Windows 구분자로 저장하므로 양쪽 다 받아 준다.
    normalized = relative_path.replace("\\", "/")
    return DATASET_ROOT / normalized


def _to_file_ref(metadata: dict) -> FileRef | None:
    """색인 메타데이터를 BE1 계약의 FileRef로 바꾼다.

    계약이 MVP 범위 밖 확장자를 거부하므로, 범위 밖이면 None을 돌려 건너뛴다.
    """
    extension = str(metadata.get("extension", "")).lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        return None

    relative_path = str(metadata.get("current_path", ""))
    absolute = _resolve_path(relative_path, user_file=metadata.get("source") == "user")

    size_bytes = 0
    modified_at: datetime | None = None
    if absolute.is_file():
        stat = absolute.stat()
        size_bytes = stat.st_size
        modified_at = datetime.fromtimestamp(stat.st_mtime)

    return FileRef(
        # FE가 그대로 미리보기 API에 넘길 수 있도록 절대 경로를 준다.
        path=str(absolute),
        name=str(metadata.get("current_name", absolute.name)),
        extension=extension,
        size_bytes=size_bytes,
        modified_at=modified_at,
    )


def _to_score(distance: float) -> float:
    """코사인 거리를 0~1 관련도로 바꾼다. 계약이 이 범위를 강제한다."""
    return max(0.0, min(1.0, 1.0 - float(distance)))


def feedback_collection(create: bool = False):
    """사용자 피드백 예시 컬렉션. 없으면 None (create=True면 만들어서 반환)."""
    global _feedback_collection_cache

    if _feedback_collection_cache is not None:
        return _feedback_collection_cache

    with _collection_lock:
        if _feedback_collection_cache is not None:
            return _feedback_collection_cache
        try:
            if create:
                _feedback_collection_cache = _chroma_client().get_or_create_collection(
                    FEEDBACK_COLLECTION_NAME,
                    embedding_function=OllamaEmbeddingFunction(),
                    metadata={"hnsw:space": "cosine"},
                )
            else:
                _feedback_collection_cache = _chroma_client().get_collection(
                    FEEDBACK_COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction())
        except Exception:
            return None

    return _feedback_collection_cache


def _active_collection():
    """검색 대상 컬렉션을 고른다. 사용자 색인이 있으면 그것을, 없으면 합성 색인을.

    (사용자가 자기 폴더를 색인한 순간부터 검색은 진짜 파일을 대상으로 동작한다.
    합성 색인은 RAG 추천 예시와 시연용으로만 남는다.)
    """
    user = user_collection()
    if user is not None:
        try:
            if user.count() > 0:
                return user, "user"
        except Exception:
            pass
    return _collection(), "dataset"


def search(query: str, top_k: int = 5) -> SearchResponse:
    """자연어 질의로 색인된 문서를 찾는다."""
    started = time.perf_counter()

    ready, message = check_ollama()
    if not ready:
        raise SearchUnavailable(message)

    collection, _source = _active_collection()

    if collection.count() == 0:
        raise SearchUnavailable(
            "아직 검색할 문서가 없습니다. [폴더 선택]으로 정리할 폴더를 고르면 "
            "문서를 읽어 검색을 준비합니다."
        )

    # 계약 밖 확장자가 섞여 있을 수 있으니 조금 더 받아서 걸러낸다.
    result = collection.query(query_texts=[query], n_results=min(top_k * 2, 20))

    metadatas = result.get("metadatas", [[]])[0]
    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]

    hits: list[SearchHit] = []
    for metadata, document, distance in zip(metadatas, documents, distances):
        file_ref = _to_file_ref(dict(metadata or {}))
        if file_ref is None:
            continue

        matched_text = (document or "").strip()[:MAX_MATCHED_TEXT]
        if not matched_text:
            # 계약이 빈 문자열을 거부한다. 본문이 없으면 파일명이라도 넣는다.
            matched_text = file_ref.name

        hits.append(SearchHit(file=file_ref, score=_to_score(distance), matched_text=matched_text))
        if len(hits) >= top_k:
            break

    # 계약이 관련도 내림차순을 강제한다. Chroma는 거리 오름차순으로 주므로 이미 맞지만
    # 필터링 뒤 순서를 확실히 보장한다.
    hits.sort(key=lambda hit: hit.score, reverse=True)

    return SearchResponse(
        query=query,
        total_hits=len(hits),
        hits=hits,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


def index_status() -> dict:
    """색인 상태를 알려 준다. FE가 왜 검색이 안 되는지 표시할 때 쓴다.

    검색과 **같은 캐시된 컬렉션**을 쓴다. 여기서 클라이언트를 따로 만들면
    같은 경로를 두 번 여는 셈이 되어 HNSW 로드가 깨진다.
    """
    dataset_count = 0
    user_count = 0
    detail = ""

    user = user_collection()
    if user is not None:
        try:
            user_count = user.count()
        except Exception:
            pass

    try:
        dataset_count = _collection().count()
    except SearchUnavailable as exc:
        if user_count == 0:
            detail = str(exc)
    except Exception as exc:  # 예상 밖의 오류도 화면에 이유를 보여 준다.
        detail = f"색인 상태를 확인할 수 없습니다: {exc}"

    total = user_count + dataset_count
    if total == 0 and not detail:
        detail = ("아직 검색할 문서가 없습니다. [폴더 선택]으로 정리할 폴더를 고르면 "
                  "문서를 읽어 검색을 준비합니다.")

    return {
        "ready": total > 0,
        "indexed_documents": user_count if user_count else dataset_count,
        # 검색이 실제로 보는 소스. 사용자 색인이 생기면 user로 바뀐다.
        "source": "user" if user_count else "dataset",
        "user_documents": user_count,
        "dataset_documents": dataset_count,
        "embed_model": OllamaEmbeddingFunction().name(),
        "detail": detail,
    }
