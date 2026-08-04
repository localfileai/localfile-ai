"""승인된 추천을 실제 파일 이동·개명으로 적용한다 (기능④, BE1 4주차).

기획안 원칙: AI는 제안만 하고, 파일을 실제로 바꾸는 건 사용자가 승인한 뒤다.
이 모듈은 그 "승인 뒤"를 담당한다 — 안전장치가 본체다:

  - 경로 탈출 금지 : 대상 경로가 root 밖으로 나가면 그 항목만 실패 처리
  - 충돌 검사     : 대상에 같은 이름이 이미 있으면 덮어쓰지 않고 건너뜀
  - 파일 단위 격리 : 권한 에러·사용 중 파일이 나와도 나머지 항목은 계속 진행
  - 작업 이력     : 실제로 옮긴 내역을 JSON으로 남겨 되돌리기(undo)를 지원

dry_run=True면 위 검증만 수행하고 파일은 건드리지 않는다 — FE가 적용 전
"몇 건이 실제로 가능한지"를 미리 보여줄 때 쓴다.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from ..contracts.ai import AppliedItem, ApplyItem, ApplyResponse
from ..core.config import BASE_DIR

# 작업 이력 저장 위치. server.exe로 패키징돼도 실행 파일 옆이라 쓰기 가능하다.
HISTORY_DIR = Path(os.getenv("LOCAL_FILE_AI_HISTORY", BASE_DIR / "apply_history"))


def _resolve_root(root: str) -> Path:
    path = Path(root).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"정리 대상 폴더를 찾을 수 없습니다: {root}") from exc
    if not resolved.is_dir():
        raise ValueError(f"폴더가 아닙니다: {root}")
    return resolved


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _apply_one(root: Path, item: ApplyItem, dry_run: bool) -> AppliedItem:
    """항목 1건을 검증·적용한다. 어떤 실패도 예외로 새지 않고 결과에 담긴다."""
    source = Path(item.source_path).expanduser()
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError):
        return AppliedItem(source_path=item.source_path, status="failed",
                           reason="source_missing: 원본 파일이 없습니다")

    if not source.is_file():
        return AppliedItem(source_path=item.source_path, status="failed",
                           reason="not_a_file: 파일만 옮길 수 있습니다")
    if not _is_inside(source, root):
        return AppliedItem(source_path=item.source_path, status="failed",
                           reason="unsafe_path: 원본이 정리 대상 폴더 밖에 있습니다")

    target_dir = (root / item.target_folder).resolve()
    if not _is_inside(target_dir, root):
        return AppliedItem(source_path=item.source_path, status="failed",
                           reason="unsafe_path: 대상 폴더가 정리 대상 폴더 밖입니다")

    target = target_dir / item.target_filename
    if target.suffix.lower() != source.suffix.lower():
        return AppliedItem(source_path=item.source_path, status="failed",
                           reason="extension_mismatch: 확장자는 바꿀 수 없습니다")

    if target == source:
        return AppliedItem(source_path=str(source), target_path=str(target),
                           status="skipped", reason="already_in_place: 이미 제자리입니다")
    if target.exists():
        return AppliedItem(source_path=str(source), target_path=str(target),
                           status="skipped", reason="conflict: 대상에 같은 이름의 파일이 있습니다")

    if dry_run:
        return AppliedItem(source_path=str(source), target_path=str(target), status="valid")

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except PermissionError:
        # 기획안 4주차 '파일 권한 에러 방지' — 사용 중이거나 권한이 없는 파일은
        # 이 항목만 실패로 남기고 나머지는 계속 진행한다.
        return AppliedItem(source_path=str(source), target_path=str(target),
                           status="failed",
                           reason="permission: 파일이 사용 중이거나 권한이 없습니다")
    except OSError as exc:
        return AppliedItem(source_path=str(source), target_path=str(target),
                           status="failed", reason=f"os_error: {exc}"[:200])

    return AppliedItem(source_path=str(source), target_path=str(target), status="moved")


def _write_history(root: Path, moved: list[AppliedItem]) -> str:
    history_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{history_id}.json").write_text(
        json.dumps({
            "id": history_id,
            "root": str(root),
            "applied_at": datetime.now().isoformat(timespec="seconds"),
            "moves": [{"from": item.source_path, "to": item.target_path}
                      for item in moved],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return history_id


def apply_changes(root: str, items: list[ApplyItem], dry_run: bool = False) -> ApplyResponse:
    """승인된 항목들을 적용한다. root가 유효하지 않으면 ValueError."""
    resolved_root = _resolve_root(root)

    results = [_apply_one(resolved_root, item, dry_run) for item in items]
    moved = [r for r in results if r.status == "moved"]

    history_id = _write_history(resolved_root, moved) if moved else ""

    return ApplyResponse(
        total=len(results),
        moved=len(moved) if not dry_run else sum(r.status == "valid" for r in results),
        failed=sum(r.status == "failed" for r in results),
        dry_run=dry_run,
        items=results,
        history_id=history_id,
    )


def list_history(limit: int = 20) -> list[dict]:
    """최근 작업 이력. FE '정리 내역' 화면과 undo 대상 선택에 쓴다."""
    if not HISTORY_DIR.is_dir():
        return []
    entries = []
    for path in sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries.append({
            "id": data.get("id", path.stem),
            "root": data.get("root", ""),
            "applied_at": data.get("applied_at", ""),
            "moves": len(data.get("moves", [])),
            "undone": bool(data.get("undone", False)),
        })
    return entries


def undo(history_id: str = "") -> dict:
    """이동 1회분을 역순으로 되돌린다. id를 안 주면 가장 최근 작업이다.

    되돌릴 수 없는 항목(원래 자리에 다른 파일이 생겼거나, 옮긴 파일이 또
    이동된 경우)은 건너뛰고 이유를 남긴다 — 적용과 같은 파일 단위 격리.
    """
    if not HISTORY_DIR.is_dir():
        raise ValueError("되돌릴 작업 이력이 없습니다.")

    candidates = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    target_file = None
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("undone"):
            continue
        if not history_id or data.get("id") == history_id:
            target_file = (path, data)
            break

    if target_file is None:
        raise ValueError("되돌릴 작업을 찾을 수 없습니다."
                         if history_id else "되돌릴 작업 이력이 없습니다.")

    path, data = target_file
    restored, skipped = 0, []
    for move in reversed(data.get("moves", [])):
        source, target = Path(move["from"]), Path(move["to"])
        if not target.is_file():
            skipped.append({"path": str(target), "reason": "moved_file_missing"})
            continue
        if source.exists():
            skipped.append({"path": str(source), "reason": "original_slot_occupied"})
            continue
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(source))
            restored += 1
        except (PermissionError, OSError) as exc:
            skipped.append({"path": str(target), "reason": f"error: {exc}"[:200]})

    data["undone"] = True
    data["undone_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"id": data.get("id", path.stem), "restored": restored, "skipped": skipped}
