<div align="center">

# LocalFile AI

**내 PC의 문서를 로컬에서 검색하고 정리하는 데스크톱 앱**

`최종.pdf`, `발표자료2.pdf` — 이름은 기억 안 나도 내용은 기억납니다.
문서를 외부 서버로 보내지 않고, 내 PC 안에서 찾고 정리합니다.

[![server](https://github.com/localfileai/localfile-ai/actions/workflows/server.yml/badge.svg)](https://github.com/localfileai/localfile-ai/actions/workflows/server.yml)
[![desktop](https://github.com/localfileai/localfile-ai/actions/workflows/desktop.yml/badge.svg)](https://github.com/localfileai/localfile-ai/actions/workflows/desktop.yml)
[![release](https://img.shields.io/github/v/release/localfileai/localfile-ai?style=flat-square&include_prereleases)](https://github.com/localfileai/localfile-ai/releases)
[![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

[문서](docs/) · [아키텍처](docs/architecture.md) · [기여 가이드](CONTRIBUTING.md) · [로드맵](#로드맵)

</div>

---

<!-- TODO: 3주차에 앱이 동작하면 이 자리에 데모 GIF를 넣으세요.
     README에서 가장 효과가 큰 한 칸입니다. docs/assets/demo.gif -->

## 기능

| | |
|---|---|
| **자연어 검색** | "네트워크 스케줄링 발표 자료 찾아줘" — 파일명을 몰라도 내용으로 찾습니다 |
| **정리 추천** | 문서 내용을 근거로 새 파일명과 폴더를 제안합니다 |
| **증분 인덱싱** | 폴더 변경을 감지해 바뀐 파일만 다시 처리합니다 |
| **로컬 전용** | Ollama + ChromaDB. 네트워크 요청도, 유료 API도 없습니다 |

파일은 **사용자가 승인한 것만** 이동·이름 변경됩니다. 모든 변경은 SQLite에 이력으로 남습니다.

## 시작하기

### 요구사항

| | 버전 | 비고 |
|---|---|---|
| Node.js | 22 LTS | 데스크톱 앱 |
| Python | 3.14 | 백엔드 서버 |
| [Ollama](https://ollama.com) | 0.32+ | 로컬 LLM 런타임 |
| VRAM | 8GB 이상 권장 | 7~8B 모델 기준. 미만이면 CPU로 동작하나 느립니다 |

### 설치

```bash
git clone https://github.com/localfileai/localfile-ai.git
cd localfile-ai

# 모델 준비
ollama pull exaone3.5:7.8b
ollama pull bge-m3

# 백엔드
cd apps/server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[files,ai,dev]"

# 데스크톱
cd ../desktop
npm ci
```

> Windows에서 `pip.exe`를 직접 실행하면 Smart App Control에 차단되는 사례가 있습니다.
> 반드시 `python -m pip` 형태로 실행하세요.

### 실행

```bash
cd apps/desktop
npm run dev          # Electron 앱 + FastAPI 서버 동시 기동
```

서버만 따로 띄우려면 `cd apps/server && uvicorn app.main:app --reload`.
API 문서는 http://localhost:8000/docs 에서 볼 수 있습니다.

## 저장소 구조

단일 저장소입니다. 4주차에 백엔드가 `server.exe`로 빌드되어 Electron 안에 포함되므로
데스크톱과 서버가 같은 커밋에서 함께 검증되어야 합니다.
([ADR-0001](docs/decisions/0001-monorepo.md))

```
localfile-ai/
├── apps/
│   ├── desktop/                  Electron + React + TypeScript
│   │   ├── electron/             메인 프로세스 · preload · IPC · 서버 프로세스 관리
│   │   └── src/                  React UI — 검색, 미리보기, 승인
│   └── server/                   FastAPI
│       ├── app/
│       │   ├── __init__.py       create_app() 팩토리
│       │   ├── main.py           uvicorn app.main:app
│       │   ├── api/routes/       라우터 — items · mock · preprocess
│       │   ├── contracts/        Pydantic 스키마 — 팀 공용 단일 기준
│       │   ├── extraction/       PyMuPDF 텍스트 추출
│       │   ├── watcher/          Watchdog 증분 인덱싱
│       │   ├── fileops/          shutil 파일 이동 · 충돌 검사 · 이력
│       │   ├── rag/              ChromaDB 임베딩 · 유사도 검색
│       │   ├── llm/              Ollama 클라이언트 · 프롬프트 · 재시도
│       │   └── db/               SQLite
│       ├── scripts/              서버 없이 전처리만 돌려보는 CLI
│       └── experiments/          모델 비교 실험 및 데이터셋 생성기
├── packages/
│   └── contracts/                Pydantic → JSON Schema → TypeScript 타입
├── docs/
│   ├── architecture.md
│   ├── data-contract.md
│   ├── development.md
│   ├── decisions/                ADR — 왜 그렇게 정했는지
│   └── weekly/                   주차별 진행 기록
└── scripts/
```

### 타입 계약

`apps/server/app/contracts/`의 Pydantic 모델이 **단일 기준**입니다.
프론트엔드 타입은 손으로 쓰지 않고 여기서 생성합니다.

```bash
python scripts/generate_contracts.py    # → packages/contracts/index.ts
```

같은 스키마를 두 언어에 각각 손으로 쓰면 반드시 갈라집니다. 컴파일은 통과하는데
런타임에 `undefined`가 나오고, 그 버그는 통합 단계에서야 발견됩니다.

> 생성 스크립트는 계약이 안정되는 2주차에 붙입니다.
> 현재 스키마와 미해결 논의는 [docs/data-contract.md](docs/data-contract.md).

## 로드맵

| | 마일스톤 | 결과물 |
|:---:|---|---|
| ✅ **W1** | 데이터셋 확보 · Mock 연동 | 폴더를 고르면 더미 데이터가 화면에 뜨는 프로토타입 |
| 🔄 **W2** | 모델 테스트 · 시스템 뼈대 | Mock을 걷어내고 실제 LLM·DB로 검색과 추천이 동작 |
| **W3** | 모델 최적화 · 파일 제어 | [승인]을 누르면 탐색기에서 실제로 파일이 이동 |
| **W4** | 패키징 · 배포 | 개발 툴 없는 PC에서 `setup.exe` 하나로 설치 |

주차별 상세 기록은 [docs/weekly/](docs/weekly/), 릴리스는
[Releases](https://github.com/localfileai/localfile-ai/releases)에 있습니다.

### MVP 범위 밖

`스캔 PDF · OCR` · `HWP · DOCX · PPTX` · `Docker` · `클라우드 서버` ·
`자동 파일 삭제` · `승인 없는 완전 자동 정리`

마지막 두 개는 일정 문제가 아니라 방침입니다.

## 팀

| 파트 | 담당 | 소유 디렉터리 |
|---|---|---|
| **BE1** · AI/DB | [@InhyeokKang](https://github.com/InhyeokKang) | `app/rag` `app/llm` `experiments` |
| **BE2** · 파일 시스템 | [@lauranofirst1](https://github.com/lauranofirst1) | `app/api` `app/extraction` `app/watcher` `app/fileops` `app/db` |
| **FE1** · Electron 아키텍처 | [@hongham](https://github.com/hongham) | `apps/desktop/electron` |
| **FE2** · UI/UX | [@0hj2](https://github.com/0hj2) | `apps/desktop/src` |
| **AI** · 리서치/검증 | [@kimyunzoo](https://github.com/kimyunzoo) | `app/rag` `app/llm` `experiments` `docs/decisions` (BE1과 공동) |

리뷰어는 [CODEOWNERS](.github/CODEOWNERS)로 자동 지정됩니다.

**AI 트랙은 두 명이 함께 봅니다.** 모델 선정, 임베딩, 프롬프트는 한 번 정하면
되돌리기 비싸고 수치 해석이 틀리기 쉽습니다. 1주차에 무작위 라벨 데이터셋으로
모델을 비교하고 잘못된 결론을 낸 적이 있어([ADR-0002](docs/decisions/0002-model-selection.md))
교차 검증을 구조로 넣었습니다. 둘 중 한 명만 승인해도 병합됩니다.

`app/contracts/`는 전원이 리뷰어로 지정됩니다. 다만 **GitHub이 강제하는 것은
그중 1명의 승인**입니다. 전원 승인을 강제하는 기능은 없습니다.
실제 합의는 [계약 변경 제안 이슈](.github/ISSUE_TEMPLATE/contract.yml)의
체크박스로 관리합니다. 코드보다 이슈가 먼저입니다.

## 기여

브랜치 전략, 커밋 규칙, PR 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)
