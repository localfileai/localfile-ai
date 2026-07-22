# Local File AI Backend

1주차 BE2 범위의 FastAPI 백엔드입니다.

- PDF 첫 페이지 텍스트 추출
- TXT/MD 텍스트 추출
- 프론트엔드 연동용 Mock API
- 서버 상태 확인 API

설치 및 실행:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

사용 가능한 엔드포인트:

- `GET /` - 서버 실행 확인
- `GET /health` - 상태 확인
- `GET /mock/dataset?limit=5` - 프론트엔드 개발용 더미 데이터
- `POST /preprocess/extract-first-page` - 파일 또는 폴더의 지원 문서 텍스트 추출

전처리 API 요청 예시:

```json
{
  "path": "/path/to/file-or-folder"
}
```

전처리 스크립트:

```bash
python scripts/extract_first_page.py /path/to/file-or-folder
```
