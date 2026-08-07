"""자연어 유사도 검색 (BE1 기능①).

`scripts/embed_dataset.py`가 만든 ChromaDB 컬렉션을 읽어 질의와 가까운 문서를 찾는다.
응답은 BE1의 팀 공용 계약 `app/contracts/ai.py`의 `SearchResponse`로 검증한다.

5주차 개편 — **하이브리드 검색**. 벡터 유사도 순서를 그대로 내보내던 방식의
실패가 실사용에서 두 가지로 드러났다.
  - "공모전 자료"를 찾는데 파일명에 "공모전"이 없는 문서는 못 찾았다.
    파일명 대조가 이름만 봤고, 벡터 순위만으로는 변별력이 부족했다.
  - 관련 문서가 1~2개뿐이어도 top_k를 채우느라 무관한 파일이 딸려 나왔다.
그래서 세 신호(키워드·벡터·최신성)를 결합하고, 키워드가 전혀 안 맞는 후보는
벡터 유사도가 절대·상대 기준을 둘 다 넘을 때만 남긴다. 질의는 문서와 다르게
임베딩한다(embedding.embed_query — 검색 지시문). "최근 …" 질의는 파일 수정
시각을 실제 랭킹 요인으로 쓴다.
"""

from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import chromadb

from ..contracts.ai import ALLOWED_EXTENSIONS, FileRef, SearchHit, SearchResponse
from ..core import config, settings as embedding_settings
from .embedding import (COLLECTION_NAME, OllamaEmbeddingFunction, check_ollama,
                        embed_query)

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


def _embed_model_of(collection) -> str:
    """이 컬렉션이 어떤 임베딩 모델로 만들어졌는가.

    옛 색인에는 기록이 없다. 그때는 개발 기본값으로 만들어졌다고 본다.
    """
    metadata = getattr(collection, "metadata", None) or {}
    return str(metadata.get("embed_model") or config.OLLAMA_EMBED_MODEL)


def user_collection(create: bool = False):
    """사용자 폴더 색인 컬렉션. 없으면 None (create=True면 만들어서 반환).

    색인기(rag/indexer.py)는 create=True로, 검색은 create=False로 부른다.

    임베딩 모델이 바뀌었으면 **버리고 새로 만든다.** 모델이 다르면 벡터 차원과
    좌표계가 달라, 섞인 색인에서는 거리 계산이 아무 의미가 없다. 예비 모델로
    갈아타는 경우가 여기 해당한다.
    """
    global _user_collection_cache

    if _user_collection_cache is not None:
        return _user_collection_cache

    with _collection_lock:
        if _user_collection_cache is not None:
            return _user_collection_cache

        embed_model = embedding_settings.embed_model()

        if not create:
            try:
                collection = _chroma_client().get_collection(
                    USER_COLLECTION_NAME, embedding_function=OllamaEmbeddingFunction())
            except Exception:
                return None
            # 모델이 다른 옛 색인으로 검색하면 거리 계산이 의미를 잃는다.
            # 색인기가 다시 만들 때까지 없는 것으로 친다.
            if _embed_model_of(collection) != embed_model:
                return None
            _user_collection_cache = collection
            return _user_collection_cache

        def make():
            return _chroma_client().get_or_create_collection(
                USER_COLLECTION_NAME,
                embedding_function=OllamaEmbeddingFunction(),
                metadata={"hnsw:space": "cosine", "embed_model": embed_model},
            )

        try:
            collection = make()
            if _embed_model_of(collection) != embed_model:
                raise RuntimeError("embed model changed")
        except Exception:
            # 임베딩 모델이 바뀌었거나, 옛 컬렉션이 지금 임베딩 함수를 거부한다.
            # 어느 쪽이든 그 색인은 더 못 쓴다 — 버리고 새로 만든다.
            try:
                _chroma_client().delete_collection(USER_COLLECTION_NAME)
                collection = make()
            except Exception:
                return None

        _user_collection_cache = collection
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


def _is_under(file_path: str, root: str) -> bool:
    """파일이 그 폴더(하위 폴더 포함) 안에 있는가. 경로 표기 차이를 흡수한다."""
    def canonical(value: str) -> str:
        text = str(Path(value).expanduser()).replace("\\", "/").rstrip("/")
        # Windows 경로는 대소문자를 구분하지 않는다.
        return text.lower() if os.name == "nt" else text

    target, base = canonical(file_path), canonical(root)
    return target == base or target.startswith(base + "/")


# =========================================================================
# 질의 해석 — 군말을 걷어내고 내용 키워드와 "최근" 의도를 뽑는다.
# =========================================================================

# 파일명을 이어 붙일 때 쓰는 구분자. 사람은 "기말_보고서"도 "기말 보고서"로 기억한다.
_NAME_SEPARATORS = str.maketrans({c: " " for c in "_-.()[]{}·,~"})

# 검색 의도만 나타내고 문서 내용과는 무관한 말. 키워드 대조에서 뺀다.
# "공모전 자료 찾아줘"에서 문서를 가리키는 말은 "공모전"뿐이다 — "자료"와
# "찾아줘"까지 똑같이 대조하면 아무 "자료"나 이름에 든 파일이 같이 올라온다.
# ("파일"·"문서"·"자료"는 이 앱에서 모든 대상에 해당하는 말이라 아무것도 구분하지 못한다.)
_STOPWORDS = frozenset({
    "찾아줘", "찾아주라", "찾아봐", "찾아", "찾기", "찾아볼래",
    "검색", "검색해", "검색해줘", "보여줘", "보여주라", "알려줘", "열어줘",
    "관련", "관련된", "대한", "대해",
    "있나", "있어", "있는", "있는지", "있을까", "없나",
    "어디", "어디에", "어딨어", "어딨지", "뭐지", "뭐더라",
    "이거", "그거", "저거", "요거", "나의", "해줘", "주세요",
    "파일", "문서", "자료", "폴더", "파일들", "문서들", "자료들",
})

# "최근 것"을 찾는 시간 표현. 보이면 최신 파일을 위로 올린다. (긴 표현 먼저 지운다.)
_TEMPORAL_WORDS = ("얼마 전", "얼마전", "지난 주", "지난주", "저번주", "이번주",
                   "지난 달", "지난달", "저번달", "이번달",
                   "최근", "최신", "요즘", "오늘", "어제", "그저께", "엊그제")

# 토큰 끝에 붙는 흔한 조사. "공모전에서" → "공모전". 남는 부분이 2자 이상일 때만
# 떼어낸다 — "회의"의 "의"까지 떼면 안 된다.
_PARTICLES = ("에서", "으로", "이랑", "라는", "까지", "부터", "하고",
              "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "들")


def _strip_particle(token: str) -> str:
    for particle in _PARTICLES:
        if token.endswith(particle) and len(token) - len(particle) >= 2:
            return token[: -len(particle)]
    return token


def parse_query(query: str) -> tuple[list[str], bool, str]:
    """질의를 (내용 키워드, "최근" 의도, 임베딩용 문장)으로 해석한다.

    시간 표현은 문서 내용이 아니라 **파일 속성(수정 시각)**에 대한 조건이므로
    키워드·임베딩 양쪽에서 빼고, 대신 최신성 랭킹을 켠다.
    """
    temporal = any(word in query for word in _TEMPORAL_WORDS)
    cleaned = query
    if temporal:
        for word in _TEMPORAL_WORDS:
            cleaned = cleaned.replace(word, " ")
    cleaned = " ".join(cleaned.split())

    tokens: list[str] = []
    for raw in cleaned.translate(_NAME_SEPARATORS).split():
        token = raw.lower()
        if token in _STOPWORDS:
            continue
        token = _strip_particle(token)
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens, temporal, cleaned


# =========================================================================
# 랭킹 — 키워드·벡터·최신성 세 신호의 결합
# =========================================================================


def _squash(text: str) -> str:
    """비교용으로 납작하게. 구분자와 공백을 지우고 소문자로."""
    return "".join(text.translate(_NAME_SEPARATORS).split()).lower()


def _name_score(file_name: str, query: str) -> float:
    """질의가 이 파일명을 얼마나 가리키는가 (0~1).

    임베딩만으로는 "파일명 그대로 붙여넣고 이거 찾아줘"가 잘 안 맞는다. 질의 전체가
    한 문장으로 임베딩되면서 조사·군말이 파일명 신호를 덮기 때문이다. 글자 단위
    비교를 따로 두어, 사용자가 기억하는 이름을 그대로 넣었을 때는 반드시 찾게 한다.
    """
    stem = Path(file_name).stem
    flat_query, flat_stem = _squash(query), _squash(stem)
    if not flat_stem or not flat_query:
        return 0.0

    # 파일명을 통째로 붙여넣은 경우 (군말이 앞뒤에 붙어 있어도 잡힌다).
    if flat_stem in flat_query:
        return 1.0

    # 일부만 기억해 넣은 경우: 이름 토큰 중 질의에 나타난 비율.
    tokens = [t for t in stem.translate(_NAME_SEPARATORS).split() if len(t) >= 2]
    if not tokens:
        return 0.0
    matched = sum(1 for token in tokens if token.lower() in flat_query)
    return matched / len(tokens)


# 키워드 대조 대상 상한. 색인 기본 상한(500건)보다 넉넉히 잡되 무한정 읽지 않는다.
MAX_NAME_SCAN = 3000
# 이 아래는 "우연히 한 글자 겹친" 수준이라 이름 매칭으로 보지 않는다.
NAME_MATCH_THRESHOLD = 0.5

# 결합 가중치 (벡터, 키워드, 최신성). 합이 1이라 결합 점수도 0~1에 머문다.
_WEIGHTS_DEFAULT = (0.55, 0.40, 0.05)
# "최근 …"처럼 시간 의도가 보이면 최신성이 실제 랭킹 요인이 된다.
_WEIGHTS_TEMPORAL = (0.40, 0.32, 0.28)
# 키워드가 하나도 안 맞은 후보(벡터 전용)를 남길 최소 유사도. 이 아래는
# "이 색인에서 제일 덜 먼 것"일 뿐 관련 문서가 아니다.
VECTOR_FLOOR = 0.35
# 최고 후보 대비 상대 컷. 또렷한 관련 문서가 있으면 한참 뒤처진 후보는 버린다 —
# 관련 문서가 1~2개뿐일 때 무관한 파일이 top_k를 채우던 문제의 방지선.
RELATIVE_CUTOFF = 0.75
# 본문에만 나온 키워드는 파일명에 나온 것보다 약한 신호로 본다.
CONTENT_MATCH_WEIGHT = 0.7
# 최신성 반감 척도: 30일 지난 파일의 최신성 신호는 절반이 된다.
RECENCY_HALF_LIFE_DAYS = 30.0


def _lexical_rows(collection) -> list[tuple[str, dict, str]]:
    """색인에서 (id, 메타데이터, 본문)을 상한까지 읽는다. get() 미지원이면 빈 목록."""
    try:
        rows = collection.get(include=["documents", "metadatas"], limit=MAX_NAME_SCAN)
    except Exception:
        return []

    ids = rows.get("ids") or []
    metadatas = rows.get("metadatas") or []
    documents = rows.get("documents") or []

    merged: list[tuple[str, dict, str]] = []
    for position, id_ in enumerate(ids):
        metadata = dict(metadatas[position] or {}) if position < len(metadatas) else {}
        document = str(documents[position] or "") if position < len(documents) else ""
        merged.append((str(id_), metadata, document))
    return merged


def _token_weights(rows: list[tuple[str, dict, str]],
                   tokens: list[str]) -> dict[str, float]:
    """토큰별 가중치(idf). 드문 토큰이 강한 신호다.

    "공모전 발표"에서 "발표"는 절반의 파일에 있지만 "공모전"은 몇 개뿐이다.
    토큰을 똑같이 세면 "발표"만 잔뜩 걸린 파일이 진짜 "공모전" 파일을 밀어낸다.
    """
    total = len(rows)
    weights: dict[str, float] = {}
    for token in tokens:
        appearances = 0
        for _, metadata, document in rows:
            name = _squash(str(metadata.get("current_name", "")))
            if token in name or token in document.lower():
                appearances += 1
        weights[token] = math.log((total + 1) / (appearances + 1)) + 1.0
    return weights


def _keyword_score(metadata: dict, document: str, tokens: list[str],
                   weights: dict[str, float], query: str) -> float:
    """이 문서가 질의 키워드를 얼마나 담고 있는가 (0~1).

    파일명 일치가 본문 일치보다 강하다 — 파일명은 사용자가 붙인 요약이라
    신호가 진하다. 파일명 통째 붙여넣기(_name_score)는 그대로 최상 신호로 남긴다.
    """
    name = str(metadata.get("current_name", ""))
    flat_name = _squash(name)
    lowered = document.lower()

    weight_sum = sum(weights.values())
    matched = 0.0
    for token in tokens:
        if token in flat_name:
            matched += weights[token]
        elif token in lowered:
            matched += weights[token] * CONTENT_MATCH_WEIGHT
    token_score = matched / weight_sum if weight_sum else 0.0

    paste = _name_score(name, query)
    if paste < NAME_MATCH_THRESHOLD:
        paste = 0.0
    return min(1.0, max(token_score, paste))


def _recency_score(metadata: dict, file_ref: FileRef, now: datetime) -> float:
    """최신성(0~1). 30일에 절반으로 줄어든다.

    파일이 그 자리에 있으면 실제 mtime(FileRef.modified_at)을, 없으면 색인 당시
    기록한 mtime_us를 쓴다 — 어느 쪽도 재색인을 요구하지 않는다.
    """
    modified = file_ref.modified_at
    if modified is None:
        mtime_us = metadata.get("mtime_us")
        if isinstance(mtime_us, (int, float)) and mtime_us > 0:
            try:
                modified = datetime.fromtimestamp(mtime_us / 1_000_000)
            except (OverflowError, OSError, ValueError):
                modified = None
    if modified is None:
        return 0.0
    age_days = max(0.0, (now - modified).total_seconds() / 86_400)
    return 1.0 / (1.0 + age_days / RECENCY_HALF_LIFE_DAYS)


def _excerpt(document: str, tokens: list[str]) -> str:
    """결과에 보여 줄 발췌. 키워드가 처음 나온 자리 주변을 자른다.

    앞 500자만 자르면 키워드가 문서 뒤쪽에 있을 때 "왜 이게 걸렸는지"가
    화면에 안 보인다 — 일치한 대목이 보여야 결과를 신뢰할 수 있다.
    """
    text = document.strip()
    lowered = text.lower()
    start = 0
    for token in tokens:
        index = lowered.find(token)
        if index >= 0:
            start = max(0, index - 60)
            break
    return text[start:start + MAX_MATCHED_TEXT].strip()


def search(query: str, top_k: int = 5, root: str = "") -> SearchResponse:
    """자연어 질의로 색인된 문서를 찾는다. (키워드 + 벡터 + 최신성 하이브리드)

    root를 주면 그 폴더에서 색인한 문서만 대상으로 한다. 색인 컬렉션은 하나라
    여러 폴더를 오가며 쓰면 예전 폴더 파일이 결과에 섞이기 때문이다.
    """
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

    tokens, temporal, cleaned = parse_query(query)

    # ① 키워드 후보 — 파일명뿐 아니라 **본문**도 대조한다. 이름에 "공모전"이
    #    없어도 본문에 있으면 찾아야 한다.
    rows = _lexical_rows(collection)
    row_map: dict[str, tuple[dict, str]] = {
        id_: (metadata, document) for id_, metadata, document in rows}

    # ② 벡터 후보 — 질의는 문서와 다르게 임베딩한다(검색 지시문, embed_query).
    #    임베딩이 안 되는 순간(모델 교체 직후 등)에도 키워드 검색은 살아 있어야
    #    하므로, 여기의 실패는 "벡터 신호 없음"으로만 취급하고 계속 간다.
    vector: dict[str, float] = {}
    try:
        query_vector = embed_query(cleaned or query, model=_embed_model_of(collection))
        result = collection.query(query_embeddings=[query_vector],
                                  n_results=min(max(top_k * 5, 50), 200))
    except Exception:
        result = {}

    ids = (result.get("ids") or [[]])[0]
    result_metadatas = (result.get("metadatas") or [[]])[0]
    result_documents = (result.get("documents") or [[]])[0]
    result_distances = (result.get("distances") or [[]])[0]
    for position, metadata in enumerate(result_metadatas):
        metadata = dict(metadata or {})
        # id를 안 주는 컬렉션 구현(테스트 대역 등)은 경로로 대신한다.
        id_ = (str(ids[position]) if position < len(ids)
               else str(metadata.get("current_path") or f"#{position}"))
        document = (str(result_documents[position] or "")
                    if position < len(result_documents) else "")
        distance = (float(result_distances[position])
                    if position < len(result_distances) else 1.0)
        vector[id_] = max(vector.get(id_, 0.0), _to_score(distance))
        row_map.setdefault(id_, (metadata, document))

    all_rows = [(id_, metadata, document)
                for id_, (metadata, document) in row_map.items()]
    weights = _token_weights(all_rows, tokens)

    keyword: dict[str, float] = {}
    for id_, metadata, document in all_rows:
        score = _keyword_score(metadata, document, tokens, weights, query)
        if score > 0:
            keyword[id_] = score

    best_vector = max(vector.values(), default=0.0)
    weight_vector, weight_keyword, weight_recency = (
        _WEIGHTS_TEMPORAL if temporal else _WEIGHTS_DEFAULT)
    now = datetime.now()

    # 경로 기준으로 최고 점수만 남긴다 (사용자 색인은 id=경로라 사실상 1:1).
    ranked: dict[str, tuple[float, FileRef, str]] = {}
    for id_ in set(keyword) | set(vector):
        metadata, document = row_map[id_]
        keyword_part = keyword.get(id_, 0.0)
        vector_part = vector.get(id_, 0.0)

        # 키워드가 전혀 안 맞는 후보는 벡터 유사도가 절대·상대 기준을 둘 다
        # 넘을 때만 관련 문서로 본다. top_k를 채우려고 무관한 파일을 끼워 넣지
        # 않는다 — 결과가 적으면 적은 대로 보여 주는 쪽이 신뢰를 지킨다.
        if keyword_part <= 0.0 and (vector_part < VECTOR_FLOOR
                                    or vector_part < best_vector * RELATIVE_CUTOFF):
            continue

        file_ref = _to_file_ref(metadata)
        if file_ref is None:
            continue
        # 지금 고른 폴더 안의 파일만 남긴다. 문자열 완전 일치가 아니라 실제
        # 경로 포함 관계로 판단한다 — 표기 차이(끝 슬래시·구분자)에 흔들리지 않는다.
        if root and not _is_under(file_ref.path, root):
            continue

        recency = _recency_score(metadata, file_ref, now)
        combined = (weight_vector * vector_part + weight_keyword * keyword_part
                    + weight_recency * recency)
        # 파일명을 통째로 붙여넣었으면 이건 추정이 아니라 확인이다 — 만점.
        if _name_score(file_ref.name, query) >= 1.0:
            combined = 1.0

        known = ranked.get(file_ref.path)
        if known is None or combined > known[0]:
            ranked[file_ref.path] = (combined, file_ref, document)

    ordered = sorted(ranked.values(), key=lambda row: row[0], reverse=True)[:top_k]

    hits: list[SearchHit] = []
    for combined, file_ref, document in ordered:
        matched_text = _excerpt(document, tokens) or file_ref.name
        hits.append(SearchHit(file=file_ref, score=min(1.0, combined),
                              matched_text=matched_text))

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
