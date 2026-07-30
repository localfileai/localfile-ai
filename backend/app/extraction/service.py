"""
파일 시스템 관련 기능을 모아둔 서비스 파일입니다. (BE2)

기획안 3장이 요구한 대상 확장자에 맞춥니다.
  > "사용자가 선택한 폴더의 PDF, DOCX, DOC, HWP, HWPX, PPT, PPTX 파일 탐색"

초기에는 PDF/TXT/MD를 대상으로 잡았으나, 대학생이 실제로 다루는 문서는
강의자료·과제·발표자료라 txt·md를 빼고 기획안 목록으로 바로잡았습니다. (BE1 결정)

지원 방식
  pdf            PyMuPDF로 첫 페이지만
  docx · pptx    zip + XML 파싱 (외부 라이브러리 없이)
  hwpx           zip + XML 파싱
  hwp            olefile로 BodyText 스트림 디코딩

지원하지 않는 것과 이유
  doc · ppt      구형 OLE 이진 포맷. 표준 파서가 없어 외부 변환 도구(LibreOffice 등)가
                 필요합니다. 기획안이 "스캔 PDF·이미지는 초기 MVP 범위에서 제외"한 것과
                 같은 이유로 4주 일정에서는 뺍니다.
  txt · md       대상 문서가 아닙니다.
"""

from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, Iterable, List


# 첫 페이지/텍스트 추출을 지원하는 확장자 목록입니다.
SUPPORTED_TEXT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".hwpx", ".hwp"}

# zip + XML 구조라서 같은 방식으로 읽는 포맷들.
# 각 값은 본문이 들어 있는 zip 내부 경로의 접두사입니다.
ZIP_XML_FORMATS = {
    ".docx": ("word/document.xml",),
    ".pptx": ("ppt/slides/slide",),
    ".hwpx": ("Contents/section",),
}

# PDF에는 fi, fl 같은 글자를 하나의 특수문자로 저장하는 경우가 있습니다.
# 검색/임베딩에는 일반 알파벳이 더 안정적이므로 추출 후 바꿔줍니다.
LIGATURE_MAP = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}


def is_supported_text_file(path: Path) -> bool:
    """전처리 대상 파일인지 확장자 기준으로 확인합니다."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS


def normalize_ligatures(text: str) -> str:
    """PDF 합자 문자를 검색하기 쉬운 일반 알파벳으로 바꿉니다."""
    for source, target in LIGATURE_MAP.items():
        text = text.replace(source, target)
    return text


def normalize_pdf_text(text: str) -> str:
    """검색/임베딩에 쓰기 좋게 PDF 추출 텍스트를 정리합니다."""
    # 서로 다른 유니코드 표현을 표준 형태로 맞춰 검색 누락 가능성을 줄입니다.
    text = unicodedata.normalize("NFKC", text)
    text = normalize_ligatures(text)

    # 줄 끝 하이픈 때문에 끊긴 영어 단어만 다시 붙입니다. 예: en-\nables -> enables
    text = re.sub(r"([A-Za-z])-+\s*\n\s*([A-Za-z])", r"\1\2", text)

    # 하이픈이 없는 일반 줄바꿈은 삭제하지 않고 공백으로 바꿉니다.
    # 예: Distributed\nSystems -> Distributed Systems
    text = re.sub(r"\s*\n\s*", " ", text)

    # PDF 좌표 추출 과정에서 생긴 중복 공백을 하나로 줄입니다.
    text = re.sub(r"[ \t]+", " ", text)

    # 너무 많은 빈 줄은 문단 구분 두 줄까지만 남깁니다.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def truncate_text(text: str, max_chars: int) -> str:
    """긴 텍스트를 단어 중간이 아닌 마지막 공백 기준으로 자연스럽게 자릅니다."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")

    # 너무 앞에서 끊기면 정보가 과하게 줄어드니, 충분히 뒤쪽 공백일 때만 공백 기준으로 자릅니다.
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]

    return truncated.rstrip()


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

    if suffix in ZIP_XML_FORMATS:
        return _extract_zip_xml_text(path, ZIP_XML_FORMATS[suffix])

    if suffix == ".hwp":
        return _extract_hwp_text(path)

    raise ValueError(f"Unsupported file type: {suffix}")


# ---------------------------------------------------------------------
# zip + XML 계열 (docx · pptx · hwpx)
# ---------------------------------------------------------------------

def _xml_text(xml_bytes: bytes) -> str:
    """XML에서 사람이 읽는 텍스트 노드만 순서대로 모읍니다.

    포맷마다 태그 이름이 달라(w:t, a:t, hp:t …) 태그를 특정하지 않고
    모든 노드의 text를 훑습니다. 서식 태그는 text가 비어 있어 자연히 걸러집니다.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""

    parts = []
    for element in root.iter():
        if element.text and element.text.strip():
            parts.append(element.text.strip())
    return " ".join(parts)


def _extract_zip_xml_text(path: Path, prefixes: tuple[str, ...]) -> str:
    """docx · pptx · hwpx에서 본문 XML을 찾아 텍스트를 뽑습니다."""
    try:
        with zipfile.ZipFile(path) as archive:
            # 슬라이드·구역이 여러 개인 경우가 있어 이름순으로 모읍니다.
            names = sorted(
                name for name in archive.namelist()
                if any(name.startswith(prefix) for prefix in prefixes)
                and name.lower().endswith(".xml")
            )
            if not names:
                return ""
            return " ".join(_xml_text(archive.read(name)) for name in names).strip()
    except zipfile.BadZipFile as exc:
        raise ValueError(f"손상되었거나 형식이 다른 파일입니다: {path.name}") from exc


# ---------------------------------------------------------------------
# 한글 문서 (hwp)
# ---------------------------------------------------------------------

def _extract_hwp_text(path: Path) -> str:
    """HWP(구형 OLE 포맷)의 BodyText 스트림에서 텍스트를 뽑습니다."""
    try:
        import olefile
    except ImportError as exc:
        raise RuntimeError(
            "HWP를 읽으려면 olefile이 필요합니다: python -m pip install olefile"
        ) from exc

    try:
        ole = olefile.OleFileIO(str(path))
    except OSError as exc:
        raise ValueError(f"손상되었거나 형식이 다른 파일입니다: {path.name}") from exc

    try:
        streams = [
            "/".join(entry)
            for entry in ole.listdir()
            if len(entry) >= 2 and entry[0] == "BodyText" and entry[1].startswith("Section")
        ]
        parts = []
        for name in sorted(streams):
            raw = ole.openstream(name).read()
            text = raw.decode("utf-16le", errors="ignore")
            # 제어 문자와 서식 코드가 섞여 나오므로 걸러냅니다.
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
            if text.strip():
                parts.append(text.strip())
        return " ".join(parts).strip()
    finally:
        ole.close()


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

    # 샘플 문서가 `mock/pdf/...`처럼 하위 폴더에 있을 수 있어 재귀적으로 찾습니다.
    # 정렬해서 반환하면 같은 폴더를 여러 번 실행해도 결과 순서가 안정적입니다.
    for child in sorted(path.rglob("*")):
        if is_supported_text_file(child):
            yield child


def extract_from_path(target_path: str, max_chars: int = 1000) -> List[Dict[str, str]]:
    """경로에서 추출한 문서 정보를 API 응답에 쓰기 좋은 dict 리스트로 만듭니다."""
    results = []
    for file_path in iter_supported_files(target_path):
        try:
            raw_text = extract_first_page_text(str(file_path))
            normalized_text = normalize_pdf_text(raw_text)
            preview_text = truncate_text(normalized_text, max_chars)
            results.append({
                "path": str(file_path),
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "raw_text": truncate_text(raw_text, max_chars),
                "normalized_text": truncate_text(normalized_text, max_chars),
                "preview_text": preview_text,
                "error": "",
            })
        except Exception as exc:
            # 한 파일에서 실패해도 전체 폴더 처리는 계속하기 위해 파일별 error에 담습니다.
            results.append({
                "path": str(file_path),
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "raw_text": "",
                "normalized_text": "",
                "preview_text": "",
                "error": str(exc),
            })
    return results
