"""문서 첫 페이지 이미지 미리보기 (5주차).

돋보기를 눌렀을 때 추출된 텍스트만 보여 주면 "이 파일이 내가 찾던 그거인가"를
판단하기 어렵다. 표·그림·서식이 사라진 글자 덩어리라서다. 실제로 보이는
모습을 그대로 그려 주면 한눈에 알아본다.

PDF는 PDFium으로 첫 페이지를 그대로 렌더링한다. 그 외 형식(docx·hwp 등)은
렌더링 엔진이 없으므로 415를 주고, 화면이 텍스트 미리보기로 넘어간다.

렌더러를 PyMuPDF에서 PDFium(pypdfium2)으로 바꿨다 — PyMuPDF가 AGPL-3.0이라
설치본 배포와 충돌했기 때문이다 (ADR-0004). PDFium은 픽셀 바이트만 돌려주므로
PNG로 묶는 일은 `app.core.png`가 한다.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ...core import png

router = APIRouter(prefix="/preview", tags=["preview"])

# 화면에 띄우는 용도라 과하게 크게 그리지 않는다 (렌더링 시간과 메모리).
RENDER_SCALE = 1.6


@router.get("/thumbnail")
async def thumbnail(path: str = Query(..., min_length=1)):
    """문서 첫 페이지를 PNG로 렌더링해 돌려준다."""
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=415,
            detail=f"{file_path.suffix.lstrip('.').upper()} 형식은 이미지 미리보기를 지원하지 않습니다.")

    try:
        image = _render_first_page(file_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail=f"미리보기를 만들 수 없습니다: {exc}") from exc

    # 같은 파일을 다시 열 때 즉시 뜨도록 잠깐 캐시한다.
    return Response(content=image, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})


def _render_first_page(file_path: Path) -> bytes:
    """PDF 첫 페이지를 PNG 바이트로 그린다."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(file_path))
    try:
        if len(document) == 0:
            raise HTTPException(status_code=404, detail="페이지가 없는 문서입니다.")
        page = document[0]
        try:
            # rev_byteorder=True여야 PDFium 기본값인 BGR 대신 RGB로 나온다.
            bitmap = page.render(scale=RENDER_SCALE, rev_byteorder=True)
            return png.encode_rgb(bitmap.width, bitmap.height,
                                  bytes(bitmap.buffer), bitmap.stride)
        finally:
            page.close()
    finally:
        # 열린 핸들이 남으면 Windows에서 그 파일의 이름 변경·이동이 실패한다.
        document.close()
