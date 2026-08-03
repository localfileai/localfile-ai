"""
프론트엔드 개발용 Mock API 라우터입니다.

1주차에는 실제 AI/RAG 결과가 없어도 FE가 화면 연동을 진행할 수 있어야 하므로,
문서 질문/답변과 추천 폴더/파일명 형태의 더미 데이터를 반환합니다.

3주차 계약 단일화(docs/contracts-unification.md): Mock 전용 모델은 계약 패키지가
아니라 **이 파일 안에** 둡니다. `contracts/ai.py`의 실제 계약(SearchResponse,
ApplyRequest)과 이름이 겹쳐 import 실수를 유발하던 문제를 없앴습니다.
실제 경로가 전부 연결되면(4주차) 이 라우터와 함께 통째로 제거합니다.
"""

from pathlib import Path
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

# 모든 mock 엔드포인트를 `/mock` 하위로 모읍니다.
router = APIRouter(prefix="/mock", tags=["mock"])


# ---------------------------------------------------------
# Mock 전용 응답 모델 — 이 라우터 밖에서 import하지 마세요.
# 실제 계약은 contracts/ai.py가 단일 기준입니다.
# ---------------------------------------------------------

class MockAnalyzeRequest(BaseModel):
    path: str


class MockAnalyzeResponse(BaseModel):
    original_path: str
    recommended_name: str
    recommended_folder: str
    summary: str
    confidence: float
    tags: List[str]


class SearchItem(BaseModel):
    name: str
    ext: str
    path: str
    modified: str
    score: int
    snippet: str


class SearchResponse(BaseModel):
    count: int
    items: List[SearchItem]


class RenameRecommendation(BaseModel):
    id: int
    old: str
    next: str
    path: str
    ext: str
    confidence: int


class RenameResponse(BaseModel):
    count: int
    items: List[RenameRecommendation]


class MoveRecommendation(BaseModel):
    id: str
    name: str
    from_: str
    to: str
    confidence: int


class MoveResponse(BaseModel):
    current_files: List[dict]
    recommendations: List[MoveRecommendation]


class ApplyRequest(BaseModel):
    ids: List[str]


class ApplyResponse(BaseModel):
    applied: int
    status: str


class ReanalyzeResponse(BaseModel):
    message: str
    rename_count: int
    move_count: int


def build_mock_analyze_response(file_path: str) -> MockAnalyzeResponse:
    """파일 경로 하나를 받아 FE 화면에 보여줄 가짜 분석 결과를 만듭니다."""
    path = Path(file_path)
    stem = path.stem or "분석_문서"
    suffix = path.suffix or ".pdf"

    # 실제 AI가 붙기 전에는 입력 파일 내용과 상관없이 안정적인 더미 값을 반환합니다.
    # 이렇게 응답 구조를 고정해두면 FE가 결과 카드, 로딩 상태, 에러 처리를 먼저 만들 수 있습니다.
    return MockAnalyzeResponse(
        original_path=file_path,
        recommended_name=f"{stem}_정리본{suffix}",
        recommended_folder="업무",
        summary="이 문서는 프로젝트 진행 상황과 다음 작업을 정리한 문서로 가정한 Mock 분석 결과입니다.",
        confidence=0.92,
        tags=["mock", "업무", "자동분류"],
    )


@router.get("/dataset")
async def mock_dataset(limit: int = 5):
    """요청한 개수만큼 프론트엔드 표시용 더미 추천 데이터를 반환합니다."""
    # 지나치게 큰 limit 요청으로 응답이 불필요하게 커지는 것을 막습니다.
    limit = min(max(limit, 1), 100)

    sample = []
    for i in range(1, limit + 1):
        # 실제 RAG/LLM 응답이 붙기 전까지 화면 바인딩용으로 사용할 고정 구조입니다.
        sample.append({
            "id": i,
            "question": "문서의 주제는 무엇인가요?",
            "context": f"예시 문서 텍스트 {i}...",
            "answer": f"문서{i} 문서는 주로 예시 주제에 대해 설명합니다.",
            "recommended_folder": "예시_문서",
            "recommended_name": f"문서{i}_요약.txt",
        })
    return {"count": len(sample), "items": sample}

@router.post(
    "/analyze",
    response_model=MockAnalyzeResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "original_path": "/Users/alex/Documents/report.pdf",
                        "recommended_name": "report_summary.pdf",
                        "recommended_folder": "업무/프로젝트A",
                        "summary": "프로젝트 A의 진행 상황: 데이터 수집 완료, 모델 학습 필요, 배포 계획 수립.",
                        "confidence": 0.91,
                        "tags": ["프로젝트A", "요약", "업무"]
                    }
                }
            }
        }
    },
)
async def mock_analyze(request: MockAnalyzeRequest):
    """FE가 파일 분석 API 연동을 먼저 테스트할 수 있도록 하드코딩된 결과를 반환합니다."""
    return build_mock_analyze_response(request.path)


# --- 추가된 mock endpoints: frontend 샘플 UI에서 필요한 데이터와 동작을 흉내냅니다.

# 간단한 검색 결과 샘플
SEARCH_SAMPLE = [
    {"name": "가치가게_캡스톤_최종발표.pdf", "ext": "PDF", "path": "Documents/대학교/2025/캡스톤", "modified": "2025-06-13", "score": 97, "snippet": "2025년 캡스톤디자인 프로젝트로, 지역 소상공인을 위한 <mark>가치가게</mark> 플랫폼을 개발하였다."},
    {"name": "QR키오스크_설계서.txt", "ext": "TXT", "path": "Documents/프로젝트/QR-Kiosk", "modified": "2025-06-02", "score": 92, "snippet": "JSP, Tomcat, MySQL을 사용한 <mark>QR 키오스크 프로젝트</mark>의 데이터베이스 구조를 정리한다."},
    {"name": "논문학습플랫폼_README.md", "ext": "MD", "path": "Documents/GitHub/paper-learning", "modified": "2025-07-27", "score": 89, "snippet": "PDF 문단 추출, 요약, 퀴즈 생성을 지원하는 <mark>논문 학습 플랫폼</mark> 프로젝트이다."},
    {"name": "TSN_스케줄링_발표자료.pdf", "ext": "PDF", "path": "Documents/연구/TSN", "modified": "2026-06-23", "score": 87, "snippet": "TAS와 CBS+TAS의 지터, 지연, 처리량을 비교하여 <mark>네트워크 스케줄링</mark> 성능을 분석하였다."},
]


@router.get(
    "/search",
    response_model=SearchResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "count": 2,
                        "items": [
                            {
                                "name": "TSN_스케줄링_발표자료.pdf",
                                "ext": "PDF",
                                "path": "Documents/연구/TSN",
                                "modified": "2026-06-23",
                                "score": 87,
                                "snippet": "TAS와 CBS+TAS의 지터 및 처리량 비교 결과를 정리한 발표 자료입니다."
                            },
                            {
                                "name": "논문학습플랫폼_README.md",
                                "ext": "MD",
                                "path": "Documents/프로젝트/Paper-Learning",
                                "modified": "2025-07-27",
                                "score": 89,
                                "snippet": "문단 추출 및 요약 기능 설명이 포함된 README 파일입니다."
                            }
                        ]
                    }
                }
            }
        }
    },
)
async def mock_search(q: str = "", types: str = "", date: str = "all", sort: str = "score"):
    """간단한 쿼리/필터를 흉내낸 검색 결과를 반환합니다. FE의 `searchFiles`를 대체합니다."""
    items = SEARCH_SAMPLE.copy()
    ql = q.lower().strip()
    if ql:
        items = [i for i in items if ql in i["name"].lower() or ql in i["path"].lower() or ql in i["snippet"].lower()]
    if date == "2025":
        items = [i for i in items if i["modified"].startswith("2025")]
    if sort == "recent":
        items.sort(key=lambda x: x["modified"], reverse=True)
    elif sort == "name":
        items.sort(key=lambda x: x["name"])
    else:
        items.sort(key=lambda x: x["score"], reverse=True)
    return {"count": len(items), "items": items}


# 이름 변경 추천 샘플
RENAME_SAMPLE = [
    {"id": 1, "old": "최종.pdf", "next": "가치가게_캡스톤_최종발표_2025.pdf", "path": "대학교/캡스톤", "ext": "PDF", "confidence": 96},
    {"id": 2, "old": "발표자료2.pdf", "next": "TSN_TAS_CBS_성능비교_발표자료.pdf", "path": "연구/TSN", "ext": "PDF", "confidence": 93},
    {"id": 3, "old": "notes.txt", "next": "QR키오스크_DB설계_메모.txt", "path": "프로젝트/QR-Kiosk", "ext": "TXT", "confidence": 90},
    {"id": 4, "old": "readme최종.md", "next": "논문학습플랫폼_README.md", "path": "프로젝트/Paper-Learning", "ext": "MD", "confidence": 88},
]


@router.get(
    "/rename",
    response_model=RenameResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "count": 2,
                        "items": [
                            {"id": 1, "old": "최종.pdf", "next": "가치가게_캡스톤_최종발표_2025.pdf", "path": "대학교/캡스톤", "ext": "PDF", "confidence": 96},
                            {"id": 2, "old": "notes.txt", "next": "QR키오스크_DB설계_메모.txt", "path": "프로젝트/QR-Kiosk", "ext": "TXT", "confidence": 90}
                        ]
                    }
                }
            }
        }
    },
)
async def mock_rename_recommendations():
    return {"count": len(RENAME_SAMPLE), "items": RENAME_SAMPLE}


# 이동 추천 + 현재 파일 트리 샘플
CURRENT_FILES_SAMPLE = [
    {"id": "value", "name": "가치가게_캡스톤_최종발표.pdf", "ext": "PDF", "path": "Documents/다운로드"},
    {"id": "tsn", "name": "TSN_TAS_CBS_성능비교_발표자료.pdf", "ext": "PDF", "path": "Documents/바탕화면"},
    {"id": "qr", "name": "QR키오스크_DB설계_메모.txt", "ext": "TXT", "path": "Documents/다운로드"},
    {"id": "os", "name": "운영체제_기말정리.pdf", "ext": "PDF", "path": "Documents/대학교/2025/강의자료/운영체제"},
    {"id": "data", "name": "데이터통신_변조복조.md", "ext": "MD", "path": "Documents/대학교/2025/강의자료/데이터통신"},
    {"id": "paper", "name": "논문학습플랫폼_README.md", "ext": "MD", "path": "Documents/프로젝트/Paper-Learning"},
    {"id": "speech", "name": "발표코칭앱_기획서.pdf", "ext": "PDF", "path": "Documents/프로젝트/Speech-Coach"},
    {"id": "result", "name": "TSN_실험결과.txt", "ext": "TXT", "path": "Documents/연구/TSN/실험결과"},
]

MOVE_SAMPLE = [
    {"id": "value", "name": "가치가게_캡스톤_최종발표.pdf", "from_": "Documents/다운로드", "to": "Documents/대학교/2025/캡스톤/가치가게", "confidence": 96},
    {"id": "tsn", "name": "TSN_TAS_CBS_성능비교_발표자료.pdf", "from_": "Documents/바탕화면", "to": "Documents/연구/TSN/발표자료", "confidence": 93},
    {"id": "qr", "name": "QR키오스크_DB설계_메모.txt", "from_": "Documents/다운로드", "to": "Documents/프로젝트/QR-Kiosk/설계", "confidence": 90},
]


@router.get(
    "/move",
    response_model=MoveResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "current_files": [{"id": "value", "name": "가치가게_캡스톤_최종발표.pdf", "ext": "PDF", "path": "Documents/다운로드"}],
                        "recommendations": [{"id": "value", "name": "가치가게_캡스톤_최종발표.pdf", "from_": "Documents/다운로드", "to": "Documents/대학교/2025/캡스톤/가치가게", "confidence": 96}]
                    }
                }
            }
        }
    },
)
async def mock_move_recommendations():
    return {"current_files": CURRENT_FILES_SAMPLE, "recommendations": MOVE_SAMPLE}


@router.post(
    "/rename/apply",
    response_model=ApplyResponse,
    responses={
        200: {
            "content": {
                "application/json": {"example": {"applied": 2, "status": "ok"}}
            }
        }
    },
)
async def mock_apply_rename(payload: ApplyRequest):
    """모의로 이름 변경을 적용합니다. 실제 파일 변경은 수행하지 않습니다."""
    ids = payload.ids or []
    return {"applied": len(ids), "status": "ok"}


@router.post(
    "/move/apply",
    response_model=ApplyResponse,
    responses={
        200: {
            "content": {
                "application/json": {"example": {"applied": 2, "status": "ok"}}
            }
        }
    },
)
async def mock_apply_move(payload: ApplyRequest):
    ids = payload.ids or []
    return {"applied": len(ids), "status": "ok"}


@router.post(
    "/reanalyze",
    response_model=ReanalyzeResponse,
    responses={
        200: {
            "content": {
                "application/json": {"example": {"message": "reanalyzed", "rename_count": 4, "move_count": 3}}
            }
        }
    },
)
async def mock_reanalyze():
    """재분석을 흉내내고 변경된 추천 수를 반환합니다."""
    return {"message": "reanalyzed", "rename_count": len(RENAME_SAMPLE), "move_count": len(MOVE_SAMPLE)}
