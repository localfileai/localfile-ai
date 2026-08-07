"""전처리(추출) API의 요청/응답 계약입니다. (BE2)

3주차 계약 단일화(docs/contracts-unification.md)로 이 파일에는 **실제 API 계약만**
남습니다. Mock 전용 모델들은 `app/api/routes/mock.py` 안으로 옮겼습니다 —
`contracts/ai.py`와 이름이 같은데 모양이 다른 클래스(SearchResponse, ApplyRequest)가
계약 패키지에 공존하며 import 실수를 유발하던 문제를 없애기 위함입니다.

검색·추천·색인·승인 계약의 단일 기준은 `contracts/ai.py`입니다.
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
