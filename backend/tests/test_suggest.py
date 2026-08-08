"""Pydantic 검증 + 1회 재시도 파이프라인 테스트 (계획서 3주차 BE1 ③).

Ollama 없이 돈다 — LLM 호출을 가짜 함수로 주입한다.
"""

import json

import pytest

from app.contracts.ai import Category
from app.llm.client import LLMRequestError
from app.llm.suggest import (autofix_extension, build_filename, suggest_full,
                             suggest_slim)

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

    def test_잘못된_확장자는_원본으로_교체한다(self):
        raw = json.dumps({"recommended_filename": "보고서.docx"})
        fixed, did_fix = autofix_extension(raw, "pdf")
        assert did_fix
        assert json.loads(fixed)["recommended_filename"] == "보고서.pdf"

    def test_구조화_요소를_안전하게_조립한다(self):
        payload = {"subject": "데이터베이스", "topic": "정규화/함수 종속",
                   "document_type": "강의자료", "semester": "2026-1"}
        assert build_filename(payload, "pdf", Category.ASSIGNMENT) == \
            "데이터베이스_정규화_함수_종속_과제_2026-1.pdf"

    def test_Windows_예약어는_회피한다(self):
        assert build_filename({"topic": "CON"}, "pdf") == "문서_CON.pdf"


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

    def test_분류기_결과가_LLM_category를_덮어쓴다(self):
        # LLM은 lecture라고 했지만 분류기(82.8%)는 assignment — 분류기를 따른다.
        llm_says_lecture = json.dumps({
            **json.loads(VALID_FULL),
            "category": "lecture",
            "recommended_folder": "lecture/데이터베이스/2025-1",
        }, ensure_ascii=False)
        generate = make_generate([llm_says_lecture])
        result = suggest_full(generate, **COMMON,
                              category=Category.ASSIGNMENT, confidence=0.62,
                              method="label_zeroshot")
        assert result.suggestion.category is Category.ASSIGNMENT
        # 분류 폴더만 바뀌고 LLM이 만든 세부 경로(과목·학기)는 살아남는다.
        assert result.suggestion.recommended_folder == "assignment/데이터베이스/2025-1"
        assert "라벨 정의문" in result.suggestion.reason
        # 힌트가 프롬프트에 들어갔는지도 확인한다.
        assert "assignment" in generate.calls[0]["prompt"]

    def test_분류기가_etc면_폴더는_평평하게(self):
        generate = make_generate([VALID_FULL])
        result = suggest_full(generate, **COMMON,
                              category=Category.ETC, confidence=0.3,
                              method="etc_fallback")
        assert result.suggestion.category is Category.ETC
        assert result.suggestion.recommended_folder == "etc"

    def test_분류기가_없으면_LLM_출력_그대로(self):
        generate = make_generate([VALID_FULL])
        result = suggest_full(generate, **COMMON)  # category=None (폴백)
        assert result.suggestion.category is Category.ASSIGNMENT
        assert result.suggestion.recommended_folder == "assignment/데이터베이스/2025-1"

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
    SLIM_ARGS = dict(category=Category.LECTURE, confidence=2 / 3,
                     method="label_zeroshot", model_label="exaone3.5:2.4b")

    def test_파일명만_받아_자동_분류와_조립(self):
        raw = json.dumps({"recommended_filename": "운영체제_스케줄링_강의자료_2026-1"},
                         ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.suggestion.category is Category.LECTURE
        assert result.suggestion.recommended_folder == "lecture"
        assert result.suggestion.recommended_filename.endswith(".pdf")  # 확장자 보정
        assert result.suggestion.confidence == pytest.approx(0.67)
        assert "라벨 정의문" in result.suggestion.reason  # 분류 방식이 근거에 표시된다
        assert not result.retried

    def test_구조화_응답은_분류기_유형으로_파일명을_조립한다(self):
        raw = json.dumps({"subject": "데이터베이스", "topic": "정규화",
                          "document_type": "보고서", "semester": "2026-1"},
                         ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.suggestion.recommended_filename == \
            "데이터베이스_정규화_강의자료.pdf"

    def test_본문에_없는_subject_topic은_파일명에서_제외한다(self):
        raw = json.dumps({"subject": "법학", "topic": "형법",
                          "document_type": "과제", "semester": "2025-2"},
                         ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.suggestion.recommended_filename == "강의자료.pdf"

    def test_일반어_과제만_맞아도_환각_topic은_제외한다(self):
        raw = json.dumps({"subject": "인공지능", "topic": "머신러닝 과제",
                          "document_type": "과제", "semester": "2026-1"},
                         ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(
            generate, **{**COMMON, "first_page_text":
                         "인공지능 트랜스포머 과제 2026년 1학기"},
            **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert "머신러닝" not in result.suggestion.recommended_filename

    def test_학기는_LLM_추측보다_본문_근거를_따른다(self):
        raw = json.dumps({"subject": "데이터베이스", "topic": "정규화",
                          "document_type": "과제", "semester": "2025-2"},
                         ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(
            generate, **{**COMMON, "first_page_text":
                         "데이터베이스 정규화 과제, 2026년 1학기 제출"},
            **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.suggestion.recommended_filename.endswith("_2026-1.pdf")

    def test_유사_예시의_AI_표기_관례를_적용한다(self):
        from app.contracts.ai import RetrievedExample
        raw = json.dumps({"subject": "인공지능", "topic": "딥러닝",
                          "document_type": "과제", "semester": "2026-1"},
                         ensure_ascii=False)
        examples = [RetrievedExample(
            file_name="AI_머신러닝_과제_2025-2.pdf", category=Category.ASSIGNMENT,
            first_page_text="머신러닝", score=0.9)]
        generate = make_generate([raw])
        result = suggest_slim(
            generate, **{**COMMON, "first_page_text":
                         "인공지능 딥러닝 과제, 2026년 1학기"},
            examples=examples, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.suggestion.recommended_filename == "AI_딥러닝_강의자료_2026-1.pdf"

    def test_새_상태명과_구버전_접근자가_같은_값이다(self):
        raw = json.dumps({"subject": "데이터베이스", "topic": "정규화",
                          "document_type": "강의자료", "semester": ""},
                         ensure_ascii=False)
        result = suggest_slim(make_generate([raw]), **COMMON, **self.SLIM_ARGS)
        assert result.filename_normalized
        assert result.extension_fixed == result.filename_normalized

    def test_subject에_합쳐진_검증_가능한_topic을_복구한다(self):
        raw = json.dumps({"subject": "인공지능 트랜스포머", "topic": "",
                          "semester": "2026-1"}, ensure_ascii=False)
        result = suggest_slim(
            make_generate([raw]),
            **{**COMMON, "first_page_text": "인공지능 트랜스포머 과제 2026년 1학기"},
            **self.SLIM_ARGS)
        assert result.suggestion.recommended_filename == \
            "인공지능_트랜스포머_강의자료_2026-1.pdf"

    def test_예시에서_구분자와_영문_대소문자를_일반화한다(self):
        from app.contracts.ai import RetrievedExample
        raw = json.dumps({"subject": "tsn", "topic": "스케줄링",
                          "semester": "2026-1"}, ensure_ascii=False)
        examples = [RetrievedExample(
            file_name="TSN-네트워크-과제-2025.2.pdf", category=Category.ASSIGNMENT,
            first_page_text="TSN", score=.9)]
        result = suggest_slim(
            make_generate([raw]),
            **{**COMMON, "first_page_text": "TSN 스케줄링 과제 2026년 1학기"},
            examples=examples, **self.SLIM_ARGS)
        assert result.suggestion.recommended_filename == \
            "TSN-스케줄링-강의자료-2026-1.pdf"

    def test_etc_분류도_계약을_통과한다(self):
        raw = json.dumps({"recommended_filename": "무선이어폰_사용설명서.pdf"}, ensure_ascii=False)
        generate = make_generate([raw])
        result = suggest_slim(generate, **COMMON,
                              category=Category.ETC, confidence=0.21,
                              method="etc_fallback", model_label="exaone3.5:2.4b")
        assert result.suggestion is not None
        assert result.suggestion.category is Category.ETC
        assert "분류 보류" in result.suggestion.reason

    def test_금지_문자_파일명은_재시도(self):
        bad = json.dumps({"recommended_filename": "운영체제/스케줄링.pdf"}, ensure_ascii=False)
        good = json.dumps({"recommended_filename": "운영체제_스케줄링.pdf"}, ensure_ascii=False)
        generate = make_generate([bad, good])
        result = suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        assert result.suggestion is not None
        assert result.retried
        assert "recommended_filename" in generate.calls[1]["prompt"]

    def test_slim_시스템_프롬프트는_구성요소만_요구(self):
        raw = json.dumps({"recommended_filename": "a_b_c_2025-1.pdf"})
        generate = make_generate([raw])
        suggest_slim(generate, **COMMON, **self.SLIM_ARGS)
        system = generate.calls[0]["system"]
        assert all(key in system for key in ("subject", "topic", "semester"))
        assert '"document_type"' not in system  # JSON 출력 키로 요구하지 않는다
        assert "recommended_filename" not in system
        assert "confidence" not in system  # 출력 토큰 절감이 목적이다
