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

    class Config:
        schema_extra = {
            "example": {
                "original_path": "/Users/alex/Documents/report.pdf",
                "recommended_name": "report_summary.pdf",
                "recommended_folder": "업무/프로젝트A",
                "summary": "프로젝트 A의 진행 상황과 다음 단계(요약): 1) 데이터 수집 완료, 2) 모델 학습 진행 필요, 3) 배포 계획 수립.",
                "confidence": 0.91,
                "tags": ["프로젝트A", "요약", "업무"]
            }
        }


# --- 추가된 문서/응답 모델 ---
class SearchItem(BaseModel):
    name: str
    ext: str
    path: str
    modified: str
    score: int
    snippet: str

    class Config:
        schema_extra = {
            "example": {
                "name": "TSN_스케줄링_발표자료.pdf",
                "ext": "PDF",
                "path": "Documents/연구/TSN",
                "modified": "2026-06-23",
                "score": 87,
                "snippet": "TAS와 CBS+TAS의 지터 및 처리량 비교 결과를 정리한 발표 자료입니다."
            }
        }


class SearchResponse(BaseModel):
    count: int
    items: List[SearchItem]

    class Config:
        schema_extra = {
            "example": {
                "count": 2,
                "items": [
                    {
                        "name": "TSN_스케줄링_발표자료.pdf",
                        "ext": "PDF",
                        "path": "Documents/연구/TSN",
                        "modified": "2026-06-23",
                        "score": 87,
                        "snippet": "TAS와 CBS+TAS의 지터 및 처리량 비교 결과를 정리한 발표 자료입니다."
                    },
                    {
                        "name": "논문학습플랫폼_README.md",
                        "ext": "MD",
                        "path": "Documents/프로젝트/Paper-Learning",
                        "modified": "2025-07-27",
                        "score": 89,
                        "snippet": "문단 추출 및 요약 기능 설명이 포함된 README 파일입니다."
                    }
                ]
            }
        }


class RenameRecommendation(BaseModel):
    id: int
    old: str
    next: str
    path: str
    ext: str
    confidence: int

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "old": "최종.pdf",
                "next": "가치가게_캡스톤_최종발표_2025.pdf",
                "path": "대학교/캡스톤",
                "ext": "PDF",
                "confidence": 96
            }
        }


class RenameResponse(BaseModel):
    count: int
    items: List[RenameRecommendation]

    class Config:
        schema_extra = {
            "example": {
                "count": 2,
                "items": [
                    {
                        "id": 1,
                        "old": "최종.pdf",
                        "next": "가치가게_캡스톤_최종발표_2025.pdf",
                        "path": "대학교/캡스톤",
                        "ext": "PDF",
                        "confidence": 96
                    },
                    {
                        "id": 2,
                        "old": "notes.txt",
                        "next": "QR키오스크_DB설계_메모.txt",
                        "path": "프로젝트/QR-Kiosk",
                        "ext": "TXT",
                        "confidence": 90
                    }
                ]
            }
        }


class MoveRecommendation(BaseModel):
    id: str
    name: str
    from_: str
    to: str
    confidence: int

    class Config:
        schema_extra = {
            "example": {
                "id": "value",
                "name": "가치가게_캡스톤_최종발표.pdf",
                "from_": "Documents/다운로드",
                "to": "Documents/대학교/2025/캡스톤/가치가게",
                "confidence": 96
            }
        }


class MoveResponse(BaseModel):
    current_files: List[dict]
    recommendations: List[MoveRecommendation]

    class Config:
        schema_extra = {
            "example": {
                "current_files": [
                    {"id": "value", "name": "가치가게_캡스톤_최종발표.pdf", "ext": "PDF", "path": "Documents/다운로드"}
                ],
                "recommendations": [
                    {
                        "id": "value",
                        "name": "가치가게_캡스톤_최종발표.pdf",
                        "from_": "Documents/다운로드",
                        "to": "Documents/대학교/2025/캡스톤/가치가게",
                        "confidence": 96
                    }
                ]
            }
        }


class ApplyRequest(BaseModel):
    ids: List[str]

    class Config:
        schema_extra = {"example": {"ids": ["value", "tsn"]}}


class ApplyResponse(BaseModel):
    applied: int
    status: str

    class Config:
        schema_extra = {"example": {"applied": 2, "status": "ok"}}


class ReanalyzeResponse(BaseModel):
    message: str
    rename_count: int
    move_count: int

    class Config:
        schema_extra = {"example": {"message": "reanalyzed", "rename_count": 4, "move_count": 3}}
