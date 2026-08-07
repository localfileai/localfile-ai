"""첫 페이지 이미지 미리보기 API 테스트.

돋보기를 눌렀을 때 "보이는 그대로"를 그려 주는 기능이라, 실제 PDF를 렌더링해
PNG가 나오는지까지 확인한다 (mock/pdf의 실파일 사용).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = next(iter(sorted((BACKEND_ROOT / "mock" / "pdf").glob("*.pdf"))), None)


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_pdf_첫_페이지를_png로_돌려준다(client):
    if SAMPLE_PDF is None:
        pytest.skip("mock/pdf에 표본 PDF가 없다")

    response = client.get("/preview/thumbnail", params={"path": str(SAMPLE_PDF)})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    # PNG 시그니처. 진짜 이미지가 왔는지 확인한다.
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(response.content) > 1000


def test_없는_파일은_404(client):
    response = client.get("/preview/thumbnail", params={"path": "/없는/경로/문서.pdf"})
    assert response.status_code == 404


def test_렌더링할_수_없는_형식은_415(client):
    """docx·hwp 등은 렌더링 엔진이 없다. 화면은 이 코드를 보고 텍스트로 넘어간다."""
    response = client.get("/preview/thumbnail",
                          params={"path": str(BACKEND_ROOT / "requirements.txt")})
    assert response.status_code == 415
    assert "미리보기" in response.json()["detail"]
