"""
프론트엔드 개발용 Mock API 라우터입니다.

1주차에는 실제 AI/RAG 결과가 없어도 FE가 화면 연동을 진행할 수 있어야 하므로,
문서 질문/답변과 추천 폴더/파일명 형태의 더미 데이터를 반환합니다.
"""

from pathlib import Path

from fastapi import APIRouter

from ..schemas import MockAnalyzeRequest, MockAnalyzeResponse

router = APIRouter()


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


@router.get("/mock/dataset", tags=["mock"])
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


@router.post("/api/analyze", response_model=MockAnalyzeResponse, tags=["mock"])
async def mock_analyze(request: MockAnalyzeRequest):
    """FE가 파일 분석 API 연동을 먼저 테스트할 수 있도록 하드코딩된 결과를 반환합니다."""
    return build_mock_analyze_response(request.path)
