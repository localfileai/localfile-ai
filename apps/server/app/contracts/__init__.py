"""팀 공용 데이터 계약. (전원 리뷰)

BE1·BE2·FE1·FE2가 모두 이 스키마를 단일 기준으로 삼습니다.
프론트엔드 TypeScript 타입은 여기서 생성됩니다 — 손으로 다시 쓰지 마세요.

변경하려면 먼저 '계약 변경 제안' 이슈를 열고 영향받는 파트의 동의를 받으세요.
모든 모델은 extra="forbid" 입니다. LLM이 계약에 없는 필드를 덧붙이면
검증 단계에서 걸러집니다.
"""

from app.contracts.schemas import (
    MAX_FIRST_PAGE_TEXT,
    MAX_REASON_LENGTH,
    MAX_SIMILAR_EXAMPLES,
    Category,
    FileAnalysisInput,
    FileOrganizeOutput,
    FileRecommendation,
    OrganizeResponse,
    SimilarExample,
)

__all__ = [
    "MAX_FIRST_PAGE_TEXT",
    "MAX_REASON_LENGTH",
    "MAX_SIMILAR_EXAMPLES",
    "Category",
    "FileAnalysisInput",
    "FileOrganizeOutput",
    "FileRecommendation",
    "OrganizeResponse",
    "SimilarExample",
]
