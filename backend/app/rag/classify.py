"""문서 분류 (기능②) — 세 방식을 우선순위로 합친다.

  1. 사용자 예시 k-NN : 사용자가 승인한 분류 결과(피드백)와 비교. 쓸수록 맞춤화
  2. 라벨 정의문 zero-shot : 라벨 설명문 좌표와 비교. 예시 데이터 없이 첫날부터 동작
  3. etc (분류 보류)   : 어느 쪽도 충분히 가깝지 않으면 억지 분류하지 않는다

세 방식 모두 **이미 계산된 좌표끼리의 거리 비교**라 파일당 1ms 미만이다.
비싼 연산(임베딩)은 문서당 1회뿐이고, 그 좌표를 RAG 조회와도 공유한다.

라벨 정의문은 개발자가 작성해 앱에 내장한다 — 사용자 입력이 아니다.
LLM 프롬프트의 CATEGORY_GUIDE와 같은 역할을 임베딩 모델에게 시키는 것.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from ..contracts.ai import Category
from ..core import config
from .embedding import OllamaEmbeddingFunction

# 라벨 정의문 — 문서가 "어떤 설명에 가장 가까운가"를 재는 기준.
# ETC는 여기 없다: etc는 비교 대상이 아니라 "어디에도 안 가까움"의 결과다.
LABEL_DEFINITIONS: dict[Category, str] = {
    Category.LECTURE: "수업 내용을 설명하는 강의자료. 학습 목표, 개념 설명, 예제, 다음 시간 예고가 담긴 문서",
    Category.ASSIGNMENT: "기한 내에 제출해야 하는 과제. 문제, 제출 방법, 채점 기준이 담긴 문서",
    Category.REPORT: "실험이나 측정을 수행하고 결과를 분석한 보고서. 실험 방법, 결과, 결론이 담긴 문서",
    Category.REFERENCE: "논문이나 연구 자료를 읽고 핵심을 정리한 요약. 서지 정보, 제안 방법, 연구 결과가 담긴 문서",
    Category.PROJECT: "개발이나 연구 프로젝트의 목표와 계획. 기능 명세, 개발 일정, 팀 역할 분담이 담긴 기획 문서",
    Category.EXAM_PREP: "시험을 준비하며 정리한 요약 노트. 시험 범위, 핵심 개념, 예상 문제가 담긴 문서",
    Category.CAREER: "취업을 위한 자기소개서, 이력서, 포트폴리오. 지원 동기, 경력, 직무 역량이 담긴 문서",
    Category.ADMIN: "신청서, 확인서, 증명서, 공고, 공문 같은 행정 서류. 장학금·등록금 안내, 기관에 제출하는 양식이 담긴 문서",
    Category.PERSONAL: "여행 일정, 운동과 식단 기록, 이사 준비 같은 개인 일상생활 문서",
}


@dataclass
class ClassifyResult:
    category: Category
    confidence: float          # 0~1. 방식마다 의미가 다르다 (아래 method 참고)
    method: str                # "user_knn" | "label_zeroshot" | "etc_fallback"


class _State:
    """라벨 정의문 좌표 캐시. 서버 시작 후 첫 분류 때 1회만 임베딩한다."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.labels: list[Category] | None = None
        self.vectors = None  # numpy (len(labels), dim), L2 정규화됨


_state = _State()


def _normalize(matrix):
    import numpy as np

    array = np.asarray(matrix, dtype=np.float32)
    if array.ndim == 1:
        array = array[None, :]
    return array / np.clip(np.linalg.norm(array, axis=1, keepdims=True), 1e-9, None)


def embed_text(text: str) -> list[float]:
    """문서 1건을 좌표로. 분류와 RAG 조회가 이 좌표를 공유한다 (임베딩 1회 원칙)."""
    return OllamaEmbeddingFunction()([text[:config.INDEX_EMBED_MAX_CHARS]])[0]


def _label_vectors():
    if _state.vectors is None:
        with _state.lock:
            if _state.vectors is None:
                labels = list(LABEL_DEFINITIONS)
                raw = OllamaEmbeddingFunction()([LABEL_DEFINITIONS[l] for l in labels])
                _state.labels = labels
                _state.vectors = _normalize(raw)
    return _state.labels, _state.vectors


def _user_example_vote(vector, feedback_collection) -> ClassifyResult | None:
    """사용자 승인 예시와 비교한다. 충분히 가까운 예시가 있을 때만 결과를 낸다."""
    if feedback_collection is None:
        return None
    try:
        if feedback_collection.count() == 0:
            return None
        found = feedback_collection.query(
            query_embeddings=[list(map(float, vector))],
            n_results=config.CLASSIFY_USER_KNN_K)
    except Exception:
        return None

    votes: list[tuple[Category, float]] = []
    for metadata, distance in zip(found.get("metadatas", [[]])[0],
                                  found.get("distances", [[]])[0]):
        similarity = 1.0 - float(distance)
        if similarity < config.CLASSIFY_USER_MIN_SIMILARITY:
            continue
        try:
            votes.append((Category(str((metadata or {}).get("category", ""))), similarity))
        except ValueError:
            continue

    if not votes:
        return None

    from collections import Counter

    winner, count = Counter(category for category, _ in votes).most_common(1)[0]
    best = max(sim for category, sim in votes if category == winner)
    return ClassifyResult(winner, round(min(1.0, best * count / len(votes)), 2), "user_knn")


def classify_vector(vector, feedback_collection=None) -> ClassifyResult:
    """좌표 하나를 분류한다. 임베딩은 호출자가 이미 계산했어야 한다."""
    import numpy as np

    # 1순위: 사용자 피드백 예시 (그 사람의 진짜 파일·관례)
    user_result = _user_example_vote(vector, feedback_collection)
    if user_result is not None:
        return user_result

    # 2순위: 라벨 정의문 zero-shot
    labels, label_matrix = _label_vectors()
    query = _normalize(vector)[0]
    similarities = label_matrix @ query
    best = int(np.argmax(similarities))
    best_similarity = float(similarities[best])

    if best_similarity >= config.CLASSIFY_MIN_SIMILARITY:
        return ClassifyResult(labels[best], round(best_similarity, 2), "label_zeroshot")

    # 3순위: 억지로 분류하지 않는다 — 데이터가 모르는 종류의 문서다.
    return ClassifyResult(Category.ETC, round(best_similarity, 2), "etc_fallback")


def classify_text(text: str, feedback_collection=None) -> tuple[ClassifyResult, list[float]]:
    """텍스트를 분류하고, 재사용 가능하도록 좌표도 함께 돌려준다."""
    vector = embed_text(text)
    return classify_vector(vector, feedback_collection), vector
