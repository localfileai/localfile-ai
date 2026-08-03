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
  doc            olefile + [MS-DOC] 조각 테이블(piece table) 파싱, 실패 시 휴리스틱
  ppt            olefile + 레코드 순회로 TextCharsAtom/TextBytesAtom 수집

doc·ppt는 3주차까지 "표준 파서 없음"으로 미지원이었으나, hwp에 이미 쓰는 olefile로
직접 파싱하도록 구현해 기획안 3장의 대상 7종을 모두 지원한다 (BE1 3주차 정합 작업).
암호화되거나 규격을 벗어난 파일은 억지로 읽지 않고 파일 단위 실패로 처리된다.

지원하지 않는 것과 이유
  txt · md       대상 문서가 아닙니다.

저사양 PC 고려: 구형 포맷 스트림은 LEGACY_STREAM_CAP 까지만 읽는다.
첫 페이지 분량 텍스트는 그 안에 반드시 있고, 수백 MB짜리 깨진 파일이
메모리를 다 잡아먹는 사고를 막는다.
"""

from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, Iterable, List


# 첫 페이지/텍스트 추출을 지원하는 확장자 목록입니다. 기획안 3장의 7종 전부.
SUPPORTED_TEXT_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".hwpx", ".hwp"}

# 구형 OLE 포맷 스트림을 읽는 상한. 첫 페이지 텍스트는 이 안에 있다.
LEGACY_STREAM_CAP = 4 * 1024 * 1024

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

    if suffix == ".doc":
        return _extract_doc_text(path)

    if suffix == ".ppt":
        return _extract_ppt_text(path)

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


# ---------------------------------------------------------------------
# 구형 MS Office 이진 포맷 (doc · ppt) — olefile로 직접 파싱
# ---------------------------------------------------------------------

def _open_ole(path: Path):
    try:
        import olefile
    except ImportError as exc:
        raise RuntimeError(
            "doc/ppt를 읽으려면 olefile이 필요합니다: python -m pip install olefile"
        ) from exc
    try:
        return olefile.OleFileIO(str(path))
    except OSError as exc:
        raise ValueError(f"손상되었거나 형식이 다른 파일입니다: {path.name}") from exc


def _read_stream(ole, name: str) -> bytes:
    """OLE 스트림을 상한까지만 읽는다. 없으면 빈 바이트."""
    if not ole.exists(name):
        return b""
    return ole.openstream(name).read(LEGACY_STREAM_CAP)


def _clean_word_text(text: str) -> str:
    """Word 계열 텍스트의 제어·서식 문자를 정리한다."""
    text = text.replace("\r", "\n").replace("\x0b", "\n")
    # 필드 코드(0x13~0x15), 개체 자리표시(0x01, 0x08) 등 제어 문자 제거
    return re.sub(r"[\x00-\x08\x0c\x0e-\x1f]+", " ", text)


def _printable_runs_fallback(data: bytes, min_run: int = 8) -> str:
    """규격 파싱이 실패했을 때의 마지막 수단 — UTF-16LE로 읽어 글자 구간만 남긴다."""
    decoded = data.decode("utf-16le", errors="ignore")
    pattern = r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9 .,()\-_:%/·]{" + str(min_run - 1) + r",}"
    runs = re.findall(pattern, decoded)
    return " ".join(run.strip() for run in runs)


def _doc_text_from_piece_table(word: bytes, table: bytes, budget: int = 8000) -> str:
    """[MS-DOC] 조각 테이블(CLX→PlcPcd)을 따라 본문 텍스트를 앞에서부터 모은다.

    Word 97 이후의 FIB 고정 오프셋을 쓴다: fcClx=0x01A2, lcbClx=0x01A6.
    조각(piece)마다 fCompressed 비트가 8비트(cp1252)/16비트(UTF-16LE)를 구분한다.
    """
    import struct

    if len(word) < 0x01AA or struct.unpack_from("<H", word, 0)[0] != 0xA5EC:
        raise ValueError("FIB 시그니처가 아님")

    fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x01A2)
    if lcb_clx == 0 or fc_clx + lcb_clx > len(table):
        raise ValueError("CLX 범위 이상")
    clx = table[fc_clx:fc_clx + lcb_clx]

    # CLX = (Prc)* Pcdt. Prc(clxt=1)는 건너뛰고 Pcdt(clxt=2)의 PlcPcd를 찾는다.
    offset = 0
    while offset < len(clx):
        clxt = clx[offset]
        if clxt == 1:
            (cb,) = struct.unpack_from("<H", clx, offset + 1)
            offset += 3 + cb
        elif clxt == 2:
            (lcb,) = struct.unpack_from("<I", clx, offset + 1)
            plc = clx[offset + 5:offset + 5 + lcb]
            break
        else:
            raise ValueError(f"모르는 CLX 항목: {clxt}")
    else:
        raise ValueError("Pcdt 없음")

    # PlcPcd: CP (n+1)개(4바이트) 뒤에 PCD n개(8바이트)
    n = (len(plc) - 4) // 12
    if n <= 0:
        raise ValueError("빈 조각 테이블")
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
    parts: list[str] = []
    total = 0
    for i in range(n):
        fc_field = struct.unpack_from("<I", plc, (n + 1) * 4 + i * 8 + 2)[0]
        chars = cps[i + 1] - cps[i]
        compressed = bool(fc_field & 0x40000000)
        fc = (fc_field & 0x3FFFFFFF) // 2 if compressed else fc_field & 0x3FFFFFFF
        size = chars if compressed else chars * 2
        chunk = word[fc:fc + size]
        text = chunk.decode("cp1252" if compressed else "utf-16le", errors="ignore")
        parts.append(text)
        total += len(text)
        if total >= budget:
            break
    return _clean_word_text("".join(parts)).strip()


def _extract_doc_text(path: Path) -> str:
    """Word 97-2003(.doc)에서 본문 앞부분을 뽑는다."""
    ole = _open_ole(path)
    try:
        word = _read_stream(ole, "WordDocument")
        if not word:
            raise ValueError(f"WordDocument 스트림이 없습니다: {path.name}")
        # FIB 플래그 비트 9(fWhichTblStm)가 1Table/0Table을 고른다.
        table_name = "1Table" if len(word) > 0x0B and (word[0x0B] & 0x02) else "0Table"
        table = _read_stream(ole, table_name) or _read_stream(
            ole, "0Table" if table_name == "1Table" else "1Table")
        try:
            return _doc_text_from_piece_table(word, table)
        except Exception:
            # 규격을 벗어난 파일은 휴리스틱으로 한 번 더 시도한다.
            return _printable_runs_fallback(word)
    finally:
        ole.close()


# PowerPoint 97 레코드 타입. [MS-PPT]
_PPT_TEXT_CHARS_ATOM = 0x0FA0   # UTF-16LE 본문
_PPT_TEXT_BYTES_ATOM = 0x0FA8   # 8비트 본문 (라틴 위주)


def _ppt_text_from_records(data: bytes, budget: int = 8000) -> str:
    """[MS-PPT] 레코드를 순회하며 텍스트 아톰을 문서 순서대로 모은다."""
    import struct

    parts: list[str] = []
    total = 0
    stack = [(0, len(data))]
    while stack and total < budget:
        offset, end = stack.pop()
        while offset + 8 <= end and total < budget:
            ver_inst, rec_type, rec_len = struct.unpack_from("<HHI", data, offset)
            payload_start = offset + 8
            payload_end = min(payload_start + rec_len, end)
            if payload_end <= payload_start and rec_len:
                break
            if (ver_inst & 0x000F) == 0x000F:
                # 컨테이너 — 지금 위치 다음을 스택에 두고 안으로 들어간다.
                stack.append((payload_end, end))
                end = payload_end
                offset = payload_start
                continue
            if rec_type == _PPT_TEXT_CHARS_ATOM:
                text = data[payload_start:payload_end].decode("utf-16le", errors="ignore")
                parts.append(text)
                total += len(text)
            elif rec_type == _PPT_TEXT_BYTES_ATOM:
                text = data[payload_start:payload_end].decode("cp1252", errors="ignore")
                parts.append(text)
                total += len(text)
            offset = payload_end
    return _clean_word_text("\n".join(parts)).strip()


def _extract_ppt_text(path: Path) -> str:
    """PowerPoint 97-2003(.ppt)에서 슬라이드 텍스트 앞부분을 뽑는다."""
    ole = _open_ole(path)
    try:
        data = _read_stream(ole, "PowerPoint Document")
        if not data:
            raise ValueError(f"PowerPoint Document 스트림이 없습니다: {path.name}")
        text = _ppt_text_from_records(data)
        return text if text else _printable_runs_fallback(data)
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
