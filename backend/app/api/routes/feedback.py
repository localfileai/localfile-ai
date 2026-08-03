"""사용자 피드백 API (기능②③ 맞춤화, BE1 3주차).

사용자가 미리보기에서 승인·수정한 분류 결과를 라벨 예시로 저장한다.
저장된 예시는 분류(classify.py)에서 라벨 정의문보다 우선 참조된다 —
쓸수록 그 사용자의 진짜 파일·관례에 맞춰지는 구조다.

모델 학습이 아니다: 가중치는 그대로고 참조 자료만 쌓인다. 그래서 저사양에서도
비용이 없고, 잘못 쌓였으면 컬렉션을 비우는 것으로 되돌릴 수 있다.
"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...contracts.ai import FeedbackRequest
from ...core import config
from ...extraction.service import extract_from_path
from ...rag import classify
from ...rag.search import feedback_collection

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/status")
async def feedback_status():
    """쌓인 예시 수. FE가 '맞춤화 진행도'를 보여줄 때 쓴다."""
    collection = feedback_collection()
    count = 0
    if collection is not None:
        try:
            count = collection.count()
        except Exception:
            pass
    return {"examples": count}


@router.post("", status_code=201)
async def record_feedback(request: FeedbackRequest):
    """승인된 분류 1건을 예시로 저장한다. 같은 파일이 다시 오면 갱신된다."""
    text = (request.first_page_text or "").strip()
    if not text:
        try:
            items = extract_from_path(request.path, max_chars=config.INDEX_EMBED_MAX_CHARS)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        usable = [item for item in items if not item["error"]
                  and (item["normalized_text"] or item["raw_text"]).strip()]
        if not usable:
            raise HTTPException(status_code=400, detail="텍스트를 추출할 수 없는 파일입니다.")
        text = (usable[0]["normalized_text"] or usable[0]["raw_text"]).strip()

    try:
        vector = classify.embed_text(text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"임베딩을 계산할 수 없습니다: {exc}") from exc

    collection = feedback_collection(create=True)
    if collection is None:
        raise HTTPException(status_code=503, detail="피드백 저장소를 열 수 없습니다.")

    file_path = Path(request.path)
    collection.upsert(
        ids=[str(file_path)],
        embeddings=[list(map(float, vector))],
        documents=[text[:config.INDEX_EMBED_MAX_CHARS]],
        metadatas=[{
            "source": "feedback",
            "category": request.category.value,
            "filename": request.filename or file_path.name,
            "approved_at": datetime.now().isoformat(timespec="seconds"),
        }],
    )
    return {"stored": True, "examples": collection.count()}
