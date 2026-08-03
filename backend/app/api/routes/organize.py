"""파일 분류·파일명 추천 API (BE1 기능②③, 3주차).

`/mock/rename`·`/mock/move`(하드코딩)와 달리 **실제 추천 경로**다.
  추출(BE2 extraction) → RAG 조회(retrieve) → LLM 생성(llm.client)
  → Pydantic 검증 + 1회 재시도(llm.suggest) → `OrganizeResponse`

실제 파일 변경은 여기서 하지 않는다. FE가 이 응답으로 '미리보기 표'를 그리고,
사용자 승인 후의 이동/이름 변경은 BE2의 apply API(계획서 3주차 BE2 항목) 몫이다.
"""

from __future__ import annotations

import time
from datetime import datetime
from functools import partial
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...contracts.ai import (
    MAX_FIRST_PAGE_CHARS,
    FailedFile,
    FileRef,
    OrganizeRequest,
    OrganizeResponse,
    SuggestionItem,
)
from ...core import config
from ...extraction.service import extract_from_path
from ...llm import client as llm_client
from ...llm.suggest import suggest_full, suggest_slim
from ...rag.retrieve import RagContext, SearchUnavailable, retrieve_context
from ...rag.search import index_status

router = APIRouter(prefix="/organize", tags=["organize"])


def _short(text: str, limit: int = 180) -> str:
    """FailedFile.reason 계약(최대 200자)에 맞춘다."""
    return " ".join(str(text).split())[:limit]


def _to_file_ref(item: dict) -> FileRef:
    path = Path(item["path"])
    size_bytes = 0
    modified_at: datetime | None = None
    if path.is_file():
        stat = path.stat()
        size_bytes = stat.st_size
        modified_at = datetime.fromtimestamp(stat.st_mtime)
    return FileRef(
        path=str(path),
        name=item["name"],
        extension=str(item["extension"]).lstrip("."),
        size_bytes=size_bytes,
        modified_at=modified_at,
    )


@router.get("/status")
async def organize_status():
    """추천 경로 준비 상태. FE가 왜 추천이 안 되는지 표시할 때 쓴다."""
    mode = config.RECOMMEND_MODE_DEFAULT
    model = (config.OLLAMA_GENERATE_MODEL_SLIM if mode == "slim"
             else config.OLLAMA_GENERATE_MODEL)
    ready, detail = llm_client.check_generate_model(model)
    return {
        "ready": ready,
        "mode_default": mode,
        "generate_model": config.OLLAMA_GENERATE_MODEL,
        "generate_model_slim": config.OLLAMA_GENERATE_MODEL_SLIM,
        "detail": detail,
        # slim 모드와 RAG 예시 주입은 색인에 의존한다.
        "index": index_status(),
    }


@router.post("", response_model=OrganizeResponse)
async def organize(request: OrganizeRequest) -> OrganizeResponse:
    """경로의 문서를 분석해 분류·파일명 추천을 만든다. 파일은 변경하지 않는다."""
    started = time.perf_counter()

    mode = request.mode or config.RECOMMEND_MODE_DEFAULT
    model = (config.OLLAMA_GENERATE_MODEL_SLIM if mode == "slim"
             else config.OLLAMA_GENERATE_MODEL)

    ready, detail = llm_client.check_generate_model(model)
    if not ready:
        raise HTTPException(status_code=503, detail=detail)

    try:
        extracted = extract_from_path(request.path, max_chars=MAX_FIRST_PAGE_CHARS)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    generate_fn = partial(llm_client.generate, model=model)

    suggestions: list[SuggestionItem] = []
    failed: list[FailedFile] = []
    rag_unavailable_reason = ""

    for item in extracted[: request.max_files]:
        if item["error"]:
            failed.append(FailedFile(path=item["path"], reason=_short(item["error"])))
            continue

        text = item["normalized_text"] or item["raw_text"]
        if not text.strip():
            failed.append(FailedFile(path=item["path"], reason="empty_text: 추출된 텍스트가 없습니다"))
            continue

        try:
            file_ref = _to_file_ref(item)
        except Exception as exc:
            failed.append(FailedFile(path=item["path"], reason=_short(f"contract_error: {exc}")))
            continue

        # RAG 조회 — 예시(few-shot)와 k-NN 분류를 임베딩 질의 한 번으로 얻는다.
        context = RagContext()
        if request.use_rag or mode == "slim":
            try:
                context = retrieve_context(text, exclude_name=file_ref.name)
            except SearchUnavailable as exc:
                rag_unavailable_reason = str(exc)
            except Exception as exc:
                rag_unavailable_reason = f"RAG 조회 실패: {exc}"

        examples = context.examples if request.use_rag else []

        if mode == "slim":
            # slim은 k-NN 분류가 전제다 (ADR-0002 §5-1). 색인이 없으면 이 파일은 실패 처리.
            if context.knn_category is None:
                failed.append(FailedFile(
                    path=item["path"],
                    reason=_short(f"knn_unavailable: {rag_unavailable_reason or '이웃 문서 없음'}")))
                continue
            result = suggest_slim(
                generate_fn,
                current_name=file_ref.name,
                current_path=str(Path(file_ref.path).parent),
                extension=file_ref.extension,
                first_page_text=text,
                knn_category=context.knn_category,
                knn_vote_ratio=context.knn_vote_ratio,
                examples=examples,
                model_label=model,
            )
        else:
            result = suggest_full(
                generate_fn,
                current_name=file_ref.name,
                current_path=str(Path(file_ref.path).parent),
                extension=file_ref.extension,
                first_page_text=text,
                examples=examples,
            )

        if result.suggestion is None:
            failed.append(FailedFile(path=item["path"], reason=_short(result.error)))
        else:
            suggestions.append(SuggestionItem(current=file_ref, suggestion=result.suggestion))

    return OrganizeResponse(
        total_files=len(extracted[: request.max_files]),
        success_count=len(suggestions),
        suggestions=suggestions,
        failed=failed,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
