"""직접 만든 PNG 인코더 테스트 (app/core/png.py).

Pillow를 설치본에 넣지 않으려고 직접 썼다. 직접 쓴 이상 규격을 지키는지
검증해야 한다 — 브라우저가 못 읽는 PNG를 만들면 미리보기가 통째로 죽는다.

읽는 쪽은 Pillow로 확인한다. Pillow는 개발·테스트 환경에만 있으면 되고
배포본에는 들어가지 않는다.
"""

import struct
import zlib

import pytest

from app.core import png


def solid(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    return bytes(color) * width * height


class TestFormat:
    def test_시그니처와_청크_순서(self):
        data = png.encode_rgb(2, 2, solid(2, 2, (255, 0, 0)))

        # 청크는 [길이 4][태그 4][내용][CRC 4] 순서다.
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert data[12:16] == b"IHDR"
        assert data[-8:-4] == b"IEND"          # 마지막 청크는 내용이 비어 있다
        assert data[-12:-8] == b"\x00" * 4     # 그 길이는 0

    def test_IHDR가_크기와_색_형식을_담는다(self):
        data = png.encode_rgb(7, 3, solid(7, 3, (1, 2, 3)))

        width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
        assert (width, height) == (7, 3)
        assert depth == 8          # 8비트
        assert color_type == 2     # 트루컬러(RGB)

    def test_모든_청크의_CRC가_맞는다(self):
        # CRC가 틀리면 브라우저가 이미지를 통째로 거부한다.
        data = png.encode_rgb(5, 4, solid(5, 4, (10, 20, 30)))

        offset, seen = 8, []
        while offset < len(data):
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            tag = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + length]
            crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
            assert crc == zlib.crc32(tag + payload) & 0xFFFFFFFF, f"{tag} CRC 불일치"
            seen.append(tag)
            offset += 12 + length

        assert seen == [b"IHDR", b"IDAT", b"IEND"]


class TestPixels:
    def test_읽어_들이면_원래_색이_나온다(self):
        Image = pytest.importorskip("PIL.Image", reason="Pillow는 테스트에만 쓴다")
        import io

        data = png.encode_rgb(3, 2, solid(3, 2, (12, 200, 77)))
        image = Image.open(io.BytesIO(data))

        assert image.size == (3, 2)
        assert image.mode == "RGB"
        assert set(image.getdata()) == {(12, 200, 77)}

    def test_행마다_다른_색도_자리를_지킨다(self):
        Image = pytest.importorskip("PIL.Image", reason="Pillow는 테스트에만 쓴다")
        import io

        # 위 행은 빨강, 아래 행은 파랑
        pixels = bytes([255, 0, 0] * 2 + [0, 0, 255] * 2)
        image = Image.open(io.BytesIO(png.encode_rgb(2, 2, pixels)))

        assert image.getpixel((0, 0)) == (255, 0, 0)
        assert image.getpixel((1, 1)) == (0, 0, 255)

    def test_행_끝의_여백은_버린다(self):
        """렌더러가 행을 4바이트 배수로 맞추느라 여백을 넣는 경우가 있다.

        그대로 흘려보내면 이미지가 대각선으로 밀려 보인다.
        """
        Image = pytest.importorskip("PIL.Image", reason="Pillow는 테스트에만 쓴다")
        import io

        # 폭 1픽셀(3바이트)인데 한 행이 5바이트 — 뒤 2바이트는 쓰레기값
        pixels = bytes([9, 9, 9, 0xFF, 0xFF]) + bytes([7, 7, 7, 0xFF, 0xFF])
        image = Image.open(io.BytesIO(png.encode_rgb(1, 2, pixels, stride=5)))

        assert image.getpixel((0, 0)) == (9, 9, 9)
        assert image.getpixel((0, 1)) == (7, 7, 7)


class TestRejects:
    @pytest.mark.parametrize("width,height", [(0, 5), (5, 0), (-1, 5)])
    def test_크기가_잘못되면_거부한다(self, width, height):
        with pytest.raises(ValueError):
            png.encode_rgb(width, height, b"")

    def test_픽셀이_모자라면_거부한다(self):
        # 조용히 잘린 이미지를 만드느니 여기서 터지는 편이 낫다.
        with pytest.raises(ValueError, match="모자랍니다"):
            png.encode_rgb(10, 10, solid(10, 5, (0, 0, 0)))

    def test_stride가_한_행보다_작으면_거부한다(self):
        with pytest.raises(ValueError, match="stride"):
            png.encode_rgb(4, 2, solid(4, 2, (0, 0, 0)), stride=6)
