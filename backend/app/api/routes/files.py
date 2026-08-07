"""폴더 안의 문서 목록 (5주차).

"폴더 내 전체 문서" 패널은 **어떤 파일이 있는지**만 보여 주면 된다.
예전에는 이 목록을 만들려고 모든 파일의 첫 페이지 텍스트를 추출했는데,
파일이 수백 개인 폴더에서는 몇 분씩 걸려 화면이 멈춘 것처럼 보였다.
색인기가 어차피 같은 추출을 하므로 두 번 할 이유도 없다.

여기서는 파일 정보만 읽는다 — 폴더가 커도 즉시 끝난다.
"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ...extraction.service import iter_supported_files

router = APIRouter(prefix="/files", tags=["files"])

# 화면 목록의 상한. 이보다 많으면 잘라내고 총 개수를 함께 알려 준다.
MAX_ITEMS = 2000


@router.get("")
async def list_files(path: str = Query(..., min_length=1)):
    """폴더 안(하위 폴더 포함)의 지원 문서를 최근 수정 순으로 나열한다."""
    try:
        found = list(iter_supported_files(path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"경로가 없습니다: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    root = Path(path).expanduser()
    items = []
    for file_path in found:
        try:
            stat = file_path.stat()
        except OSError:
            continue
        try:
            relative = str(file_path.parent.relative_to(root))
        except ValueError:
            relative = ""
        items.append({
            "path": str(file_path),
            "name": file_path.name,
            "extension": file_path.suffix.lower().lstrip("."),
            "folder": "" if relative == "." else relative,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })

    # 최근에 손댄 파일이 위로 — 사용자가 찾는 건 대개 최근 것이다.
    items.sort(key=lambda entry: entry["modified_at"], reverse=True)
    return {"total": len(items), "items": items[:MAX_ITEMS]}
