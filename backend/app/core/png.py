"""RGB 픽셀을 PNG로 묶는 최소 인코더 — 표준 라이브러리만 씁니다.

왜 직접 쓰는가: 미리보기 렌더러(PDFium)는 픽셀 바이트만 돌려주고 PNG는
만들어 주지 않습니다. Pillow를 쓰면 한 줄이지만, 그 한 줄 때문에 설치본에
수 MB짜리 이미지 라이브러리가 통째로 들어갑니다. 우리에게 필요한 것은
"RGB 바이트 → PNG" 하나뿐이고, 그 경우의 PNG는 규격이 단순합니다.

만드는 것은 인터레이스 없는 8비트 트루컬러 PNG 하나입니다.
  시그니처 → IHDR → IDAT(zlib으로 압축한 스캔라인) → IEND
각 스캔라인 앞에는 필터 바이트(0 = 필터 없음)가 붙습니다.

참고: PNG 명세 (RFC 2083 / W3C PNG 3rd Edition)
"""

from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 압축 수준. 미리보기는 화면에 한 번 띄우고 마는 이미지라, 파일을 조금 더
# 키우더라도 빨리 만드는 편이 낫습니다. 9로 올리면 몇 배 느려집니다.
COMPRESS_LEVEL = 6


def _chunk(tag: bytes, payload: bytes) -> bytes:
    """PNG 청크 하나: 길이 + 태그 + 내용 + CRC32(태그+내용)."""
    return (struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def encode_rgb(width: int, height: int, pixels: bytes, stride: int = 0) -> bytes:
    """RGB 바이트를 PNG로 만듭니다.

    Args:
        width, height: 픽셀 단위 크기
        pixels: 위에서 아래로, 왼쪽에서 오른쪽으로 늘어놓은 RGB 바이트
        stride: 한 행이 차지하는 실제 바이트 수. 렌더러가 행 끝에 여백을
            넣는 경우가 있어 받습니다. 0이면 `width * 3`으로 봅니다.

    Raises:
        ValueError: 크기가 0 이하이거나 픽셀 바이트가 모자랄 때.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"이미지 크기가 잘못됐습니다: {width}x{height}")

    row_bytes = width * 3
    stride = stride or row_bytes
    if stride < row_bytes:
        raise ValueError(f"stride({stride})가 한 행({row_bytes})보다 작습니다")
    if len(pixels) < stride * (height - 1) + row_bytes:
        raise ValueError("픽셀 바이트가 모자랍니다")

    # 스캔라인마다 앞에 필터 바이트 0을 붙입니다. 여백(stride - row_bytes)은 버립니다.
    raw = bytearray()
    for y in range(height):
        start = y * stride
        raw.append(0)
        raw += pixels[start:start + row_bytes]

    # 비트 깊이 8, 컬러 타입 2(트루컬러), 압축 0, 필터 0, 인터레이스 0
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    return (PNG_SIGNATURE
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), COMPRESS_LEVEL))
            + _chunk(b"IEND", b""))
