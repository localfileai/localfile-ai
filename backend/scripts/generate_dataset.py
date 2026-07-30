"""LocalFile AI — BE1 1주차: 정답 데이터셋 1,000쌍 생성기.

기획안 준수 사항
  - 대상 파일 형식은 기획안 3장의 목록을 따른다.
      PDF · DOCX · DOC · HWP · HWPX · PPT · PPTX
    초기에는 PDF/TXT/MD로 잡았으나, 대학생이 실제로 다루는 문서는
    한글·워드·발표자료라서 txt/md를 빼고 위 목록으로 바로잡았다.
    (스캔 PDF와 이미지는 기획안대로 제외)

    생성기가 만드는 형식은 PDF · DOCX · PPTX · HWPX 4종이다.
    DOC · PPT는 구형 OLE 이진 포맷이라 표준 라이브러리로 '쓸' 수가 없다.
    HWP도 마찬가지여서 읽기만 지원하고 생성은 HWPX(개방형 XML)로 한다.
  - 문서 전체가 아니라 '첫 페이지만' 추출한다. PDF 추출은 PyMuPDF를 쓴다.
  - 실제 파일명은 "최종.pdf", "발표자료 2.pdf"처럼 불명확하게, 폴더 구조는
    일정하지 않게 만든다. 기획안의 문제 정의를 그대로 재현하기 위해서다.

'1,000쌍'의 쌍이란
  (지저분한 실제 파일 · 정답 3종) 을 말한다. 정답 3종은 핵심 기능 3가지에 대응한다.
    ① 자연어 검색   -> search_keywords : 이 문서를 찾을 때 사용자가 칠 법한 질의
    ② 파일 분류     -> true_category   : 들어가야 할 폴더
    ③ 파일명 추천   -> ideal_filename  : 붙어야 할 이름

정답을 문서 내용에서 결정되게 만든 이유
  이 데이터셋은 ChromaDB에 임베딩되어 'AI가 참고할 초기 지식 구조'가 된다.
  정답이 내용과 무관하면 AI에게 잘못된 예시를 학습시키게 되므로,
  category와 ideal_filename 모두 문서에 적힌 정보로부터 규칙적으로 유도한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# BE2의 추출기를 쓰려면 backend/ 를 경로에 넣어야 한다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.extraction.service import (  # noqa: E402
    extract_first_page_text,
    normalize_pdf_text,
)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
except ImportError:
    A4 = pdfmetrics = TTFont = canvas = None


# =========================================================
# 기본 설정
# =========================================================

DEFAULT_COUNT = 1000
DEFAULT_SEED = 20260727
DEFAULT_OUTPUT = Path("dataset")

# 기획안 3장의 대상 형식. 대학생이 실제로 다루는 비율을 대충 반영했다.
# (강의자료·논문 PDF가 가장 많고, 과제·보고서는 한글/워드, 발표는 PPT)
EXTENSION_WEIGHTS = {".pdf": 40, ".docx": 25, ".hwpx": 20, ".pptx": 15}

# 첫 페이지 추출 상한. 로컬 LLM 컨텍스트와 임베딩 비용을 고려한 값.
FIRST_PAGE_MAX_CHARS = 2000


# ---------------------------------------------------------
# 정답 ② 파일 분류 — 문서 유형에서 category가 결정된다.
# ---------------------------------------------------------

@dataclass(frozen=True)
class DocumentType:
    label: str          # 문서에 적히는 유형 이름
    category: str       # 정답 폴더
    sections: tuple[str, ...]


DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType("강의자료", "lecture",
                 ("학습 목표", "핵심 개념", "예제", "요약", "다음 시간 예고")),
    DocumentType("과제", "assignment",
                 ("과제 요구사항", "풀이 과정", "코드 설명", "결과", "제출 정보")),
    DocumentType("실험 보고서", "report",
                 ("실험 목적", "실험 환경", "실험 방법", "결과 및 분석", "결론")),
    DocumentType("논문 요약", "reference",
                 ("서지 정보", "연구 배경", "제안 방법", "실험 결과", "정리")),
    DocumentType("프로젝트 계획서", "project",
                 ("프로젝트 개요", "기능 명세", "일정", "역할 분담", "기대 효과")),
    DocumentType("시험 정리", "exam_prep",
                 ("시험 범위", "핵심 정리", "예상 문제", "오답 노트", "체크리스트")),
)

CATEGORIES = tuple(dict.fromkeys(d.category for d in DOCUMENT_TYPES))


# ---------------------------------------------------------
# 문서 주제
# ---------------------------------------------------------

@dataclass(frozen=True)
class Topic:
    course: str         # 과목명
    subject: str        # 분야 키
    title: str          # 문서 주제
    keywords: tuple[str, ...]   # 자연어 검색 평가에 쓸 핵심어


TOPICS: tuple[Topic, ...] = (
    Topic("데이터베이스", "database", "관계형 데이터베이스 정규화",
          ("정규화", "제3정규형", "함수 종속")),
    Topic("데이터베이스", "database", "SQL 질의 최적화와 인덱스 설계",
          ("질의 최적화", "인덱스", "실행 계획")),
    Topic("데이터베이스", "database", "트랜잭션과 동시성 제어",
          ("트랜잭션", "동시성 제어", "락")),
    Topic("운영체제", "os", "프로세스 스케줄링 알고리즘",
          ("스케줄링", "라운드로빈", "프로세스")),
    Topic("운영체제", "os", "가상 메모리와 페이지 교체",
          ("가상 메모리", "페이지 교체", "LRU")),
    Topic("운영체제", "os", "교착 상태 탐지와 회피",
          ("교착 상태", "데드락", "은행원 알고리즘")),
    Topic("컴퓨터네트워크", "network", "TCP 혼잡 제어",
          ("TCP", "혼잡 제어", "슬라이딩 윈도우")),
    Topic("컴퓨터네트워크", "network", "HTTP와 REST API 설계",
          ("HTTP", "REST API", "상태 코드")),
    Topic("컴퓨터네트워크", "network", "라우팅 프로토콜 비교",
          ("라우팅", "OSPF", "BGP")),
    Topic("자료구조", "algorithm", "트리와 그래프 탐색",
          ("트리", "그래프 탐색", "BFS DFS")),
    Topic("알고리즘", "algorithm", "동적 계획법과 그리디 비교",
          ("동적 계획법", "그리디", "최적 부분 구조")),
    Topic("알고리즘", "algorithm", "정렬 알고리즘 성능 분석",
          ("정렬", "퀵소트", "시간 복잡도")),
    Topic("인공지능", "ai", "합성곱 신경망 기반 이미지 분류",
          ("CNN", "이미지 분류", "합성곱")),
    Topic("인공지능", "ai", "자연어 처리 문장 임베딩",
          ("자연어 처리", "임베딩", "문장 분류")),
    Topic("인공지능", "ai", "강화학습 경로 탐색",
          ("강화학습", "보상", "경로 탐색")),
    Topic("소프트웨어공학", "se", "요구사항 명세와 유스케이스",
          ("요구사항", "유스케이스", "명세서")),
    Topic("소프트웨어공학", "se", "단위 테스트와 통합 테스트",
          ("단위 테스트", "테스트 커버리지", "통합 테스트")),
    Topic("정보보안", "security", "대칭키와 공개키 암호",
          ("암호화", "공개키", "대칭키")),
    Topic("정보보안", "security", "웹 취약점과 SQL 인젝션",
          ("웹 취약점", "SQL 인젝션", "보안")),
    Topic("웹프로그래밍", "web", "프론트엔드 상태 관리",
          ("프론트엔드", "상태 관리", "컴포넌트")),
)

SEMESTERS = ("2024-1", "2024-2", "2025-1", "2025-2", "2026-1")

STUDENT_NAMES = ("김민준", "이서연", "박지호", "최수빈", "정다은", "한예준")


# ---------------------------------------------------------
# 지저분한 실제 파일명 — 기획안의 문제 정의를 재현한다.
# ---------------------------------------------------------

MESSY_NAME_PATTERNS = (
    "최종", "최종본", "진짜최종", "최종_수정", "최종_최종",
    "문서", "새 문서", "제목 없음", "무제", "asdf", "test",
    "발표자료", "자료", "정리", "다운로드", "스캔", "복사본",
    "Document", "Untitled", "new", "temp", "aaa",
)

# 지저분한 폴더 — 정리가 안 된 상태를 흉내낸다.
MESSY_DIRS = (
    "Downloads", "Desktop", "Documents", "바탕화면", "새 폴더",
    "새 폴더 (2)", "학교", "학교/과제", "정리안함", "임시",
    "Documents/수업", "Downloads/자료", "Desktop/과제모음",
)


# =========================================================
# 유틸리티
# =========================================================

def sanitize(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]', "_", value)
    value = re.sub(r"\s+", "_", value.strip())
    return value.strip("._") or "untitled"


def random_datetime(rng: random.Random) -> datetime:
    start = datetime(2024, 3, 1, 9, 0, 0)
    span = int((datetime(2026, 7, 20, 23, 59, 59) - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, span))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_korean_font() -> Path | None:
    for candidate in (
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    ):
        if candidate.exists():
            return candidate
    return None


def normalize_text(text: str, limit: int = FIRST_PAGE_MAX_CHARS) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


# =========================================================
# 문서 본문 생성
# =========================================================

BODY_SENTENCES = (
    "본 내용은 수업에서 다룬 개념을 정리한 것이다.",
    "핵심 아이디어는 문제를 작은 단위로 나누어 처리하는 데 있다.",
    "예제를 통해 동작 과정을 단계별로 확인할 수 있다.",
    "성능은 입력 크기와 자료 구조 선택에 따라 크게 달라진다.",
    "실제 적용 시에는 예외 상황 처리가 함께 고려되어야 한다.",
    "아래 표와 그림은 이해를 돕기 위한 보조 자료이다.",
    "관련 개념과의 차이를 비교하면 이해가 빨라진다.",
    "이 부분은 시험에 자주 출제되므로 반복 확인이 필요하다.",
)


def build_document_text(rng: random.Random, meta: dict) -> str:
    """문서 첫 페이지에 해당하는 본문을 만든다.

    분류·파일명 추천의 근거가 되는 정보(문서 유형, 과목, 학기, 주제)를
    머리말에 명시한다. 자연어 검색 평가를 위해 핵심어도 본문에 등장시킨다.
    """
    doc_type: DocumentType = meta["doc_type"]
    topic: Topic = meta["topic"]

    lines = [
        f"{topic.title} {doc_type.label}",
        "",
        f"문서 유형: {doc_type.label}",
        f"과목: {topic.course}",
        f"학기: {meta['semester']}",
        f"작성자: {meta['author']}",
        f"작성일: {meta['created'].strftime('%Y-%m-%d')}",
        "",
        "개요",
        f"이 문서는 {topic.course} 과목의 {topic.title}에 관한 {doc_type.label}이다. "
        f"{', '.join(topic.keywords)} 등의 내용을 다룬다.",
        "",
    ]

    for number, section in enumerate(doc_type.sections, start=1):
        lines.append(f"{number}. {section}")
        for _ in range(rng.randint(2, 3)):
            picked = rng.sample(BODY_SENTENCES, k=rng.randint(2, 3))
            keyword = rng.choice(topic.keywords)
            lines.append(f"{keyword}와 관련하여, " + " ".join(picked))
        lines.append("")

    return "\n".join(lines)


# =========================================================
# 파일 쓰기 (PDF / DOCX / PPTX / HWPX)
#
# docx · pptx · hwpx는 전부 zip + XML 구조라 표준 라이브러리로 만들 수 있다.
# python-docx 같은 의존성을 더하지 않으려고 최소 골격만 직접 구성한다.
# =========================================================

def _xml_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _paragraphs(text: str) -> list[str]:
    """빈 줄을 제외한 문단 목록."""
    return [line for line in text.splitlines() if line.strip()]


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""


def write_docx(path: Path, text: str, _: dict) -> None:
    """Word 문서. 본문은 word/document.xml 의 w:t 노드에 담긴다."""
    body = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{_xml_escape(line)}</w:t></w:r></w:p>"
        for line in _paragraphs(text)
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", document)


def write_pptx(path: Path, text: str, _: dict) -> None:
    """발표자료. 문단을 몇 장의 슬라이드로 나눠 담는다."""
    lines = _paragraphs(text)
    # 슬라이드 한 장에 6문단씩. 첫 페이지 추출이 앞 슬라이드부터 읽는다.
    chunks = [lines[i:i + 6] for i in range(0, len(lines), 6)] or [[""]]

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        for number, chunk in enumerate(chunks, start=1):
            paragraphs = "".join(
                f"<a:p><a:r><a:t>{_xml_escape(line)}</a:t></a:r></a:p>" for line in chunk
            )
            slide = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
                ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                f"<p:cSld><p:spTree><p:sp><p:txBody>{paragraphs}</p:txBody></p:sp>"
                "</p:spTree></p:cSld></p:sld>"
            )
            archive.writestr(f"ppt/slides/slide{number}.xml", slide)


def write_hwpx(path: Path, text: str, _: dict) -> None:
    """한글 문서(개방형 HWPX). 본문은 Contents/section*.xml 에 담긴다.

    구형 HWP는 OLE 이진 포맷이라 표준 라이브러리로 만들 수 없다.
    읽기는 app/extraction/service.py 가 olefile로 지원한다.
    """
    paragraphs = "".join(
        f"<hp:p><hp:run><hp:t>{_xml_escape(line)}</hp:t></hp:run></hp:p>"
        for line in _paragraphs(text)
    )
    section = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f"{paragraphs}</hs:sec>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", section)


_PDF_FONT: str | None = None


def _pdf_font() -> str:
    global _PDF_FONT
    if _PDF_FONT:
        return _PDF_FONT
    font_path = find_korean_font()
    if font_path and pdfmetrics and TTFont:
        try:
            pdfmetrics.registerFont(TTFont("KoreanFont", str(font_path)))
            _PDF_FONT = "KoreanFont"
            return _PDF_FONT
        except Exception:
            pass
    _PDF_FONT = "Helvetica"
    return _PDF_FONT


def write_pdf(path: Path, text: str, _: dict) -> None:
    if canvas is None or A4 is None:
        raise RuntimeError("PDF 생성을 위해 reportlab이 필요합니다: python -m pip install reportlab")

    font = _pdf_font()
    width, height = A4
    pdf = canvas.Canvas(str(path), pagesize=A4)
    margin, line_height = 55, 15
    max_chars = int((width - margin * 2) / 6.2)

    y = height - margin
    pdf.setFont(font, 10)
    for source in text.splitlines():
        chunks = [source[i:i + max_chars] for i in range(0, len(source), max_chars)] or [""]
        for chunk in chunks:
            if y <= margin:
                pdf.showPage()
                pdf.setFont(font, 10)
                y = height - margin
            pdf.drawString(margin, y, chunk if font != "Helvetica"
                           else chunk.encode("ascii", "replace").decode("ascii"))
            y -= line_height
    pdf.save()


WRITERS = {
    ".pdf": write_pdf,
    ".docx": write_docx,
    ".pptx": write_pptx,
    ".hwpx": write_hwpx,
}


# =========================================================
# 첫 페이지 추출 — BE2의 추출기를 그대로 쓴다
#
# 계획안에서 텍스트 추출(PyMuPDF, 첫 페이지만)은 BE2 담당이다.
# 예전에는 이 생성기가 자체 추출 코드를 갖고 있었는데, 그러면 같은 PDF에서
# 두 함수가 다른 텍스트를 뽑아 임베딩과 런타임 입력이 어긋난다.
# 그래서 app/extraction/service.py 를 import해 한 곳으로 모았다.
# 새 형식(docx·pptx·hwpx)도 그쪽이 지원하므로 자동으로 따라온다.
# =========================================================

def extract_first_page(path: Path) -> tuple[str, str]:
    """(첫 페이지 텍스트, 상태)를 돌려준다. 성공 시 상태는 'success'."""
    try:
        raw = extract_first_page_text(str(path))
    except Exception as error:
        return "", f"{type(error).__name__}: {error}"

    if not raw.strip():
        return "", "empty_text"

    # BE2의 정규화(NFKC · 합자 · 하이픈 복원) 뒤 길이 상한을 적용한다.
    return normalize_text(normalize_pdf_text(raw)), "success"

    return "", "unsupported_extension"


# =========================================================
# 메타데이터
# =========================================================

@dataclass
class Record:
    index: int
    # --- 사용자 PC에 실제로 있는 상태 (지저분함) ---
    current_path: str
    current_name: str
    extension: str
    size_bytes: int
    modified_at: str
    sha256: str
    # --- 문서에서 읽어낸 내용 ---
    first_page_text: str
    extraction_status: str
    doc_type: str
    course: str
    subject: str
    topic_title: str
    semester: str
    # --- 정답 3종 ---
    true_category: str          # ② 파일 분류
    ideal_filename: str         # ③ 파일명 추천
    search_keywords: str        # ① 자연어 검색 (파이프 구분)
    ideal_path: str             # ②+③ 을 합친 최종 위치


def build_ideal_filename(meta: dict, extension: str) -> str:
    """정답 파일명 규칙: 과목_주제_문서유형_학기.ext

    문서 머리말에 전부 적혀 있는 정보만 사용하므로, 문서를 읽으면 유도할 수 있다.
    """
    topic: Topic = meta["topic"]
    doc_type: DocumentType = meta["doc_type"]
    parts = [topic.course, topic.title, doc_type.label, meta["semester"]]
    return sanitize("_".join(parts)) + extension


def build_messy_name(rng: random.Random, extension: str) -> str:
    """사용자 PC의 실제 파일명. 기획안의 '최종.pdf, 발표자료 2.pdf' 상황."""
    base = rng.choice(MESSY_NAME_PATTERNS)
    style = rng.randint(0, 3)
    if style == 0:
        return f"{base}{extension}"
    if style == 1:
        return f"{base} {rng.randint(1, 9)}{extension}"
    if style == 2:
        return f"{base}_{rng.randint(1, 30)}{extension}"
    return f"{base}({rng.randint(1, 5)}){extension}"


# =========================================================
# 생성
# =========================================================

def generate(output_root: Path, count: int, seed: int, overwrite: bool) -> Path:
    if canvas is None:
        raise RuntimeError("reportlab이 필요합니다: python -m pip install reportlab")

    rng = random.Random(seed)

    if output_root.exists():
        if not overwrite:
            raise FileExistsError(f"이미 존재합니다. --overwrite 를 쓰세요: {output_root}")
        shutil.rmtree(output_root)

    files_root = output_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    extensions = list(EXTENSION_WEIGHTS)
    weights = list(EXTENSION_WEIGHTS.values())
    used: set[Path] = set()
    records: list[Record] = []

    for index in range(1, count + 1):
        topic = rng.choice(TOPICS)
        doc_type = rng.choice(DOCUMENT_TYPES)
        extension = rng.choices(extensions, weights=weights, k=1)[0]
        semester = rng.choice(SEMESTERS)
        created = random_datetime(rng)

        meta = {
            "topic": topic,
            "doc_type": doc_type,
            "semester": semester,
            "author": rng.choice(STUDENT_NAMES),
            "created": created,
            "heading": f"{topic.title} {doc_type.label}",
        }

        text = build_document_text(rng, meta)

        # 실제 저장 위치: 정리가 안 된 폴더 + 불명확한 파일명
        messy_dir = files_root / rng.choice(MESSY_DIRS)
        messy_dir.mkdir(parents=True, exist_ok=True)

        for _ in range(50):
            candidate = messy_dir / build_messy_name(rng, extension)
            if candidate not in used:
                break
        else:
            candidate = messy_dir / f"{index:04d}{extension}"
        used.add(candidate)

        WRITERS[extension](candidate, text, meta)

        stamp = created.timestamp()
        import os
        os.utime(candidate, (stamp, stamp))

        first_page, status = extract_first_page(candidate)
        stat = candidate.stat()

        ideal_name = build_ideal_filename(meta, extension)
        records.append(Record(
            index=index,
            current_path=str(candidate.relative_to(output_root)),
            current_name=candidate.name,
            extension=extension.lstrip("."),
            size_bytes=stat.st_size,
            modified_at=created.isoformat(timespec="seconds"),
            sha256=sha256_of(candidate),
            first_page_text=first_page,
            extraction_status=status,
            doc_type=doc_type.label,
            course=topic.course,
            subject=topic.subject,
            topic_title=topic.title,
            semester=semester,
            true_category=doc_type.category,
            ideal_filename=ideal_name,
            search_keywords="|".join(topic.keywords),
            ideal_path=f"{doc_type.category}/{topic.course}/{semester}/{ideal_name}",
        ))

        if index % 100 == 0 or index == count:
            print(f"[진행] {index}/{count}")

    metadata_path = output_root / "dataset.csv"
    with metadata_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Record.__annotations__))
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "seed": seed,
        "count": len(records),
        "scope_note": (
            "기획안 3장 대상 형식: PDF·DOCX·DOC·HWP·HWPX·PPT·PPTX. "
            "생성기는 PDF/DOCX/PPTX/HWPX 4종을 만든다 "
            "(DOC·PPT·HWP는 구형 이진 포맷이라 표준 라이브러리로 생성 불가). "
            "초기 PDF/TXT/MD에서 txt·md를 제외하도록 바로잡음 — 대학생 대상 문서가 아님."
        ),
        "first_page_extractor": "app/extraction/service.py (BE2) — PDF는 PyMuPDF, 나머지는 zip+XML",
        "categories": list(CATEGORIES),
        "extension_counts": _count(records, "extension"),
        "category_counts": _count(records, "true_category"),
        "doc_type_counts": _count(records, "doc_type"),
        "course_counts": _count(records, "course"),
        "extraction_status_counts": _count(records, "extraction_status"),
        "label_rule": "true_category = DOCUMENT_TYPES[문서 유형].category  (문서 머리말에서 유도 가능)",
        "filename_rule": "ideal_filename = 과목_주제_문서유형_학기.확장자",
        "notice": "실제 학생·개인정보를 포함하지 않는 합성 데이터셋입니다.",
    }
    (output_root / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("데이터셋 생성 완료")
    print(f"- 루트     : {output_root.resolve()}")
    print(f"- 파일 수  : {len(records)}쌍")
    print(f"- 메타데이터: {metadata_path.resolve()}")
    return metadata_path


def _count(records: list[Record], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = getattr(record, field_name)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LocalFile AI 정답 데이터셋 1,000쌍 생성 (PDF/TXT/Markdown)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.count <= 0:
        print("[에러] --count는 1 이상이어야 합니다.", file=sys.stderr)
        return 1

    generate(args.output.expanduser(), args.count, args.seed, args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
