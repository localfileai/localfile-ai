# ⚠️ 이 저장소는 이전되었습니다

**→ https://github.com/localfileai/localfile-ai**

LocalFile AI는 단일 저장소로 통합되었습니다.
이 저장소의 백엔드 코드는 커밋 히스토리와 함께 `apps/server/` 로 옮겨졌습니다.

```
app/api/routes/          ->  apps/server/app/api/routes/
app/extraction/service.py -> apps/server/app/extraction/service.py
app/contracts/api.py     ->  apps/server/app/contracts/api.py
main.py                  ->  apps/server/app/main.py
scripts/                 ->  apps/server/scripts/
```

이유는 [ADR-0001](https://github.com/localfileai/localfile-ai/blob/main/docs/decisions/0001-monorepo.md)에 있습니다.
요약하면, 4주차에 `server.exe`가 Electron 안에 들어가 설치 파일 하나로 나가는데
저장소가 갈라져 있으면 어느 커밋 조합이 동작하는 상태인지 기록되지 않습니다.

## 옮기지 않은 것

`mock/pdf/` 의 TSN 논문 9건(24MB)은 옮기지 않았습니다.
새 저장소가 public이라 저널 논문을 공개 재배포하게 되기 때문입니다.
**원본은 이 저장소에 그대로 있으니** 필요하면 여기서 받아 쓰거나
private인 `Dataset` 저장소로 옮기세요.

## 현재 로컬 구조

서버에서 import되는 애플리케이션 코드는 `app/` 안에 역할별로 모았습니다.
`mock/pdf/`, `dataset/`, `chroma_db/`는 코드가 아니라 샘플·생성물이라 루트에 따로 둡니다.

```
app/
  api/routes/       # FastAPI 라우터
  contracts/        # API 응답 모델과 AI 계약 모델
  extraction/       # PDF/TXT/MD 텍스트 추출 로직
  core/             # 설정/공통 유틸 확장 자리
  db/               # DB 연동 확장 자리
scripts/            # 데이터셋 생성, 임베딩, 모델 테스트 CLI
mock/pdf/           # 공개 저장소로 옮기지 않은 샘플 PDF
dataset/            # 생성된 합성 데이터셋
chroma_db/          # 로컬 ChromaDB 산출물
```

## AI 산출물 편입

`../AI/`에 있던 BE1 AI/RAG 산출물은 이 백엔드에서 바로 실행할 수 있게 아래 위치로 합쳤습니다.

```
AI/schemas.py          ->  app/contracts/ai.py
AI/generate_dataset.py ->  scripts/generate_dataset.py
AI/embed_dataset.py    ->  scripts/embed_dataset.py
AI/test_models.py      ->  scripts/test_models.py
```

실행 예:

```bash
python3 scripts/generate_dataset.py --count 100 --output dataset --overwrite
python3 scripts/embed_dataset.py --csv dataset/dataset.csv --db chroma_db
python3 scripts/test_models.py --csv dataset/dataset.csv --with-rag --db chroma_db
```

임베딩과 모델 테스트는 로컬 Ollama 서버와 모델 설치가 필요합니다.

## 작업 중이던 브랜치가 있다면

```bash
git clone https://github.com/localfileai/localfile-ai.git
cd localfile-ai
git checkout -b feat/be2-작업이름
# 기존 작업 파일을 apps/server/ 아래 해당 위치로 옮겨 붙이세요
```

새 저장소는 `main`이 기본 브랜치이고 PR 리뷰 1건이 필수입니다.
규칙은 [CONTRIBUTING.md](https://github.com/localfileai/localfile-ai/blob/main/CONTRIBUTING.md)를 보세요.
