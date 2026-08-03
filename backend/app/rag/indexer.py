"""사용자 폴더 색인기 (기능① 검색을 실파일로 여는 마지막 조각).

BE2의 추출 서비스로 첫 페이지 텍스트를 뽑아 임베딩하고, 합성 데이터셋과
분리된 `user_documents` 컬렉션에 넣는다. 이 컬렉션에 문서가 생기는 순간부터
`GET /search`는 사용자 파일을 대상으로 동작한다 (`search._active_collection`).

설계 결정
  - **백그라운드 1개 작업만**: 임베딩이 파일당 CPU 4.6초라(ADR-0002) 동기 API로는
    타임아웃 난다. 스레드 하나로 돌리고 진행률을 `GET /index/status`로 노출한다.
    Ollama가 요청을 직렬 처리하므로 색인 중 검색은 느려진다 — 이것도 status에 표시.
  - **증분**: 문서 id = 파일 절대 경로. mtime이 같으면 임베딩을 건너뛴다.
    (파일 삭제 감지·실시간 감시는 계획서상 BE2의 Watchdog 몫이라 여기 없다)
  - **저사양 보호**: 한 번에 max_files 상한. 실패 파일은 이유와 함께 기록하고 계속.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from ..contracts.ai import MAX_FIRST_PAGE_CHARS
from ..extraction.service import extract_from_path
from .search import user_collection

# 한 번의 collection.add에 보낼 문서 수. embed_dataset.py의 배치와 같은 크기.
BATCH_SIZE = 16


class IndexerBusy(RuntimeError):
    """이미 색인 작업이 돌고 있다."""


_lock = threading.Lock()
_state: dict = {
    "running": False,
    "path": "",
    "total": 0,        # 이번 작업 대상 파일 수
    "done": 0,         # 임베딩 완료(신규+갱신)
    "skipped": 0,      # mtime 동일로 건너뜀
    "failed": [],      # [{path, reason}]
    "started_at": None,
    "finished_at": None,
    "error": "",       # 작업 전체를 중단시킨 오류
}


def status() -> dict:
    """진행률 스냅샷. 리스트는 복사해서 돌려준다."""
    with _lock:
        snapshot = dict(_state)
        snapshot["failed"] = list(_state["failed"])
        return snapshot


def _run(path: str, max_files: int) -> None:
    collection = user_collection(create=True)
    try:
        items = extract_from_path(path, max_chars=MAX_FIRST_PAGE_CHARS)[:max_files]
        with _lock:
            _state["total"] = len(items)

        for offset in range(0, len(items), BATCH_SIZE):
            batch = items[offset:offset + BATCH_SIZE]

            ids, documents, metadatas = [], [], []
            for item in batch:
                if item["error"]:
                    with _lock:
                        _state["failed"].append(
                            {"path": item["path"], "reason": item["error"][:180]})
                    continue
                text = (item["normalized_text"] or item["raw_text"]).strip()
                if not text:
                    with _lock:
                        _state["failed"].append(
                            {"path": item["path"], "reason": "empty_text"})
                    continue

                file_path = Path(item["path"])
                # float mtime은 ChromaDB 저장을 거치며 마지막 비트가 흔들려
                # 동등 비교가 깨진다(실측). 정수 마이크로초로 저장한다.
                mtime_us = file_path.stat().st_mtime_ns // 1_000 if file_path.is_file() else 0
                ids.append(str(file_path))
                documents.append(text)
                metadatas.append({
                    "source": "user",
                    "current_name": item["name"],
                    "current_path": str(file_path),
                    "extension": str(item["extension"]).lstrip("."),
                    "mtime_us": mtime_us,
                    "indexed_at": datetime.now().isoformat(timespec="seconds"),
                })

            if not ids:
                continue

            # 증분: 이미 같은 mtime으로 색인된 파일은 임베딩하지 않는다.
            existing = collection.get(ids=ids)
            unchanged = set()
            for known_id, known_meta in zip(existing.get("ids", []),
                                            existing.get("metadatas", []) or []):
                position = ids.index(known_id)
                if (known_meta or {}).get("mtime_us") == metadatas[position]["mtime_us"]:
                    unchanged.add(known_id)

            fresh = [i for i, id_ in enumerate(ids) if id_ not in unchanged]
            with _lock:
                _state["skipped"] += len(ids) - len(fresh)

            if fresh:
                # upsert: 같은 경로가 다시 오면 갱신된다 (이름은 같고 내용이 바뀐 파일).
                collection.upsert(
                    ids=[ids[i] for i in fresh],
                    documents=[documents[i] for i in fresh],
                    metadatas=[metadatas[i] for i in fresh],
                )
            with _lock:
                _state["done"] += len(fresh)
    except Exception as exc:
        with _lock:
            _state["error"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        with _lock:
            _state["running"] = False
            _state["finished_at"] = datetime.now().isoformat(timespec="seconds")


def start(path: str, max_files: int = 500) -> dict:
    """백그라운드 색인을 시작한다. 이미 돌고 있으면 IndexerBusy.

    경로 검증(존재하는 파일/폴더인가)은 호출 전에 끝나 있어야 한다 —
    라우터가 extract 계층의 FileNotFoundError를 400으로 바꿔 주도록
    여기서 미리 존재 확인만 한다.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(str(target))

    with _lock:
        if _state["running"]:
            raise IndexerBusy(f"이미 색인 중입니다: {_state['path']}")
        _state.update({
            "running": True, "path": str(target),
            "total": 0, "done": 0, "skipped": 0, "failed": [],
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None, "error": "",
        })

    thread = threading.Thread(target=_run, args=(str(target), max_files),
                              name="user-indexer", daemon=True)
    thread.start()
    return status()
