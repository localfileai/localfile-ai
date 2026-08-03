"""구형 MS Office(doc·ppt) 파서 테스트 — 규격대로 합성한 바이트로 검증한다.

olefile은 쓰기를 지원하지 않아 실제 OLE 파일을 만들 수 없다. 대신 파서를
스트림 바이트를 받는 순수 함수로 두고, [MS-DOC]/[MS-PPT] 규격대로 조립한
바이트를 넣어 검증한다. 실파일 스모크 테스트는 실기기에서 진행한다.
"""

import struct

from app.extraction.service import (
    SUPPORTED_TEXT_EXTENSIONS,
    _doc_text_from_piece_table,
    _ppt_text_from_records,
    _printable_runs_fallback,
)


def make_doc_streams(text: str, compressed: bool = False):
    """조각 1개짜리 WordDocument/Table 스트림을 [MS-DOC] 규격대로 만든다."""
    if compressed:
        payload = text.encode("cp1252")
        fc_field = (0x400 * 2) | 0x40000000
    else:
        payload = text.encode("utf-16le")
        fc_field = 0x400

    word = bytearray(0x400 + len(payload))
    struct.pack_into("<H", word, 0, 0xA5EC)                      # FIB 시그니처
    word[0x400:0x400 + len(payload)] = payload

    # PlcPcd: CP 2개 + PCD 1개
    plc = struct.pack("<II", 0, len(text)) + struct.pack("<HIH", 0, fc_field, 0)
    clx = b"\x02" + struct.pack("<I", len(plc)) + plc            # Pcdt
    struct.pack_into("<II", word, 0x01A2, 0, len(clx))           # fcClx=0, lcbClx

    return bytes(word), clx


def ppt_record(rec_type: int, payload: bytes, container: bool = False) -> bytes:
    ver_inst = 0x000F if container else 0x0000
    return struct.pack("<HHI", ver_inst, rec_type, len(payload)) + payload


class TestDocPieceTable:
    def test_유니코드_조각(self):
        word, table = make_doc_streams("운영체제 스케줄링 강의자료 1주차")
        assert _doc_text_from_piece_table(word, table) == "운영체제 스케줄링 강의자료 1주차"

    def test_압축_8비트_조각(self):
        word, table = make_doc_streams("OS Lecture Notes", compressed=True)
        assert _doc_text_from_piece_table(word, table) == "OS Lecture Notes"

    def test_제어문자는_정리된다(self):
        word, table = make_doc_streams("제목\r본문\x13필드\x15끝")
        text = _doc_text_from_piece_table(word, table)
        assert "\r" not in text and "\x13" not in text
        assert "제목" in text and "본문" in text

    def test_시그니처가_아니면_거부(self):
        try:
            _doc_text_from_piece_table(b"\x00" * 0x200, b"")
        except ValueError:
            pass
        else:
            raise AssertionError("ValueError가 나야 한다")

    def test_휴리스틱_폴백은_한글_구간을_건진다(self):
        blob = b"\x01\x02" * 50 + "데이터베이스 정규화 과제 문서입니다".encode("utf-16le") + b"\x00" * 20
        assert "데이터베이스 정규화" in _printable_runs_fallback(blob)


class TestPptRecords:
    def test_컨테이너_안의_텍스트_아톰을_순서대로(self):
        chars = ppt_record(0x0FA0, "발표자료 첫 슬라이드".encode("utf-16le"))
        bytes_atom = ppt_record(0x0FA8, b"English notes")
        slide = ppt_record(0x03EE, chars + bytes_atom, container=True)
        text = _ppt_text_from_records(slide)
        assert text.index("발표자료") < text.index("English")

    def test_텍스트가_아닌_레코드는_무시(self):
        junk = ppt_record(0x0BC1, b"\x00" * 16)
        chars = ppt_record(0x0FA0, "핵심 내용".encode("utf-16le"))
        assert _ppt_text_from_records(junk + chars) == "핵심 내용"

    def test_깨진_길이에도_죽지_않는다(self):
        broken = struct.pack("<HHI", 0x0000, 0x0FA0, 0xFFFFFF) + b"\x41\x00"
        _ppt_text_from_records(broken)  # 예외 없이 반환하면 된다


def test_지원_확장자는_기획안_7종():
    assert SUPPORTED_TEXT_EXTENSIONS == {
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".hwpx", ".hwp"}
