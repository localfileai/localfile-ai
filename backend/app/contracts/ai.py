"""LocalFile AI — RAG 적용에 필요한 데이터 포맷 구조.

BE1 1주차 산출물 ④. 팀 전체(BE2 / FE)가 공유하는 단일 계약이다.

기획안의 핵심 기능 3가지에 그대로 대응한다.
  ① 자연어 기반 파일 검색   -> SearchQuery / SearchHit / SearchResponse
  ② 파일 분류 추천          -> FileSuggestion.category
  ③ 파일명 추천             -> FileSuggestion.recommended_filename

기획안 "Pydantic: AI 응답과 파일 변경 요청 검증"에 따라 두 방향을 모두 검증한다.
  - AI 응답      : FileSuggestion  (로컬 LLM이 낸 JSON)
  - 파일 변경 요청: ApplyRequest    (사용자가 승인한 뒤 FE가 보내는 요청)

기획안 "사용자가 승인한 경우에만 파일명 변경 및 이동 실행"을 지키기 위해
ApplyRequest.approved 는 반드시 True 여야 통과한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 로컬 LLM 컨텍스트와 응답 속도를 고려한 첫 페이지 텍스트 상한.
MAX_FIRST_PAGE_CHARS = 2000
# 파일명 추천은 제목이 뒤쪽에 있는 문서도 다루도록 더 넓은 분석 표본을 사용한다.
MAX_ANALYSIS_CHARS = 6000
# RAG 프롬프트에 끼워 넣을 유사 예시 최대 개수.
MAX_SIMILAR_EXAMPLES = 3
# MVP 대상 확장자.
#
# 기획안 3장: "사용자가 선택한 폴더의 PDF, DOCX, DOC, HWP, HWPX, PPT, PPTX 파일 탐색"
# — 그 7종 전부다.
#
# 초기에는 PDF/TXT/MD로 잡았으나, 대학생이 실제로 다루는 문서는 강의자료·과제·발표자료라
# txt·md는 대상이 아니라고 판단해 기획안 목록으로 바로잡았다. (BE1 결정)
#
# doc·ppt는 3주차까지 "구형 OLE 포맷, 표준 파서 없음"으로 미지원이었으나,
# hwp에 이미 쓰는 olefile로 직접 파싱을 구현해 기획안과 정합시켰다
# (extraction/service.py의 _extract_doc_text / _extract_ppt_text).
ALLOWED_EXTENSIONS = ("pdf", "docx", "doc", "pptx", "ppt", "hwpx", "hwp")


class Category(str, Enum):
    """파일 분류 폴더.

    3주차 확장: 대학생의 실제 폴더에는 학업 문서만 있지 않다. 학업 6종에
    비학업 3종을 더하고, 어디에도 맞지 않는 문서를 위한 ETC를 둔다 —
    분류기가 모르는 문서를 억지로 학업 폴더에 넣는 것을 막는 안전값이다.
    """

    # --- 학업 (1주차부터) ---
    LECTURE = "lecture"        # 강의자료
    ASSIGNMENT = "assignment"  # 과제
    REPORT = "report"          # 실험 보고서
    REFERENCE = "reference"    # 논문 요약 · 참고자료
    PROJECT = "project"        # 프로젝트 계획서
    EXAM_PREP = "exam_prep"    # 시험 정리
    # --- 비학업 (3주차 확장) ---
    CAREER = "career"          # 자기소개서 · 이력서 · 지원서
    ADMIN = "admin"            # 장학·등록·증명 등 학사 행정
    PERSONAL = "personal"      # 여행 계획 · 생활 문서
    ETC = "etc"                # 어디에도 해당 없음 (분류 보류 포함)


class Strict(BaseModel):
    """계약에 없는 필드를 거부하는 공통 베이스."""

    model_config = ConfigDict(extra="forbid")


# =========================================================
# 공통
# =========================================================

class FileRef(Strict):
    """사용자 PC에 실제로 존재하는 파일 1건."""

    path: str = Field(..., min_length=1, description="절대 또는 루트 기준 경로")
    name: str = Field(..., min_length=1, description="현재 파일명 (확장자 포함)")
    extension: str = Field(..., min_length=1, description="확장자, 점 제외")
    size_bytes: int = Field(..., ge=0)
    modified_at: datetime | None = Field(default=None, description="최종 수정 시각")

    @field_validator("extension")
    @classmethod
    def _mvp_scope(cls, value: str) -> str:
        normalized = value.lower().lstrip(".")
        if normalized not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"MVP 범위 밖 확장자입니다: {value!r}. "
                f"허용: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        return normalized


# =========================================================
# ① 자연어 기반 파일 검색
# =========================================================

class SearchQuery(Strict):
    """FE 검색바에서 올라오는 요청."""

    query: str = Field(..., min_length=1, max_length=200,
                       description='예: "네트워크 스케줄링 발표 자료 찾아줘"')
    top_k: int = Field(default=20, ge=1, le=100, description="반환할 최대 건수")


class SearchHit(Strict):
    """검색 결과 1건.

    기획안: "관련 파일, 일치한 문장, 파일 위치를 관련도순으로 제공"
    """

    file: FileRef
    score: float = Field(..., ge=0.0, le=1.0,
                         description="관련도. 1에 가까울수록 유사 (거리를 변환한 값)")
    matched_text: str = Field(..., min_length=1, max_length=500,
                              description="질의와 일치한 문서 내 문장")


class SearchResponse(Strict):
    """① 자연어 검색 API 응답."""

    query: str = Field(..., min_length=1)
    total_hits: int = Field(..., ge=0)
    hits: list[SearchHit] = Field(default_factory=list, description="관련도 내림차순")
    elapsed_ms: int = Field(..., ge=0)

    @field_validator("hits")
    @classmethod
    def _sorted_desc(cls, hits: list[SearchHit]) -> list[SearchHit]:
        scores = [hit.score for hit in hits]
        if scores != sorted(scores, reverse=True):
            raise ValueError("hits는 관련도 내림차순으로 정렬되어야 합니다.")
        return hits


# =========================================================
# ②③ 파일 분류 · 파일명 추천 (RAG)
# =========================================================

class RetrievedExample(Strict):
    """ChromaDB에서 꺼낸 유사 문서 1건. RAG 프롬프트의 few-shot 예시로 쓴다."""

    file_name: str = Field(..., min_length=1)
    category: Category
    first_page_text: str = Field(..., max_length=MAX_FIRST_PAGE_CHARS)
    score: float = Field(..., ge=0.0, le=1.0)


class AnalysisInput(Strict):
    """로컬 LLM에 넘기는 분석 입력 1건."""

    file: FileRef
    first_page_text: str = Field(..., max_length=MAX_FIRST_PAGE_CHARS,
                                 description=f"첫 페이지 텍스트, 최대 {MAX_FIRST_PAGE_CHARS}자")
    similar_examples: list[RetrievedExample] = Field(
        default_factory=list, max_length=MAX_SIMILAR_EXAMPLES,
        description=f"RAG 검색 결과, 최대 {MAX_SIMILAR_EXAMPLES}건")


class FileSuggestion(Strict):
    """★ 로컬 LLM 출력 계약 ★ — 이 모델을 통과하지 못한 응답은 버린다."""

    category: Category = Field(..., description="② 분류 결과")
    recommended_folder: str = Field(..., min_length=1, max_length=200,
                                    description="② 추천 폴더 경로. 예: lecture/운영체제/2025-1")
    recommended_filename: str = Field(..., min_length=1, max_length=150,
                                      description="③ 추천 파일명. 확장자 포함")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=1, max_length=200, description="한국어 근거")

    @field_validator("recommended_filename")
    @classmethod
    def _safe_filename(cls, value: str) -> str:
        if any(ch in value for ch in '\\/:*?"<>|') or any(ord(ch) < 32 for ch in value):
            raise ValueError(f"파일명에 사용할 수 없는 문자가 있습니다: {value!r}")
        if value != value.rstrip(" ."):
            raise ValueError(f"파일명은 공백이나 점으로 끝날 수 없습니다: {value!r}")
        if "." not in value:
            raise ValueError(f"확장자가 없습니다: {value!r}")
        stem = value.rsplit(".", 1)[0]
        if stem.upper() in {"CON", "PRN", "AUX", "NUL",
                            *(f"COM{i}" for i in range(1, 10)),
                            *(f"LPT{i}" for i in range(1, 10))}:
            raise ValueError(f"Windows 예약 파일명은 사용할 수 없습니다: {value!r}")
        return value

    @field_validator("recommended_folder")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ":" in value:
            raise ValueError(f"절대 경로는 허용되지 않습니다: {value!r}")
        if ".." in value.split("/"):
            raise ValueError(f"상위 경로 참조는 허용되지 않습니다: {value!r}")
        return value


class OrganizeRequest(Strict):
    """②③ 추천 요청. FE가 사용자가 고른 파일/폴더 경로를 보낸다."""

    path: str = Field(..., min_length=1, description="분석할 파일 또는 폴더의 절대 경로")
    mode: str | None = Field(
        default=None,
        description='추천 모드. "full"(7.8b 5필드) · "slim"(k-NN 분류 + 소형 모델 파일명) · '
                    '"auto"(생성 속도를 재보고 느리면 slim). 없으면 서버 기본값(auto). '
                    "ADR-0002 §5-1 참고")
    max_files: int = Field(default=20, ge=1, le=100,
                           description="한 번에 처리할 최대 파일 수. CPU에서 파일당 수십 초라 상한을 둔다")
    offset: int = Field(default=0, ge=0,
                        description="이 순번부터 분석한다. 상한을 넘는 폴더를 \"이어서 분석\"할 때 "
                                    "FE가 지금까지 분석한 수를 넣는다")
    use_rag: bool = Field(default=True,
                          description="유사 문서 예시를 프롬프트에 주입할지 여부")

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in ("full", "slim", "auto"):
            raise ValueError(f'mode는 "full"·"slim"·"auto" 중 하나여야 합니다: {value!r}')
        return value


class FeedbackRequest(Strict):
    """②③ 사용자 피드백 — 승인·수정한 분류 결과를 라벨 예시로 저장한다.

    저장된 예시는 이후 분류에서 라벨 정의문보다 우선 참조된다 (맞춤화).
    모델을 학습시키는 것이 아니라 참조 자료를 쌓는 것이다.
    """

    path: str = Field(..., min_length=1, description="대상 파일의 절대 경로")
    category: Category = Field(..., description="사용자가 확정한 분류")
    filename: str | None = Field(default=None, max_length=150,
                                 description="사용자가 확정한 파일명 (있으면 관례 예시로도 활용)")
    first_page_text: str | None = Field(
        default=None, max_length=MAX_FIRST_PAGE_CHARS,
        description="첫 페이지 텍스트. 없으면 서버가 path에서 다시 추출한다")


class IndexRequest(Strict):
    """① 사용자 폴더 색인 요청. 색인이 되어야 자연어 검색이 실파일을 대상으로 동작한다."""

    path: str = Field(..., min_length=1, description="색인할 파일 또는 폴더의 절대 경로")
    max_files: int = Field(default=500, ge=1, le=5000,
                           description="한 번에 색인할 최대 파일 수. CPU에서 파일당 약 4.6초")


class SuggestionItem(Strict):
    """파일 1건에 대한 현재 상태 + 추천 결과."""

    current: FileRef
    suggestion: FileSuggestion


class FailedFile(Strict):
    """처리하지 못한 파일. 억지로 추천하지 않고 이유와 함께 남긴다."""

    path: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=200,
                        description="예: pdf_error, empty_text, llm_invalid_json")


class OrganizeResponse(Strict):
    """②③ 파일 분류·파일명 추천 API 응답. FE는 이걸로 '미리보기 표'를 그린다."""

    total_files: int = Field(..., ge=0)
    success_count: int = Field(..., ge=0)
    suggestions: list[SuggestionItem] = Field(default_factory=list)
    failed: list[FailedFile] = Field(default_factory=list)
    elapsed_ms: int = Field(..., ge=0)
    stages_ms: dict[str, int] = Field(default_factory=dict,
                                      description="추출·임베딩·분류·RAG·LLM·검증 누적 시간")


# =========================================================
# 승인 후 실제 파일 변경 요청
# =========================================================

class ApplyItem(Strict):
    """사용자가 체크한 항목 1건."""

    source_path: str = Field(..., min_length=1)
    target_folder: str = Field(..., min_length=1)
    target_filename: str = Field(..., min_length=1)


class ApplyRequest(Strict):
    """기획안: '사용자가 승인한 경우에만 파일명 변경 및 이동 실행'."""

    approved: bool = Field(..., description="반드시 True여야 한다")
    root: str = Field(..., min_length=1,
                      description="정리 대상 폴더의 절대 경로. target_folder는 이 아래의 상대 경로다")
    items: list[ApplyItem] = Field(..., min_length=1)
    dry_run: bool = Field(default=False, description="True면 검증만 하고 실제 변경은 하지 않음")

    @field_validator("approved")
    @classmethod
    def _must_be_approved(cls, value: bool) -> bool:
        if not value:
            raise ValueError("사용자 승인 없이는 파일을 변경할 수 없습니다.")
        return value


class AppliedItem(Strict):
    """파일 1건의 적용 결과. 실패해도 전체가 죽지 않고 여기 이유가 남는다."""

    source_path: str = Field(..., min_length=1)
    target_path: str = Field(default="", description="이동/개명된 최종 경로 (성공 시)")
    status: str = Field(..., description="moved | valid(dry_run) | skipped | failed")
    reason: str = Field(default="", max_length=200,
                        description="예: conflict(대상에 같은 이름 존재), file_in_use, unsafe_path")


class ApplyResponse(Strict):
    """승인 후 파일 변경 API 응답. 기획안 4주차 '권한 에러 방지'가 여기 반영된다."""

    total: int = Field(..., ge=0)
    moved: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    dry_run: bool
    items: list[AppliedItem] = Field(default_factory=list)
    history_id: str = Field(default="", description="되돌리기(undo)에 쓰는 작업 이력 ID")


# =========================================================
# 자체 테스트
# =========================================================

if __name__ == "__main__":
    import json

    from pydantic import ValidationError

    passed = 0

    def check_ok(label: str, fn) -> None:
        global passed
        fn()
        passed += 1
        print(f"  OK   {label}")

    def check_error(label: str, fn) -> None:
        global passed
        try:
            fn()
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"]) or "(model)"
            passed += 1
            print(f"  OK   {label:<42} -> {loc}: {first['type']}")
        else:
            raise AssertionError(f"ValidationError가 나야 하는데 통과함: {label}")

    SAMPLE_FILE = {
        "path": "files/Downloads/최종.pdf", "name": "최종.pdf",
        "extension": "pdf", "size_bytes": 20480,
    }
    SAMPLE_SUGGESTION = {
        "category": "assignment",
        "recommended_folder": "assignment/데이터베이스/2025-1",
        "recommended_filename": "데이터베이스_정규화_과제_2025-1.pdf",
        "confidence": 0.87,
        "reason": "문서 유형이 과제로 명시되어 있고 과목은 데이터베이스이다.",
    }

    print("=" * 74)
    print("[테스트 1] ① 자연어 검색 스키마")
    print("=" * 74)
    check_ok("SearchQuery 기본값 top_k=20",
             lambda: SearchQuery(query="네트워크 스케줄링 발표 자료 찾아줘"))
    check_ok("SearchResponse 정렬 정상", lambda: SearchResponse(
        query="정규화", total_hits=2, elapsed_ms=120,
        hits=[
            SearchHit(file=FileRef(**SAMPLE_FILE), score=0.91, matched_text="제3정규형 설명"),
            SearchHit(file=FileRef(**SAMPLE_FILE), score=0.72, matched_text="함수 종속"),
        ]))
    check_error("SearchResponse 정렬 위반", lambda: SearchResponse(
        query="정규화", total_hits=2, elapsed_ms=120,
        hits=[
            SearchHit(file=FileRef(**SAMPLE_FILE), score=0.5, matched_text="a"),
            SearchHit(file=FileRef(**SAMPLE_FILE), score=0.9, matched_text="b"),
        ]))
    check_error("빈 검색어", lambda: SearchQuery(query=""))
    check_error("top_k 범위 초과", lambda: SearchQuery(query="정규화", top_k=999))

    print()
    print("=" * 74)
    print("[테스트 2] ②③ LLM 출력 계약 — 정상 JSON")
    print("=" * 74)
    parsed = FileSuggestion.model_validate(SAMPLE_SUGGESTION)
    assert parsed.category is Category.ASSIGNMENT
    passed += 1
    print(f"  OK   category={parsed.category.value!r}  filename={parsed.recommended_filename!r}")

    check_ok("AnalysisInput + RAG 예시 2건", lambda: AnalysisInput(
        file=FileRef(**SAMPLE_FILE),
        first_page_text="관계형 데이터베이스 정규화 과제 ...",
        similar_examples=[
            RetrievedExample(file_name="a.pdf", category=Category.ASSIGNMENT,
                             first_page_text="정규화 실습", score=0.88),
            RetrievedExample(file_name="b.md", category=Category.LECTURE,
                             first_page_text="정규화 강의", score=0.71),
        ]))
    check_ok("OrganizeResponse 중첩", lambda: OrganizeResponse(
        total_files=2, success_count=1, elapsed_ms=4300,
        suggestions=[SuggestionItem(current=FileRef(**SAMPLE_FILE), suggestion=parsed)],
        failed=[FailedFile(path="files/Desktop/스캔.pdf", reason="pdf_error: 텍스트 레이어 없음")]))

    print()
    print("=" * 74)
    print("[테스트 3] ②③ LLM 출력 계약 — 잘못된 응답 차단")
    print("=" * 74)
    bad_cases = [
        ("Enum 밖 category", {**SAMPLE_SUGGESTION, "category": "homework"}),
        ("빈 recommended_folder", {**SAMPLE_SUGGESTION, "recommended_folder": ""}),
        ("confidence 1.5", {**SAMPLE_SUGGESTION, "confidence": 1.5}),
        ("confidence -0.1", {**SAMPLE_SUGGESTION, "confidence": -0.1}),
        ("필드 누락", {k: v for k, v in SAMPLE_SUGGESTION.items() if k != "confidence"}),
        ("reason 200자 초과", {**SAMPLE_SUGGESTION, "reason": "가" * 201}),
        ("계약에 없는 필드", {**SAMPLE_SUGGESTION, "note": "extra"}),
        ("파일명에 경로 문자", {**SAMPLE_SUGGESTION, "recommended_filename": "a/b.pdf"}),
        ("파일명에 확장자 없음", {**SAMPLE_SUGGESTION, "recommended_filename": "보고서"}),
        ("절대 경로 폴더", {**SAMPLE_SUGGESTION, "recommended_folder": "C:/Windows"}),
        ("상위 경로 참조", {**SAMPLE_SUGGESTION, "recommended_folder": "../../etc"}),
    ]
    for label, payload in bad_cases:
        check_error(label, lambda p=payload: FileSuggestion.model_validate(p))

    check_ok("기획안 대상 확장자(docx)",
             lambda: FileRef(**{**SAMPLE_FILE, "extension": "docx"}))
    check_ok("기획안 대상 확장자(hwp)",
             lambda: FileRef(**{**SAMPLE_FILE, "extension": "hwp"}))
    # doc·ppt는 3주차에 olefile 직접 파싱으로 지원 범위에 들어왔다.
    check_ok("기획안 대상 확장자(doc)",
             lambda: FileRef(**{**SAMPLE_FILE, "extension": "doc"}))
    check_ok("기획안 대상 확장자(ppt)",
             lambda: FileRef(**{**SAMPLE_FILE, "extension": "ppt"}))
    check_error("범위 밖 확장자(png)",
                lambda: FileRef(**{**SAMPLE_FILE, "extension": "png"}))
    check_error("범위 밖 확장자(txt)",
                lambda: FileRef(**{**SAMPLE_FILE, "extension": "txt"}))
    check_error("승인 없는 파일 변경 요청", lambda: ApplyRequest(
        approved=False, root="C:/Users/a/Downloads",
        items=[ApplyItem(source_path="a.pdf", target_folder="lecture", target_filename="b.pdf")]))
    check_ok("승인된 파일 변경 요청", lambda: ApplyRequest(
        approved=True, root="C:/Users/a/Downloads",
        items=[ApplyItem(source_path="a.pdf", target_folder="lecture", target_filename="b.pdf")]))
    check_ok("추천 요청 기본값(mode 생략)",
             lambda: OrganizeRequest(path="C:/Users/a/Documents"))
    check_ok("추천 요청 slim 모드",
             lambda: OrganizeRequest(path="C:/Users/a/Documents", mode="slim"))
    check_error("추천 요청 모르는 mode",
                lambda: OrganizeRequest(path="C:/Users/a/Documents", mode="turbo"))
    check_error("추천 요청 max_files 초과",
                lambda: OrganizeRequest(path="C:/Users/a/Documents", max_files=999))

    print()
    print("=" * 74)
    print("[테스트 4] LLM에 넘길 JSON Schema")
    print("=" * 74)
    schema = FileSuggestion.model_json_schema()
    assert set(schema["required"]) == {
        "category", "recommended_folder", "recommended_filename", "confidence", "reason"}
    print(json.dumps(schema, indent=2, ensure_ascii=False)[:900] + "\n  ...")
    passed += 1

    print()
    print("=" * 74)
    print(f"자체 테스트 {passed}건 모두 통과")
    print("=" * 74)
