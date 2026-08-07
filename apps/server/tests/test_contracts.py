"""데이터 계약 검증.

LLM 출력이 계약을 벗어나는 경우를 여기서 전부 잡습니다.
exaone3.5는 90건 중 5건에서 형식 제약을 어겼습니다 (reason 초과 3, Enum 밖 값 2).
계약이 느슨해지면 그 오류가 그대로 UI까지 흘러갑니다.
"""

import pytest
from pydantic import ValidationError

from app.contracts import (
    MAX_REASON_LENGTH,
    Category,
    FileAnalysisInput,
    FileOrganizeOutput,
    FileRecommendation,
    OrganizeResponse,
    SimilarExample,
)

VALID_OUTPUT = {
    "category": "assignment",
    "recommended_folder": "assignment/database/2025_1학기",
    "recommended_filename": "데이터베이스_정규화_과제_보고서.docx",
    "confidence": 0.87,
    "reason": "제목과 본문이 정규화 실습 과제 제출물 형식이라 assignment로 분류함",
}


def test_valid_llm_output_passes():
    parsed = FileOrganizeOutput.model_validate(VALID_OUTPUT)

    assert parsed.category is Category.ASSIGNMENT
    assert parsed.confidence == 0.87


def test_korean_json_string_parses():
    """LLM은 JSON 문자열을 반환합니다. 한글이 깨지지 않는지 확인합니다."""
    import json

    raw = json.dumps(VALID_OUTPUT, ensure_ascii=False)
    parsed = FileOrganizeOutput.model_validate_json(raw)

    assert parsed.recommended_filename == VALID_OUTPUT["recommended_filename"]


@pytest.mark.parametrize(
    ("label", "override", "expected_type"),
    [
        ("Enum 밖 category", {"category": "homework"}, "enum"),
        ("빈 recommended_folder", {"recommended_folder": ""}, "string_too_short"),
        ("빈 recommended_filename", {"recommended_filename": ""}, "string_too_short"),
        ("confidence 범위 초과", {"confidence": 1.5}, "less_than_equal"),
        ("confidence 범위 미만", {"confidence": -0.1}, "greater_than_equal"),
        ("reason 빈 문자열", {"reason": ""}, "string_too_short"),
        ("reason 길이 초과", {"reason": "가" * (MAX_REASON_LENGTH + 1)}, "string_too_long"),
        ("계약에 없는 필드", {"note": "extra"}, "extra_forbidden"),
    ],
)
def test_invalid_llm_output_rejected(label, override, expected_type):
    payload = {**VALID_OUTPUT, **override}

    with pytest.raises(ValidationError) as exc_info:
        FileOrganizeOutput.model_validate(payload)

    types = {e["type"] for e in exc_info.value.errors()}
    assert expected_type in types, f"{label}: {types}"


def test_missing_field_rejected():
    payload = {k: v for k, v in VALID_OUTPUT.items() if k != "confidence"}

    with pytest.raises(ValidationError):
        FileOrganizeOutput.model_validate(payload)


def test_all_violations_reported_at_once():
    """재시도 프롬프트에 위반 사유를 전부 담으려면 한 번에 모두 보고돼야 합니다."""
    payload = {
        "category": "homework",
        "recommended_folder": "",
        "confidence": 1.5,
        "reason": "",
    }

    with pytest.raises(ValidationError) as exc_info:
        FileOrganizeOutput.model_validate(payload)

    assert exc_info.value.error_count() >= 4


def test_similar_examples_capped():
    """RAG 예시가 3건을 넘으면 프롬프트가 길어져 응답이 느려집니다."""
    example = SimilarExample(
        first_page_text="정규화 실습 결과 정리",
        category=Category.ASSIGNMENT,
        relative_path="assignment/database/0002_정규화.docx",
        file_name="0002_정규화.docx",
    )

    with pytest.raises(ValidationError):
        FileAnalysisInput(
            file_name="0001_보고서.docx",
            extension="docx",
            first_page_text="데이터베이스 정규화 과제 보고서",
            similar_examples=[example] * 4,
        )


def test_first_page_text_capped():
    with pytest.raises(ValidationError):
        FileAnalysisInput(
            file_name="0001_보고서.docx",
            extension="docx",
            first_page_text="가" * 1501,
        )


def test_response_nests_recommendations():
    response = OrganizeResponse(
        total_files=2,
        success_count=1,
        failed_files=["C:/data/깨진파일.pdf"],
        recommendations=[
            FileRecommendation(
                original_path="C:/data/0001_보고서.docx",
                original_name="0001_보고서.docx",
                result=FileOrganizeOutput.model_validate(VALID_OUTPUT),
            )
        ],
    )

    assert response.recommendations[0].result.category is Category.ASSIGNMENT
    assert len(response.failed_files) == 1


def test_json_schema_required_fields():
    """LLM에 넘기는 JSON Schema가 필수 필드를 전부 명시하는지."""
    schema = FileOrganizeOutput.model_json_schema()

    assert set(schema["required"]) == {
        "category",
        "recommended_folder",
        "recommended_filename",
        "confidence",
        "reason",
    }
