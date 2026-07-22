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
    # raw_text는 PDF에서 최대한 그대로 뽑은 원문 확인용 텍스트입니다.
    raw_text: str = ""
    # normalized_text는 검색, 요약, 임베딩에 쓰기 좋게 정리한 텍스트입니다.
    normalized_text: str = ""
    # preview_text는 max_chars 기준으로 단어 중간을 피해서 자른 화면 표시용 텍스트입니다.
    preview_text: str = ""
    # 폴더 처리 중 일부 파일만 실패할 수 있으므로 파일별 에러를 응답에 포함합니다.
    error: str = ""


class ExtractPathResponse(BaseModel):
    """전처리 API의 전체 응답 구조입니다."""

    count: int
    items: List[ExtractedDocument]


class MockAnalyzeRequest(BaseModel):
    """FE가 분석 요청을 보낼 때 사용할 최소 입력값입니다."""

    path: str


class MockAnalyzeResponse(BaseModel):
    """AI/RAG 완성 전까지 FE가 화면 개발에 사용할 가짜 분석 결과입니다."""

    original_path: str
    recommended_name: str
    recommended_folder: str
    summary: str
    confidence: float
    tags: List[str]
