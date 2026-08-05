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
  - **최근 파일 우선**: 수정일 역순으로 색인한다. 사용자가 찾는 파일은 대부분
    최근 것이라, 전체 색인이 끝나기 전에도 "체감상 다 되는" 상태가 빨리 온다.
    검색은 색인이 도는 중에도 이미 들어간 문서를 대상으로 동작한다.
  - **임베딩 텍스트 상한**: 임베딩 시간은 글자 수에 비례한다. 첫 페이지(최대
    2,000자)를 다시 INDEX_EMBED_MAX_CHARS(기본 800자)로 줄여 저사양 색인을
    2~3배 당긴다. 주제 판별과 결과 발췌(500자)에는 영향이 없다.
  - **저사양 보호**: 한 번에 max_files 상한. 실패 파일은 이유와 함께 기록하고 계속.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from ..contracts.ai import MAX_FIRST_PAGE_CHARS
from ..core import config
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


def _last_index_file() -> Path:
    from ..core.config import BASE_DIR

    return BASE_DIR / "last_index.json"


def remember_root(path: str, indexed: int) -> None:
    """마지막으로 색인한 폴더를 기록한다. 앱을 다시 켜면 이 폴더로 복원된다."""
    try:
        _last_index_file().write_text(json.dumps({
            "root": path,
            "indexed": indexed,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # 기록에 실패해도 색인 자체는 유효하다


def last_root() -> str:
    """마지막으로 색인한 폴더 경로. 없으면 빈 문자열."""
    try:
        data = json.loads(_last_index_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    root = str(data.get("root", ""))
    # 폴더가 사라졌으면 복원하지 않는다
    return root if root and Path(root).exists() else ""


def status() -> dict:
    """진행률 스냅샷. 리스트는 복사해서 돌려준다."""
    with _lock:
        snapshot = dict(_state)
        snapshot["failed"] = list(_state["failed"])

    # 화면의 진행 바는 "처리한 파일 수"로 그려야 한다. done만 쓰면 증분 색인에서
    # 대부분이 skipped로 빠져 0에 멈춘 것처럼 보인다.
    processed = snapshot["done"] + snapshot["skipped"]
    snapshot["processed"] = processed

    # 남은 시간 추정. 처리 속도가 잡히기 전에는 None을 준다(화면이 0분이라 하지 않게).
    elapsed = 0.0
    if snapshot["started_at"]:
        try:
            elapsed = max(0.0, (datetime.now()
                                - datetime.fromisoformat(snapshot["started_at"])).total_seconds())
        except ValueError:
            elapsed = 0.0
    snapshot["elapsed_sec"] = round(elapsed, 1)

    eta = None
    if snapshot["running"] and processed > 0 and snapshot["total"] > processed and elapsed > 1:
        eta = (snapshot["total"] - processed) * (elapsed / processed)
    snapshot["eta_sec"] = round(eta) if eta is not None else None

    snapshot["last_root"] = last_root()
    return snapshot


def _record_failure(path: str, reason: str) -> None:
    with _lock:
        _state["failed"].append({"path": path, "reason": str(reason)[:180]})


def _upsert_batch(collection, ids: list, documents: list, metadatas: list) -> int:
    """한 묶음을 색인하고 실제로 들어간 건수를 돌려준다.

    묶음 하나가 실패해도 색인 전체를 포기하지 않는다. 예전에는 여기서 난 예외가
    _run 전체를 빠져나가, 임베딩 요청 한 번만 실패해도 **한 건도 색인되지 않은 채**
    "색인 완료"가 됐다. 그러면 화면에는 폴더 안 파일이 다 보이는데 검색만 죽어 있어
    사용자가 원인을 알 방법이 없다.

    묶음이 실패하면 한 건씩 다시 시도한다. 문제 있는 파일 하나 때문에 같이 묶인
    멀쩡한 15건을 버리지 않기 위해서다.
    """
    try:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)
    except Exception as batch_error:
        stored = 0
        for position, id_ in enumerate(ids):
            try:
                collection.upsert(ids=[id_], documents=[documents[position]],
                                  metadatas=[metadatas[position]])
                stored += 1
            except Exception as file_error:
                _record_failure(id_, f"{type(file_error).__name__}: {file_error}")
        if stored == 0:
            # 묶음도 개별도 다 실패했다 — 파일 문제가 아니라 임베딩 쪽 문제다.
            # 이유를 남겨야 화면이 "왜 안 되는지"를 말할 수 있다.
            with _lock:
                if not _state["error"]:
                    _state["error"] = (
                        f"문서를 읽어 들이지 못했습니다 "
                        f"({type(batch_error).__name__}: {batch_error})"[:300])
        return stored


def _run(path: str, max_files: int) -> None:
    collection = user_collection(create=True)
    try:
        items = extract_from_path(path, max_chars=MAX_FIRST_PAGE_CHARS)

        # 최근 수정 파일부터. max_files에 걸려 잘려도 최신 파일이 우선 포함된다.
        def modified_at(item: dict) -> float:
            file_path = Path(item["path"])
            return file_path.stat().st_mtime if file_path.is_file() else 0.0

        items.sort(key=modified_at, reverse=True)
        items = items[:max_files]
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

                # 파일명과 상위 폴더명을 본문 앞에 붙인다.
                # 본문만 임베딩하면 "파일명 그대로 넣어도 못 찾는" 상태가 된다 —
                # 사람은 기억나는 파일명으로도 찾으므로 파일명 자체가 검색 대상이어야 한다.
                label = file_path.stem.replace("_", " ").replace("-", " ")
                parent = file_path.parent.name
                text = f"{label}\n{parent}\n{text}".strip()

                # 임베딩 시간은 글자 수에 비례한다 — 상한을 걸어 저사양 색인을 당긴다.
                # 파일명을 붙인 **뒤에** 자른다. 앞에서 자르면 상한을 넘겨 버린다.
                text = text[:config.INDEX_EMBED_MAX_CHARS]
                # float mtime은 ChromaDB 저장을 거치며 마지막 비트가 흔들려
                # 동등 비교가 깨진다(실측). 정수 마이크로초로 저장한다.
                mtime_us = file_path.stat().st_mtime_ns // 1_000 if file_path.is_file() else 0
                ids.append(str(file_path))
                documents.append(text)
                metadatas.append({
                    "source": "user",
                    # 검색을 "지금 고른 폴더"로 한정하는 기준.
                    # 이게 없으면 예전에 색인한 다른 폴더 파일이 결과에 섞인다.
                    "root": path,
                    "current_name": item["name"],
                    "current_path": str(file_path),
                    "extension": str(item["extension"]).lstrip("."),
                    "mtime_us": mtime_us,
                    "indexed_at": datetime.now().isoformat(timespec="seconds"),
                })

            if not ids:
                continue

            # 증분: 이미 같은 mtime으로 색인된 파일은 임베딩하지 않는다.
            # 이 조회가 실패하면 "전부 새 파일"로 보고 그냥 다시 색인한다 —
            # 건너뛰기는 최적화일 뿐이라, 여기서 색인을 멈출 이유가 없다.
            unchanged = set()
            try:
                existing = collection.get(ids=ids)
                for known_id, known_meta in zip(existing.get("ids", []),
                                                existing.get("metadatas", []) or []):
                    position = ids.index(known_id)
                    if (known_meta or {}).get("mtime_us") == metadatas[position]["mtime_us"]:
                        unchanged.add(known_id)
            except Exception:
                pass

            fresh = [i for i, id_ in enumerate(ids) if id_ not in unchanged]
            with _lock:
                _state["skipped"] += len(ids) - len(fresh)

            if fresh:
                # upsert: 같은 경로가 다시 오면 갱신된다 (이름은 같고 내용이 바뀐 파일).
                stored = _upsert_batch(
                    collection,
                    ids=[ids[i] for i in fresh],
                    documents=[documents[i] for i in fresh],
                    metadatas=[metadatas[i] for i in fresh],
                )
                with _lock:
                    _state["done"] += stored
    except Exception as exc:
        with _lock:
            # 사용자에게 그대로 보이는 문구다. 예외 이름만 던지면 아무 도움이 안 된다.
            _state["error"] = (
                f"폴더를 읽는 중 문제가 생겨 검색 준비를 끝내지 못했습니다 "
                f"({type(exc).__name__}: {exc})"[:300])
    finally:
        with _lock:
            _state["running"] = False
            _state["finished_at"] = datetime.now().isoformat(timespec="seconds")
            indexed = _state["done"] + _state["skipped"]
            failed_before_start = bool(_state["error"])
        # 앱을 다시 켰을 때 이 폴더로 돌아오게 한다 — "폴더를 고르지도 않았는데
        # 검색 준비 완료"로 보이던 혼란이 여기서 사라진다.
        if indexed and not failed_before_start:
            remember_root(path, indexed)


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
