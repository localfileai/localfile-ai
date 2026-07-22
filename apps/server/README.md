# Local File AI Backend

LocalFileAI 프로젝트의 백엔드 공용 저장소입니다.

BE1, BE2가 같은 레포를 사용하되 각자 작업 브랜치를 나누어 개발합니다.
`dev` 브랜치는 서로 합의된 개발 코드를 모으는 기준 브랜치로 사용합니다.
`main` 브랜치는 최종 제출 또는 안정 버전이 필요할 때만 사용합니다.

## 현재 구현 범위

현재 1주차 기준으로 BE2 작업 범위가 먼저 들어가 있습니다.

- PDF 첫 페이지 텍스트 추출
- TXT/MD 텍스트 추출
- 프론트엔드 연동용 Mock API
- 서버 상태 확인 API

## BE2: 파일 시스템/전처리/Mock API 담당

주 작업 브랜치:

```bash
git checkout be2/preprocess-fileops
```

주요 담당 파일:

- `app/routers/preprocess.py`: 파일/폴더 텍스트 추출 API
- `app/services/fileops.py`: 파일 탐색과 텍스트 추출/정규화 로직
- `app/routers/mock.py`: 프론트엔드 연동용 Mock API
- `scripts/extract_first_page.py`: 전처리 로직 단독 실행 스크립트

BE2 작업 메모:

- 1주차 핵심은 PDF 첫 페이지, TXT/MD 텍스트 추출이 안정적으로 되는 것입니다.
- FE가 붙기 쉽게 API 응답 구조를 갑자기 바꾸지 말고, 바꿔야 하면 README에 같이 기록합니다.

## 브랜치 규칙

작업 전에는 항상 최신 `dev`를 기준으로 자기 브랜치를 업데이트합니다.

```bash
git checkout dev
git pull origin dev
git checkout be2/preprocess-fileops
git merge dev
```

작업 후에는 자기 브랜치에 커밋하고 push합니다.

```bash
git status
git add .
git commit -m "작업 내용 요약"
git push
```

주의할 점:

- `main`에 직접 작업하지 않습니다.
- 평소 개발 기준은 `dev`입니다.
- 상대방 담당 파일을 수정해야 하면 먼저 말하고 진행합니다.
- `.venv`, `.env`, `__pycache__` 같은 로컬 파일은 커밋하지 않습니다.
- 충돌이 나면 임의로 지우지 말고, 어느 쪽 코드가 필요한지 확인한 뒤 정리합니다.

## GitHub 기본 브랜치 설정

GitHub 저장소 설정에서 기본 브랜치를 `dev`로 바꿉니다.

```text
Settings > Branches > Default branch > dev
```

이 설정은 저장소 관리자 권한이 있는 사람이 GitHub 웹에서 변경해야 합니다.

## 설치 및 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

브라우저에서 API 문서를 확인하려면 서버 실행 후 아래 주소로 들어갑니다.

```text
http://127.0.0.1:8000/docs
```

## 사용 가능한 엔드포인트

- `GET /` - 서버 실행 확인
- `GET /health` - 상태 확인
- `GET /mock/dataset?limit=5` - 프론트엔드 개발용 더미 데이터
- `POST /api/analyze` - 프론트엔드 파일 분석 화면용 Mock API
- `POST /preprocess/extract-first-page` - 파일 또는 폴더의 지원 문서 텍스트 추출

## Mock API 요청 예시

아직 실제 AI/RAG가 연결되지 않았기 때문에, 어떤 파일 경로를 보내도 정해진 더미 분석 결과를 돌려줍니다.
FE는 이 응답으로 로딩 스피너, 결과 카드, 추천 폴더/파일명 화면을 먼저 개발할 수 있습니다.

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"path": "/Users/me/Documents/report.pdf"}'
```

응답 예시:

```json
{
  "original_path": "/Users/me/Documents/report.pdf",
  "recommended_name": "report_정리본.pdf",
  "recommended_folder": "업무",
  "summary": "이 문서는 프로젝트 진행 상황과 다음 작업을 정리한 문서로 가정한 Mock 분석 결과입니다.",
  "confidence": 0.92,
  "tags": ["mock", "업무", "자동분류"]
}
```

## 전처리 API 요청 예시

```json
{
  "path": "/path/to/file-or-folder"
}
```

응답의 텍스트 필드는 용도별로 나뉩니다.

- `raw_text`: PDF에서 최대한 그대로 추출한 원문 확인용 텍스트
- `normalized_text`: 합자, 줄끝 하이픈, 일반 줄바꿈을 정리한 검색/임베딩용 텍스트
- `preview_text`: `max_chars` 기준으로 단어 중간을 피해서 자른 화면 표시용 텍스트

## 전처리 스크립트

```bash
python3 scripts/extract_first_page.py /path/to/file-or-folder
```

## RAG 정답 데이터셋 보조 스크립트

PDF/TXT/MD에서 추출한 텍스트를 바탕으로 개발용 질문/답변 JSONL을 만듭니다.
PDF는 `app/services/fileops.py`의 전처리 로직을 재사용하므로 첫 페이지만 읽습니다.

```bash
python3 scripts/generate_fake_dataset.py -n 1000 --source-dir /path/to/sample-docs --out fake_dataset.jsonl
```

## 간단 검증 명령

코드를 수정한 뒤 최소한 아래 명령으로 문법과 전처리 스크립트를 확인합니다.

```bash
PYTHONPYCACHEPREFIX=/tmp/sidepj_pycache python3 -m compileall main.py app scripts
python3 scripts/extract_first_page.py README.md
python3 scripts/generate_fake_dataset.py -n 3 --source-dir . --out /tmp/fake_dataset_test.jsonl
```
