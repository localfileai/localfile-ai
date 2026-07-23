# Local File AI Backend — 실행 방법 & 브랜치 규칙

이 파일은 간단하게 로컬에서 서버를 실행하는 방법과 팀의 브랜치 규칙만 담고 있습니다.

## 실행 방법 (로컬)

1. 가상환경 생성 및 활성화

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. 의존성 설치

```bash
python3 -m pip install -r requirements.txt
```

3. 서버 실행 (개발용)

```bash
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

4. 실행 확인

브라우저에서 다음 URL을 열어 OpenAPI 문서를 확인하세요:

```
http://127.0.0.1:8000/docs
```

또는 터미널에서 간단 검증:

```bash
curl -sS http://127.0.0.1:8000/ | head -n 5
curl -sS http://127.0.0.1:8000/mock/search | jq '.'
```

## 브랜치 규칙

팀은 `dev` 브랜치를 기본 개발 브랜치로 사용합니다. 개인 작업은 `dev`에서 브랜치를 따서 진행하세요.

1. 작업 시작 전 (항상 최신 `dev`로 동기화)

```bash
git checkout dev
git pull origin dev
git checkout -b feat/your-feature
```

2. 작업 완료 후 (커밋 → push → PR)

```bash
git add .
git commit -m "요약: 작업 내용"
git push -u origin feat/your-feature
```

3. PR 규칙

- PR 대상은 `dev`로 합니다.
- 리뷰 요청 전에 로컬에서 `dev`를 rebase 또는 merge 해서 충돌이 없도록 합니다.
- `main`에는 직접 머지하지 않습니다; 릴리스 시 관리자가 병합합니다.

## 간단 주의사항

- 로컬 민감 파일(`.venv`, `.env`, `__pycache__`)은 커밋하지 마세요.
- 다른 사람의 담당 파일을 수정해야 하면 미리 합의하고 진행하세요.

---

README를 요청하신 대로 실행방법과 브랜치 규칙만 남기도록 단순화했습니다.
