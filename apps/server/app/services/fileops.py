"""
파일 시스템 관련 기능을 모아둔 서비스 파일입니다.

현재 1주차 BE2 범위에서는 PDF/TXT/MD 텍스트 추출이 핵심입니다.
`move_and_rename`은 3주차 실제 파일 이동 기능을 위해 남겨둔 보조 함수입니다.
"""

from pathlib import Path
import shutil
from typing import Dict, Iterable, List, Tuple


# 첫 페이지/텍스트 추출을 지원하는 확장자 목록입니다.
SUPPORTED_TEXT_EXTENSIONS = {".pdf", ".txt", ".md"}


def is_supported_text_file(path: Path) -> bool:
    """전처리 대상 파일인지 확장자 기준으로 확인합니다."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS


def extract_first_page_text(file_path: str) -> str:
    """지원 문서에서 추출할 텍스트를 반환합니다."""
    path = Path(file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(str(path))
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            # PyMuPDF는 PDF를 실제로 열 때만 import해서 서버 시작을 가볍게 유지합니다.
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required to extract PDF text.") from exc

        doc = fitz.open(str(path))
        try:
            if doc.page_count == 0:
                return ""
            return doc.load_page(0).get_text("text").strip()
        finally:
            # PDF 파일 핸들이 남지 않도록 항상 닫습니다.
            doc.close()

    if suffix in {".txt", ".md"}:
        # 텍스트 파일은 인코딩 문제가 있어도 가능한 만큼 읽도록 errors="ignore"를 둡니다.
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    raise ValueError(f"Unsupported file type: {suffix}")


def iter_supported_files(target_path: str) -> Iterable[Path]:
    """파일 하나 또는 폴더에서 지원하는 문서 파일만 순서대로 반환합니다."""
    path = Path(target_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.is_file():
        if is_supported_text_file(path):
            yield path
        return
    if not path.is_dir():
        raise ValueError(f"Not a file or directory: {path}")

    for child in sorted(path.iterdir()):
        if is_supported_text_file(child):
            yield child


def extract_from_path(target_path: str, max_chars: int = 1000) -> List[Dict[str, str]]:
    """경로에서 추출한 문서 정보를 API 응답에 쓰기 좋은 dict 리스트로 만듭니다."""
    results = []
    for file_path in iter_supported_files(target_path):
        try:
            text = extract_first_page_text(str(file_path))
            results.append({
                "path": str(file_path),
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "text": text[:max_chars],
                "error": "",
            })
        except Exception as exc:
            # 한 파일에서 실패해도 전체 폴더 처리는 계속하기 위해 파일별 error에 담습니다.
            results.append({
                "path": str(file_path),
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "text": "",
                "error": str(exc),
            })
    return results


def move_and_rename(src: str, dest_dir: str, new_name: str) -> Tuple[str, str]:
    """파일을 대상 폴더로 이동하면서 새 이름으로 변경합니다."""
    s = Path(src)
    d = Path(dest_dir)

    # 대상 폴더가 없으면 먼저 만들어 실제 파일 이동이 실패하지 않게 합니다.
    d.mkdir(parents=True, exist_ok=True)
    target = d / new_name

    shutil.move(str(s), str(target))
    return str(s), str(target)
