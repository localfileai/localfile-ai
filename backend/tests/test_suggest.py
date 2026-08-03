"""Pydantic 검증 + 1회 재시도 파이프라인 테스트 (계획서 3주차 BE1 ③).

Ollama 없이 돈다 — LLM 호출을 가짜 함수로 주입한다.
"""

import json

import pytest

from app.contracts.ai import Category
from app.llm.client import LLMRequestError
from app.llm.suggest import autofix_extension, suggest_full, suggest_slim

VALID_FULL = json.dumps({
    "category": "assignment",
    "recommended_folder": "assignment/데이터베이스/2025-1",
    "recommended_filename": "데이터베이스_정규화_과제_2025-1.pdf",
    "confidence": 0.9,
    "reason": "문서 유형이 과제로 명시되어 있다.",
}, ensure_ascii=False)


def make_generate(responses):
    """호출될 때마다 responses에서 하나씩 꺼내 주는 가짜 LLM. 호출 기록을 남긴다."""
    calls = []

    def generate(system, prompt):
        calls.append({"system": system, "prompt": prompt})
        response = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response

    generate.calls = calls
    return generate


COMMON = dict(
    current_name="최종.pdf",
    current_path="C:/Users/a/Downloads",
    extension="pdf",
    first_page_text="데이터베이스 정규화 과제 ...",
)


class TestAutofixExtension:
    def test_확장자_없으면_붙인다(self):
        raw = json.dumps({"recommended_filename": "정규화_과제_2025-1"})
        fixed, did_fix = autofix_extension(raw, "pdf")
        assert did_fix
        assert json.loads(fixed)["recommended_filename"] == "정규화_과제_2025-1.pdf"

    def test_이미_있으면_그대로(self):
        raw = json.dumps({"recommended_filename": "정규화_과제.pdf"})
        _, did_fix = autofix_extension(raw, "pdf")
        assert not did_fix

    def test_대소문자_확장자도_인정(self):
        raw = json.dumps({"recommended_filename": "REPORT.PDF"})
        _, did_fix = autofix_extension(raw, "pdf")
        assert not did_fix

    def test_JSON이_아니면_건드리지_않는다(self):
        raw, did_fix = autofix_extension("깨진 응답 {", "pdf")
        assert raw == "깨진 응답 {"
        assert not did_fix


class TestSuggestFull:
    def test_정상_응답은_재시도_없이_통과(self):
        generate = make_generate([VALID_FULL])
        result = suggest_full(generate, **COMMON)
        assert result.suggestion is not None
        assert result.suggestion.category is Category.ASSIGNMENT
        assert not result.retried
        assert len(generate.calls) == 1

    def test_확장자_누락은_보정으로_해결_재시도_아님(self):
        # ADR-0002 1차 측정에서 JSON 유효율 62.5%의 원인 전부가 이 사례였다.
        payload = json.loads(VALID_FULL)
        payload["recommended_filename"] = "데이터베이스_정규화_과제_2025-1"
        generate = make_generate([json.dumps(payload, ensure_ascii=False)])
        result = suggest_full(generate, **COMMON)
        assert result.suggestion is not None
        assert result.suggestion.recommended_filename.endswith(".pdf")
        assert result.extension_fixed
        assert not result.retried
        assert len(generate.calls) == 1

    def test_검증_실패시_위반을_명시해_1회_재시도(self):
        bad = json.dumps({**json.loads(VALID_FULL), "category": "homework"},
                         ensure_ascii=False)
        generate = make_generate([bad, VALID_FULL])
        result = suggest_full(generate, **COMMON)
        assert result.suggestion is not None
        assert result.retried
        assert len(generate.calls) == 2
        # 재시도 프롬프트가 위반 필드를 그대로 알려 줘야 한다.
        retry_prompt = generate.calls[1]["prompt"]
        assert "category" in retry_prompt
        assert "위반" in retry_prompt

    def test_재시도도_실패하면_이유와_함께_실패(self):
        bad = json.dumps({**json.loads(VALID_FULL), "confidence": 1.5},
                         ensure_ascii=False)
        generate = make_generate([bad, bad])
        result = suggest_full(generate, **COMMON)
        assert result.suggestion is None
        assert result.retried
        assert result.error.startswith("llm_invalid_json")
        assert len(result.error) <= 200  # FailedFile.reason 계약
        assert len(generate.calls) == 2  # 재시도는 정확히 1회

    def test_호출_실패는_요청_에러로_기록(self):
        generate = make_generate([LLMRequestError("timeout(180s)")])
        result = suggest_full(generate, **COMMON)
        assert result.suggestion is None
        assert "llm_request_error" in result.error

    def test_RAG_예시가_프롬프트에_들어간다(self):
        from app.contracts.ai import RetrievedExample
        examples = [RetrievedExample(
            file_name="운영체제_스케줄링_강의자료_2026-1.pdf",
            category=Category.LECTURE, first_page_text="...", score=0.8)]
        generate = make_generate([VALID_FULL])
        suggest_full(generate, examples=examples, **COMMON)
        prompt = generate.calls[0]["prompt"]
        assert "운영체제_스케줄링_강의자료_2026-1.pdf" in prompt
        assert "lecture" in prompt


class TestSuggestSlim:
    SLIM_ARGS = dict(knn_category=Category.LECTURE, knn_vote_ratio=2 / 3,
                     model_label="exaone3.5:2.4b")

    def test_파일명만_받아_kNN_분류와_조립(self):
        raw = json.dumps({"recommended_filename": "운영체제_스케줄링_강의자료_2026-1"},
                         ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.suggestion.category is Category.LECTURE
        assert result.suggestion.recommended_folder == "lecture"
        assert result.suggestion.recommended_filename.endswith(".pdf")  # 확장자 보정
        assert result.suggestion.confidence == pytest.approx(0.67)
        assert not result.retried

    def test_금지_문자_파일명은_재시도(self):
        bad = json.dumps({"recommended_filename": "운영체제/스케줄링.pdf"}, ensure_ascii=False)
        good = json.dumps({"recommended_filename": "운영체제_스케줄링.pdf"}, ensure_ascii=False)
        generate = make_generate([bad, good])
        result = suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.retried
        assert "recommended_filename" in generate.calls[1]["prompt"]

    def test_slim_시스템_프롬프트는_파일명만_요구(self):
        raw = json.dumps({"recommended_filename": "a_b_c_2025-1.pdf"})
        generate = make_generate([raw])
        suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        system = generate.calls[0]["system"]
        assert "recommended_filename" in system
        assert "confidence" not in system  # 출력 토큰 절감이 목적이다
