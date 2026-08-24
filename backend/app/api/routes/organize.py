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
    MAX_ANALYSIS_CHARS,
    FailedFile,
    FileRef,
    OrganizeRequest,
    OrganizeResponse,
    SuggestionItem,
)
from ...core import config, settings
from ...extraction.service import extract_from_path
from ...llm import client as llm_client
from ...llm.suggest import suggest_full, suggest_slim
from ...rag import classify
from ...rag.retrieve import RagContext, SearchUnavailable, retrieve_context
from ...rag.search import feedback_collection, index_status

router = APIRouter(prefix="/organize", tags=["organize"])


def _short(text: str, limit: int = 180) -> str:
    """FailedFile.reason 계약(최대 200자)에 맞춘다."""
    return " ".join(str(text).split())[:limit]


# auto 모드의 속도 판정 결과 캐시. 프로세스당 한 번만 잰다.
#   None = 아직 안 잼 / "full"·"slim" = 판정 완료
_auto_resolved: dict = {"mode": None, "probe_sec": None}


def _resolve_mode(requested: str | None) -> str:
    """요청 모드(없으면 서버 기본값)를 실제 실행 모드로 확정한다.

    "auto"는 저사양 대응이다 (ADR-0002 §5-1): 16토큰 생성을 한 번 재보고
    임계값(AUTO_SLIM_THRESHOLD_SEC)보다 느리면 slim으로 강등한다.
    GPU 실측은 1초 미만, CPU 실측은 9초 이상이라 경계가 뚜렷하다.
    """
    mode = requested or config.RECOMMEND_MODE_DEFAULT
    if mode != "auto":
        return mode

    if _auto_resolved["mode"] is None:
        try:
            elapsed = llm_client.probe_generation_seconds(settings.generate_model())
        except llm_client.LLMRequestError:
            # 재보기조차 실패할 정도면 저사양·불안정 쪽으로 둔다.
            elapsed = float("inf")
        _auto_resolved["probe_sec"] = None if elapsed == float("inf") else round(elapsed, 2)
        _auto_resolved["mode"] = (
            "slim" if elapsed > config.AUTO_SLIM_THRESHOLD_SEC else "full")
    return _auto_resolved["mode"]


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
             else settings.generate_model())
    ready, detail = llm_client.check_generate_model(model)
    return {
        "ready": ready,
        "mode_default": mode,
        # auto의 판정 결과. 아직 첫 추천 요청 전이면 null이다.
        "mode_resolved": _auto_resolved["mode"],
        "probe_sec": _auto_resolved["probe_sec"],
        "generate_model": settings.generate_model(),
        "generate_model_slim": config.OLLAMA_GENERATE_MODEL_SLIM,
        "detail": detail,
        # slim 모드와 RAG 예시 주입은 색인에 의존한다.
        "index": index_status(),
    }


@router.post("", response_model=OrganizeResponse)
async def organize(request: OrganizeRequest) -> OrganizeResponse:
    """경로의 문서를 분석해 분류·파일명 추천을 만든다. 파일은 변경하지 않는다."""
    started = time.perf_counter()
    stage_seconds = {name: 0.0 for name in
                     ("extract", "embedding", "classify", "rag", "llm")}

    mode = _resolve_mode(request.mode)
    model = (config.OLLAMA_GENERATE_MODEL_SLIM if mode == "slim"
             else settings.generate_model())

    ready, detail = llm_client.check_generate_model(model)
    if not ready:
        raise HTTPException(status_code=503, detail=detail)

    try:
        stage_started = time.perf_counter()
        extracted = extract_from_path(request.path, max_chars=MAX_ANALYSIS_CHARS)
        stage_seconds["extract"] += time.perf_counter() - stage_started
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base_generate = partial(
        llm_client.generate, model=model,
        num_predict=(config.SLIM_NUM_PREDICT if mode == "slim" else None))

    def generate_fn(system: str, prompt: str) -> str:
        stage_started = time.perf_counter()
        try:
            return base_generate(system, prompt)
        finally:
            stage_seconds["llm"] += time.perf_counter() - stage_started

    suggestions: list[SuggestionItem] = []
    failed: list[FailedFile] = []
    rag_unavailable_reason = ""

    # "이어서 분석": FE가 지금까지 분석한 수를 offset으로 보내면 그다음 묶음을
    # 처리한다. 정렬이 실행마다 같아야 이어붙임이 성립한다 — extract_from_path가
    # 경로순으로 돌려주므로 성립.
    for item in extracted[request.offset : request.offset + request.max_files]:
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

        # 임베딩 1회 원칙: 문서 좌표를 한 번 계산해 분류와 RAG 조회가 공유한다.
        # 분류는 전 모드에서 분류기(classify.py)가 담당한다 — 3파전 실측 결과
        # LLM 직접 분류(50%)보다 라벨 정의문 zero-shot(82.8%)이 정확하다.
        vector = None
        try:
            stage_started = time.perf_counter()
            vector = classify.embed_text(text)
        except Exception as exc:
            rag_unavailable_reason = f"임베딩 실패: {exc}"
        finally:
            stage_seconds["embedding"] += time.perf_counter() - stage_started

        decision = None
        if vector is not None:
            stage_started = time.perf_counter()
            decision = classify.classify_vector(vector, feedback_collection())
            stage_seconds["classify"] += time.perf_counter() - stage_started

        context = RagContext()
        if vector is not None and request.use_rag:
            try:
                stage_started = time.perf_counter()
                context = retrieve_context(
                    embedding=vector, exclude_name=file_ref.name)
            except SearchUnavailable as exc:
                rag_unavailable_reason = str(exc)
            except Exception as exc:
                rag_unavailable_reason = f"RAG 조회 실패: {exc}"
            finally:
                stage_seconds["rag"] += time.perf_counter() - stage_started

        examples = context.examples if request.use_rag else []

        if mode == "slim":
            # slim은 분류기 결과가 필수다 (LLM은 파일명만 만들므로).
            if decision is None:
                failed.append(FailedFile(
                    path=item["path"],
                    reason=_short(f"classify_unavailable: {rag_unavailable_reason or '임베딩 불가'}")))
                continue
            result = suggest_slim(
                generate_fn,
                current_name=file_ref.name,
                current_path=str(Path(file_ref.path).parent),
                extension=file_ref.extension,
                first_page_text=text,
                category=decision.category,
                confidence=decision.confidence,
                method=decision.method,
                examples=examples,
                model_label=model,
            )
        else:
            # full: LLM은 파일명·세부 폴더·근거를 만들고, category는 분류기가
            # 덮어쓴다. 분류기를 못 쓰는 상황(임베딩 실패)이면 LLM 출력 그대로 폴백.
            result = suggest_full(
                generate_fn,
                current_name=file_ref.name,
                current_path=str(Path(file_ref.path).parent),
                extension=file_ref.extension,
                first_page_text=text,
                examples=examples,
                category=decision.category if decision else None,
                confidence=decision.confidence if decision else 0.0,
                method=decision.method if decision else "label_zeroshot",
            )

        if result.suggestion is None:
            failed.append(FailedFile(path=item["path"], reason=_short(result.error)))
        else:
            suggestions.append(SuggestionItem(current=file_ref, suggestion=result.suggestion))

    elapsed = time.perf_counter() - started
    measured = sum(stage_seconds.values())
    stages_ms = {name: int(seconds * 1000) for name, seconds in stage_seconds.items()}
    stages_ms["other"] = max(0, int((elapsed - measured) * 1000))
    return OrganizeResponse(
        # 전체 **발견** 수를 준다. 예전에는 상한(max_files)으로 자른 수를 total로
        # 줘서, 파일 80개 폴더를 골라도 화면에 "전체 20개"로 보였고 어떤 파일이
        # 빠졌는지 알 길이 없었다. 이번에 처리한 수는 suggestions+failed로 센다.
        total_files=len(extracted),
        success_count=len(suggestions),
        suggestions=suggestions,
        failed=failed,
        elapsed_ms=int(elapsed * 1000), stages_ms=stages_ms,
    )
