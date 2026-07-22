"""
API 요청/응답에 사용하는 Pydantic 모델을 모아둔 파일입니다.

라우터에서 직접 dict 구조를 흩뿌리지 않고 모델로 고정하면,
FE와 협업할 때 응답 형태를 예측하기 쉬워집니다.
"""

from typing import List

from pydantic import BaseModel


class ExtractPathRequest(BaseModel):
    """전처리 API가 받을 파일 또는 폴더 경로입니다."""

    path: str


class ExtractedDocument(BaseModel):
    """문서 하나의 텍스트 추출 결과입니다."""

    path: str
    name: str
    extension: str
    text: str
    # 폴더 처리 중 일부 파일만 실패할 수 있으므로 파일별 에러를 응답에 포함합니다.
    error: str = ""


class ExtractPathResponse(BaseModel):
    """전처리 API의 전체 응답 구조입니다."""

    count: int
    items: List[ExtractedDocument]
