"""Ollama 임베딩 어댑터.

BE1이 `scripts/embed_dataset.py`에서 쓴 것과 **같은 모델·같은 방식**이다.
색인과 검색이 다른 임베딩을 쓰면 거리 계산이 의미를 잃으므로 반드시 일치해야 한다.

실험 스크립트(`scripts/`)를 `app/`에서 import하지 않는 규칙이 있어
(프로덕션이 탐색용 코드에 의존하지 않도록) 어댑터를 이쪽에 따로 둔다.

3주차 최적화 (ADR-0002 §5): 질의 지연의 96%가 요청당 고정 오버헤드로 측정됐고,
GPU나 작은 모델로는 줄지 않는다. 실효 대책으로 두 가지를 적용한다.
  - `requests.Session` 재사용: TCP 커넥션을 요청마다 새로 맺지 않는다.
  - `keep_alive`: 요청이 끝나도 모델을 메모리에 유지해 재로딩을 피한다.

5주차 배포 대응: **모델 이름이 목록에 보인다고 그 PC에서 도는 것은 아니다.**
`ollama pull`은 레지스트리에서 파일을 받아 오기만 하므로, 실행기(Ollama)가
낡았거나 메모리가 모자라면 pull은 성공하고 `/api/embed`만 500으로 죽는다.
그래서 이 모듈은 두 가지를 더 한다.
  - 실패 시 Ollama가 보낸 **본문 메시지를 사람 말로 바꿔 올린다** (예전에는
    `raise_for_status()`가 삼켜서 "500 Server Error"만 남았다).
  - 실제로 한 건을 임베딩해 보는 `probe()`와, 안 되면 두루 도는 모델로
    갈아타는 `ensure_usable_model()`.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from ..core import config, settings

# 1주차 bge-m3 → 3주차 qwen3-embedding:0.6b로 개정 (ADR-0002 §2 개정 참고).
# 어려운 평가셋 실측: paraphrase Top-1 90%(bge-m3 70%) · k-NN 89.8% · 크기 절반.
DEFAULT_EMBED_MODEL = config.OLLAMA_EMBED_MODEL
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL

# 색인 시 컬렉션 이름. `scripts/embed_dataset.py`의 COLLECTION_NAME과 같아야 한다.
COLLECTION_NAME = os.getenv("LOCAL_FILE_AI_COLLECTION", "file_documents")

# 프로세스당 한 개의 커넥션 풀을 공유한다. 검색·색인 상태 조회·추천이
# 전부 이 세션을 거치므로 요청마다 커넥션을 다시 맺지 않는다.
_session = requests.Session()


# 실패 원인의 갈래. 화면이 "그래서 뭘 눌러야 하나"를 이 값으로 정한다.
#   runtime — Ollama 설치 자체가 깨졌거나 낡았다. 어떤 모델을 받아도 안 된다.
#             앱이 Ollama를 다시 설치하는 것 말고는 방법이 없다.
#   memory  — 이 PC 메모리로 모델을 못 올린다. 더 작은 모델이면 될 수 있다.
#   missing — 모델 파일이 없다. 받으면 된다.
#   offline — Ollama가 응답하지 않는다.
#   unknown — 나머지. 원문을 그대로 보여 준다.
FAILURE_RUNTIME = "runtime"
FAILURE_MEMORY = "memory"
FAILURE_MISSING = "missing"
FAILURE_OFFLINE = "offline"
FAILURE_UNKNOWN = "unknown"


class EmbeddingUnavailable(RuntimeError):
    """임베딩을 만들 수 없는 상태. 메시지는 그대로 사용자에게 보여 준다."""

    def __init__(self, message: str, kind: str = FAILURE_UNKNOWN) -> None:
        super().__init__(message)
        self.kind = kind


def resolve_model() -> str:
    """지금 쓰는 임베딩 모델. 예비 모델로 갈아탄 적이 있으면 그 값."""
    return settings.embed_model()


# 메모리 부족은 문구가 뚜렷해 먼저 걸러낸다.
_MEMORY_HINTS = ("more system memory", "out of memory", "cudamalloc",
                 "insufficient memory")
# 실행기가 깨졌거나 낡은 경우. "llama-server binary not found"처럼 `not found`가
# 섞여 있어서, 모델 미설치보다 **먼저** 봐야 한다 (예전에는 여기서 오진했다).
_RUNTIME_HINTS = ("llama-server", "llama runner", "runner process",
                  "binary not found", "error starting", "exit status",
                  "unknown model architecture", "unable to load",
                  "unsupported", "does not support", "invalid model",
                  "no such file")


def classify(detail: str) -> str:
    """Ollama가 보낸 오류 원문이 어느 갈래인지."""
    lowered = detail.lower()
    if any(hint in lowered for hint in _MEMORY_HINTS):
        return FAILURE_MEMORY
    if any(hint in lowered for hint in _RUNTIME_HINTS):
        return FAILURE_RUNTIME
    if "not found" in lowered or "no such model" in lowered:
        return FAILURE_MISSING
    return FAILURE_UNKNOWN


def _describe_error(response: requests.Response, model: str) -> tuple[str, str]:
    """Ollama의 오류 응답을 (사람 말, 갈래)로 바꾼다.

    Ollama는 실패 이유를 본문 JSON의 `error`에 담아 준다. 예전에는
    `raise_for_status()`가 상태 코드만 남겨서, 화면에 "500 Server Error"만 뜨고
    정작 원인(메모리 부족인지, 실행기가 깨진 건지)은 아무 데도 안 남았다.
    """
    detail = ""
    try:
        detail = str((response.json() or {}).get("error", "")).strip()
    except ValueError:
        detail = (response.text or "").strip()
    detail = detail[:200]

    kind = classify(detail)
    if kind == FAILURE_MEMORY:
        return (f"이 PC의 메모리가 부족해 검색 모델({model})을 올리지 못했습니다. "
                f"다른 프로그램을 닫고 다시 시도해 주세요. (원문: {detail})"), kind
    if kind == FAILURE_RUNTIME:
        return (f"문서 분석 도구가 이 PC에서 동작하지 않습니다 — 설치가 손상됐거나 "
                f"버전이 낡았습니다. 앱이 자동으로 다시 설치합니다. "
                f"(원문: {detail})"), kind
    if kind == FAILURE_MISSING:
        return (f"검색 모델({model})이 설치되어 있지 않습니다. "
                f"설정에서 모델을 다시 받아 주세요. (원문: {detail})"), kind
    return (f"검색 모델({model})로 문서를 읽지 못했습니다 "
            f"(HTTP {response.status_code}: {detail or '이유 없음'})"), kind


def _embed(model: str, inputs: list[str], timeout: int) -> list[list[float]]:
    """Ollama에 임베딩을 요청한다. 실패하면 이유가 담긴 예외를 올린다."""
    try:
        response = _session.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={
                "model": model,
                "input": inputs,
                # 검색이 뜸한 시간대에도 모델이 내려가지 않게 유지한다.
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
            },
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise EmbeddingUnavailable(
            f"문서 분석 도구에 연결할 수 없습니다: {exc}",
            FAILURE_OFFLINE) from exc

    # 오래된 Ollama에는 묶음 엔드포인트(/api/embed)가 없다. 한 건씩 도는
    # 옛 엔드포인트로 물러선다 — 느리지만 되는 편이 안 되는 것보다 낫다.
    if response.status_code == 404:
        return [_embed_one_legacy(model, text, timeout) for text in inputs]

    if not response.ok:
        raise EmbeddingUnavailable(*_describe_error(response, model))

    vectors = (response.json() or {}).get("embeddings")
    if not vectors:
        raise EmbeddingUnavailable(
            f"검색 모델({model})이 빈 응답을 돌려줬습니다. 문서 분석 도구가 "
            f"손상됐을 수 있습니다 — 앱이 자동으로 다시 설치합니다.",
            FAILURE_RUNTIME)
    return vectors


def _embed_one_legacy(model: str, text: str, timeout: int) -> list[float]:
    """구버전 Ollama의 단건 임베딩 엔드포인트."""
    response = _session.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": model, "prompt": text, "keep_alive": config.OLLAMA_KEEP_ALIVE},
        timeout=timeout,
    )
    if not response.ok:
        raise EmbeddingUnavailable(*_describe_error(response, model))
    vector = (response.json() or {}).get("embedding")
    if not vector:
        raise EmbeddingUnavailable(f"검색 모델({model})이 빈 응답을 돌려줬습니다.",
                                   FAILURE_RUNTIME)
    return vector


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Ollama의 다국어 임베딩 모델을 ChromaDB에 물리는 어댑터."""

    def __init__(self, model: str | None = None,
                 timeout: int = config.EMBED_TIMEOUT_SEC) -> None:
        # 기본값을 import 시점에 굳히지 않는다 — 실행 중에 예비 모델로 갈아탈 수 있다.
        self._model = model or resolve_model()
        self._timeout = timeout

    def name(self) -> str:
        # ChromaDB가 컬렉션 메타데이터에 저장한다. 색인/검색이 같아야 한다.
        return f"ollama-{self._model}"

    def __call__(self, input: Documents) -> Embeddings:
        return _embed(self._model, list(input), self._timeout)


# qwen3-embedding은 질의↔문서 **비대칭** 검색용으로 학습된 모델이다. 모델 카드의
# 권장 형식대로 **질의에만** 아래 지시문을 붙이고, 문서는 그대로 임베딩한다.
# 문서 쪽 형식은 그대로이므로 기존 색인과 호환된다 — 재색인이 필요 없다.
_QUERY_INSTRUCT = ("Instruct: Given a web search query, retrieve relevant "
                   "passages that answer the query\nQuery: ")


def embed_query(text: str, model: str | None = None) -> list[float]:
    """검색 질의 1건을 임베딩한다. 문서 임베딩과 달리 검색 지시문을 붙인다.

    질의를 문서처럼 맨몸으로 임베딩하면 관련 문서와 무관 문서의 유사도가
    한 덩어리로 붙어 구분력이 떨어진다 — "관련 없는 파일이 검색 결과를 채우는"
    원인 중 하나였다. 분류·추천(RAG)의 문서↔문서 유사도 조회는 대칭이 맞으므로
    이 지시문을 쓰지 않는다 (OllamaEmbeddingFunction 그대로).
    """
    model = model or resolve_model()
    if "qwen3-embedding" in model:
        text = _QUERY_INSTRUCT + text
    return _embed(model, [text], config.EMBED_TIMEOUT_SEC)[0]


def ollama_version() -> str:
    """설치된 Ollama 버전. 확인할 수 없으면 빈 문자열."""
    try:
        response = _session.get(f"{OLLAMA_BASE_URL}/api/version", timeout=1.5)
        response.raise_for_status()
        return str((response.json() or {}).get("version", ""))
    except (requests.exceptions.RequestException, ValueError):
        return ""


def installed_models() -> set[str]:
    """설치된 모델 이름 집합. 태그 있는 이름과 없는 이름을 모두 담는다."""
    try:
        response = _session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        response.raise_for_status()
    except (requests.exceptions.RequestException, ValueError):
        return set()

    names: set[str] = set()
    for entry in (response.json() or {}).get("models", []):
        name = str(entry.get("name", ""))
        if name:
            names.add(name)
            names.add(name.split(":")[0])
    return names


def probe(model: str) -> tuple[bool, str, str]:
    """이 모델로 **실제로** 한 건 임베딩해 본다. (되는가, 안 되는 이유, 갈래)

    이름이 `/api/tags`에 보이는 것과 그 PC에서 도는 것은 다른 문제다.
    `ollama pull`은 파일을 받아 오기만 하므로, 실행기가 낡았거나 메모리가
    모자라면 pull은 성공하고 첫 임베딩에서 500이 난다. 그 상태로 색인을
    시작하면 사용자는 한참 기다린 뒤에야 아무것도 안 됐다는 걸 알게 된다.
    """
    try:
        _embed(model, ["문서 검색 준비 확인"], timeout=min(config.EMBED_TIMEOUT_SEC, 120))
        return True, "", ""
    except EmbeddingUnavailable as exc:
        return False, str(exc), exc.kind
    except Exception as exc:  # 예상 밖의 오류도 이유를 남긴다
        return (False, f"검색 모델({model}) 확인 중 오류: {type(exc).__name__}: {exc}",
                FAILURE_UNKNOWN)


_ensure_lock = threading.Lock()
_verified_model = ""


def ensure_usable_model(force: bool = False,
                        pull: Callable[[str], None] | None = None) -> str:
    """실제로 도는 임베딩 모델을 정해 돌려준다. 하나도 없으면 EmbeddingUnavailable.

    기본 모델이 이 PC에서 안 돌면 **두루 도는 예비 모델로 갈아탄다.**
    예비 모델(nomic-embed-text)은 작고 오래돼서 구버전 Ollama와 저사양 PC에서도
    동작한다. 검색 품질은 기본 모델보다 낮지만, 검색이 아예 안 되는 것보다 낫다.

    `pull`을 주면 설치되지 않은 후보를 그 함수로 받아 온다 (준비 화면에서
    진행률을 그리며 받을 때). 안 주면 설치된 것만 시도한다 — 색인 도중에
    수 GB를 말없이 내려받기 시작하면 안 되기 때문이다.

    한 번 확인한 모델은 다시 확인하지 않는다 — 확인 자체가 임베딩 1회다.
    """
    global _verified_model

    with _ensure_lock:
        if _verified_model and not force:
            return _verified_model

        current = resolve_model()
        installed = installed_models()

        # 지금 모델 먼저, 그다음 예비 모델. 중복은 없앤다.
        candidates: list[str] = [current]
        for fallback in config.OLLAMA_EMBED_FALLBACKS:
            if fallback not in candidates:
                candidates.append(fallback)

        reasons: list[tuple[str, str]] = []
        for candidate in candidates:
            if candidate not in installed and candidate.split(":")[0] not in installed:
                if pull is None:
                    reasons.append((f"검색 모델({candidate})이 설치되어 있지 않습니다.",
                                    FAILURE_MISSING))
                    continue
                try:
                    pull(candidate)
                except Exception as exc:
                    reasons.append((f"검색 모델({candidate})을 받지 못했습니다: {exc}",
                                    FAILURE_MISSING))
                    continue

            ok, reason, kind = probe(candidate)
            if ok:
                if candidate != current:
                    settings.set_embed_model(candidate)
                _verified_model = candidate
                return candidate

            reasons.append((reason, kind))
            # 실행기가 깨졌으면 다른 모델을 받아 봐야 똑같이 죽는다. 몇 백 MB를
            # 헛되이 내려받게 하지 말고 여기서 멈춰 "Ollama 재설치"로 안내한다.
            if kind == FAILURE_RUNTIME:
                break

        if reasons:
            raise EmbeddingUnavailable(*reasons[0])
        raise EmbeddingUnavailable(f"검색 모델({current})을 쓸 수 없습니다.")


def forget_verified_model() -> None:
    """확인 결과를 잊는다. 모델을 새로 받은 뒤에 부른다."""
    global _verified_model
    with _ensure_lock:
        _verified_model = ""


def check_ollama(model: str | None = None) -> tuple[bool, str]:
    """Ollama 서버와 모델이 준비됐는지 확인한다. (준비됨, 안내문)"""
    model = model or resolve_model()
    try:
        response = _session.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return False, (
            "문서 분석 도구가 실행되지 않았습니다. 앱을 껐다 다시 열면 "
            "자동으로 시작됩니다."
        )

    installed = {m["name"].split(":")[0] for m in response.json().get("models", [])}
    if model.split(":")[0] not in installed:
        return False, f"검색 모델({model})이 아직 설치되지 않았습니다. 설정에서 준비 화면을 열어 주세요."

    return True, ""
