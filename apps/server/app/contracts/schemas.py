"""LocalFile AI 데이터 계약.

BE1(LLM 출력) / BE2(API 응답) / FE2(화면 렌더링)가 공유하는 입출력 스키마다.
LLM 출력은 반드시 FileOrganizeOutput으로 검증한 뒤에만 다음 단계로 넘긴다.

검증 실패 시 위반한 제약을 프롬프트에 명시해 1회 재시도한다. app/llm/ 참고.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# first_page_text 상한. 로컬 LLM 컨텍스트와 응답 속도를 고려한 값이다.
MAX_FIRST_PAGE_TEXT = 1500
# RAG 검색으로 프롬프트에 끼워 넣을 유사 예시 최대 개수.
MAX_SIMILAR_EXAMPLES = 3
# reason 길이 상한. exaone3.5가 3/30 확률로 어긴다 — 재시도 로직이 필수다.
MAX_REASON_LENGTH = 200


class Category(StrEnum):
    """파일 최상위 분류. experiments/generate_student_dataset.py와 동일하다.

    StrEnum이므로 f-string에 넣으면 값이 그대로 나온다 ("assignment").
    프롬프트를 조립할 때 .value를 붙이지 않아도 된다.
    """

    PROJECT = "project"
    ASSIGNMENT = "assignment"
    ESSAY = "essay"
    RESEARCH = "research"
    LECTURE = "lecture"
    REFERENCE = "reference"
    PRACTICE = "practice"
    TEAM_PROJECT = "team_project"


class SimilarExample(BaseModel):
    """ChromaDB 검색 결과 1건. RAG 프롬프트에서 few-shot 예시로 쓴다."""

    model_config = ConfigDict(extra="forbid")

    first_page_text: str = Field(..., description="유사 파일의 첫 페이지 텍스트")
    category: Category = Field(..., description="유사 파일의 정답 카테고리")
    relative_path: str = Field(..., description="루트 기준 상대 경로")
    file_name: str = Field(..., description="유사 파일명")


class FileAnalysisInput(BaseModel):
    """LLM에 넘기는 분석 입력 1건."""

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(..., min_length=1, description="원본 파일명")
    extension: str = Field(..., min_length=1, description="확장자(점 제외). 예: docx")
    first_page_text: str = Field(
        ...,
        max_length=MAX_FIRST_PAGE_TEXT,
        description=f"첫 페이지 텍스트. 최대 {MAX_FIRST_PAGE_TEXT}자",
    )
    similar_examples: list[SimilarExample] = Field(
        default_factory=list,
        max_length=MAX_SIMILAR_EXAMPLES,
        description=f"RAG 유사 예시. 최대 {MAX_SIMILAR_EXAMPLES}건",
    )


class FileOrganizeOutput(BaseModel):
    """LLM 출력 계약. 로컬 LLM이 만든 JSON은 반드시 이 모델을 통과해야 한다."""

    model_config = ConfigDict(extra="forbid")

    category: Category = Field(..., description="8개 카테고리 중 하나")
    recommended_folder: str = Field(..., min_length=1, description="추천 폴더 경로")
    recommended_filename: str = Field(..., min_length=1, description="추천 파일명")
    confidence: float = Field(..., ge=0.0, le=1.0, description="확신도 0.0~1.0")
    reason: str = Field(
        ...,
        min_length=1,
        max_length=MAX_REASON_LENGTH,
        description=f"추천 근거 1~{MAX_REASON_LENGTH}자",
    )


class FileRecommendation(BaseModel):
    """파일 1건에 대한 최종 추천 결과."""

    model_config = ConfigDict(extra="forbid")

    original_path: str = Field(..., min_length=1, description="원본 절대/상대 경로")
    original_name: str = Field(..., min_length=1, description="원본 파일명")
    result: FileOrganizeOutput = Field(..., description="LLM 추천 결과")


class OrganizeResponse(BaseModel):
    """API 응답 계약. FE가 이 형태로 받는다."""

    model_config = ConfigDict(extra="forbid")

    total_files: int = Field(..., ge=0, description="요청에 포함된 전체 파일 수")
    success_count: int = Field(..., ge=0, description="추천 생성에 성공한 파일 수")
    failed_files: list[str] = Field(default_factory=list, description="실패한 파일 경로 목록")
    recommendations: list[FileRecommendation] = Field(
        default_factory=list, description="성공한 파일들의 추천 결과"
    )
