"""RAG 컨텍스트 조회 (기능②③ 추천 경로).

추천 한 건에 필요한 두 가지를 **임베딩 질의 한 번**으로 같이 얻는다.
  - few-shot 예시: 비슷한 문서들이 어떻게 정리돼 있었는지 (프롬프트 주입용)
  - k-NN 분류: 최근접 이웃의 카테고리 다수결 (ADR-0002 §5-1, 추가 비용 0)

질의 임베딩이 CPU에서 건당 약 2.8초라(ADR-0002 §5) 예시 검색과 분류를
따로 질의하면 그 비용이 두 배가 된다. 그래서 조회 함수를 하나로 합쳤다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter

from ..contracts.ai import (
    MAX_FIRST_PAGE_CHARS,
    MAX_SIMILAR_EXAMPLES,
    Category,
    RetrievedExample,
)
from .search import SearchUnavailable, _collection

# k-NN 다수결에 쓸 이웃 수. ADR-0002 §5-1 실측에서 k=3이 96.0%로 최고였다.
KNN_K = 3

# 질의 텍스트 상한. 색인된 본문과 같은 기준(첫 페이지)이라 이 이상은 의미가 없다.
MAX_QUERY_CHARS = 1500


@dataclass
class RagContext:
    """추천 한 건에 쓰는 RAG 조회 결과."""

    examples: list[RetrievedExample] = field(default_factory=list)
    # k-NN 다수결 분류. 이웃 메타데이터가 비정상이면 None일 수 있다.
    knn_category: Category | None = None
    # 다수결 득표율 (0.0~1.0). slim 모드에서 confidence로 쓴다.
    knn_vote_ratio: float = 0.0


def _to_score(distance: float) -> float:
    """코사인 거리를 0~1 관련도로 바꾼다. `rag.search._to_score`와 같은 규칙."""
    return max(0.0, min(1.0, 1.0 - float(distance)))


def retrieve_context(
    text: str,
    *,
    top_k_examples: int = MAX_SIMILAR_EXAMPLES,
    exclude_name: str | None = None,
) -> RagContext:
    """문서 텍스트로 유사 예시와 k-NN 분류를 한 번에 조회한다.

    `exclude_name`: 실험에서 자기 자신(같은 파일명)이 이웃으로 잡히는 것을 막을 때 쓴다.
    색인이 준비되지 않았으면 SearchUnavailable이 그대로 올라간다 — 호출자가
    "예시 없이 진행"할지 결정한다.
    """
    collection = _collection()

    # 제외 대상과 계약 위반 예시를 걸러도 남도록 조금 더 받아 둔다.
    want = max(top_k_examples, KNN_K)
    result = collection.query(
        query_texts=[text[:MAX_QUERY_CHARS]],
        n_results=min(want * 2, 10),
    )

    metadatas = result.get("metadatas", [[]])[0]
    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]

    context = RagContext()
    votes: list[Category] = []

    for metadata, document, distance in zip(metadatas, documents, distances):
        metadata = dict(metadata or {})
        name = str(metadata.get("current_name", ""))
        if exclude_name and name == exclude_name:
            continue

        try:
            category = Category(str(metadata.get("true_category", "")))
        except ValueError:
            # 색인 메타데이터가 계약 밖이면 예시·투표 모두에서 제외한다.
            continue

        if len(votes) < KNN_K:
            votes.append(category)

        if len(context.examples) < top_k_examples:
            context.examples.append(
                RetrievedExample(
                    # 정리된 뒤의 모습을 보여 줘야 few-shot 예시가 된다.
                    file_name=str(metadata.get("ideal_filename", name) or name),
                    category=category,
                    first_page_text=(document or "")[:MAX_FIRST_PAGE_CHARS],
                    score=_to_score(distance),
                )
            )

        if len(votes) >= KNN_K and len(context.examples) >= top_k_examples:
            break

    if votes:
        winner, count = Counter(votes).most_common(1)[0]
        context.knn_category = winner
        context.knn_vote_ratio = count / len(votes)

    return context


__all__ = ["RagContext", "retrieve_context", "SearchUnavailable", "KNN_K"]
