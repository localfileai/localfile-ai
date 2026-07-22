"""
프론트엔드 개발용 Mock API 라우터입니다.

1주차에는 실제 AI/RAG 결과가 없어도 FE가 화면 연동을 진행할 수 있어야 하므로,
문서 질문/답변과 추천 폴더/파일명 형태의 더미 데이터를 반환합니다.
"""

from fastapi import APIRouter

router = APIRouter()


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
