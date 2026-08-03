"""추천 프롬프트와 재시도 프롬프트.

full 프롬프트는 1주차 실험(`scripts/test_models.py`)에서 검증된 문안을 그대로 쓴다.
문안을 바꾸면 ADR-0002의 측정 수치와 비교할 수 없게 되므로, 바꿀 때는
같은 실험으로 재측정해야 한다.

slim 프롬프트는 ADR-0002 §5-1의 저사양 대책이다. 분류를 k-NN이 맡으면
LLM은 파일명 한 줄만 만들면 되고, 디코더 생성 시간은 출력 길이에 비례하므로
출력 토큰을 143 → 31개로 줄여 CPU에서 47.8초 → 13.0초가 됐다.
"""

from __future__ import annotations

from pydantic import ValidationError

from ..contracts.ai import MAX_FIRST_PAGE_CHARS, RetrievedExample

CATEGORY_GUIDE = """- lecture     : 강의자료, 수업 노트
- assignment  : 제출용 과제
- report      : 실험 보고서, 결과 분석
- reference   : 논문 요약, 참고자료
- project     : 프로젝트 계획서, 설계 문서
- exam_prep   : 시험 정리, 요약 노트
- career      : 자기소개서, 이력서, 포트폴리오 등 취업·지원 문서
- admin       : 장학금·등록금·증명서 등 학사 행정 안내
- personal    : 여행 계획, 체크리스트 등 개인 생활 문서
- etc         : 위 어디에도 해당하지 않는 문서 (억지로 다른 값을 고르지 말 것)"""

FILENAME_RULES = """recommended_filename 규칙:
- 과목명, 문서 주제, 문서 유형, 학기를 밑줄(_)로 이어 붙입니다.
- 원본 확장자를 그대로 유지합니다.
- \\ / : * ? " < > | 문자는 쓸 수 없습니다."""

# full: 5필드 전부 LLM이 생성. test_models.py의 SYSTEM_PROMPT와 같은 문안이다.
SYSTEM_PROMPT_FULL = f"""당신은 어질러진 개인 문서를 정리해 주는 파일 정리 전문가입니다.
사용자의 파일은 "최종.pdf", "무제.txt"처럼 이름만 봐서는 내용을 알 수 없습니다.
첫 페이지 텍스트를 읽고 어느 폴더에 어떤 이름으로 보관할지 판단하십시오.

반드시 아래 JSON 객체 하나만 출력하십시오. 설명, 인사말, 마크다운 코드펜스 등
JSON 외의 문자는 절대 출력하지 마십시오.

{{
  "category": "<아래 10개 중 정확히 하나>",
  "recommended_folder": "<상대 경로. 예: lecture/운영체제/2025-1>",
  "recommended_filename": "<확장자를 포함한 새 파일명>",
  "confidence": <0.0 이상 1.0 이하의 실수>,
  "reason": "<한국어 1~200자 근거>"
}}

category는 다음 10개 값 중 하나여야 하며, 그 외의 값은 허용되지 않습니다.
{CATEGORY_GUIDE}

{FILENAME_RULES}
"""

# slim: LLM은 파일명만 만든다. 분류는 k-NN(retrieve.py), 나머지 필드는 백엔드가 채운다.
SYSTEM_PROMPT_SLIM = f"""당신은 어질러진 개인 문서에 알기 쉬운 새 파일명을 지어 주는 전문가입니다.
첫 페이지 텍스트를 읽고 새 파일명 하나만 정하십시오.

반드시 아래 JSON 객체 하나만 출력하십시오. 다른 문자는 절대 출력하지 마십시오.

{{
  "recommended_filename": "<확장자를 포함한 새 파일명>"
}}

{FILENAME_RULES}
- 학기(예: 2025-1)를 알 수 있으면 반드시 포함합니다.
"""


def build_user_prompt(
    *,
    current_name: str,
    current_path: str,
    extension: str,
    first_page_text: str,
    examples: list[RetrievedExample] | None = None,
) -> str:
    """분석 대상 파일 정보와 RAG 예시로 사용자 프롬프트를 만든다."""
    parts = [
        f"현재 파일명: {current_name}",
        f"현재 위치: {current_path}",
        f"확장자: {extension}",
        "",
        f"첫 페이지 텍스트 (최대 {MAX_FIRST_PAGE_CHARS}자):",
        "---",
        first_page_text[:MAX_FIRST_PAGE_CHARS],
        "---",
    ]
    if examples:
        parts += ["", "참고: 비슷한 문서들은 이렇게 정리되어 있었습니다."]
        for example in examples:
            parts.append(f"  - {example.file_name}  ->  {example.category.value} 폴더")
    parts += ["", "이 파일을 분석해 JSON 한 개만 출력하십시오."]
    return "\n".join(parts)


def format_violations(error: ValidationError) -> str:
    """ValidationError를 모델이 고칠 수 있는 한국어 위반 목록으로 바꾼다.

    재시도 프롬프트의 핵심이다. "형식이 틀렸다"가 아니라 **어느 필드가 어떤
    제약을 어겼는지**를 그대로 보여 줘야 모델이 그 부분만 고친다.
    """
    lines = []
    for item in error.errors():
        loc = ".".join(str(part) for part in item["loc"]) or "(전체)"
        lines.append(f"- {loc}: {item['msg']}")
    return "\n".join(lines)


def build_retry_prompt(user_prompt: str, raw_response: str, violations: str) -> str:
    """검증에 실패한 응답과 위반 내역을 붙여 1회 재시도 프롬프트를 만든다."""
    return (
        f"{user_prompt}\n\n"
        "[재시도] 방금 출력한 JSON이 아래 규칙을 위반해 거부되었습니다.\n"
        f"이전 출력:\n{raw_response}\n\n"
        f"위반 내역:\n{violations}\n\n"
        "위반된 항목을 모두 고쳐, 같은 파일에 대한 JSON 객체 하나만 다시 출력하십시오."
    )
