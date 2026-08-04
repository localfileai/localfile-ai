<div align="center">

# LocalFile AI

**내 PC의 문서를 로컬에서 검색하고 정리하는 데스크톱 앱**

`최종.pdf`, `발표자료 2.pdf` — 이름은 기억 안 나도 내용은 기억납니다.
문서를 외부 서버로 보내지 않고, 내 PC 안에서 찾고 정리합니다.

**1주차 통합본** · Electron + React + TypeScript / FastAPI + Ollama + ChromaDB

</div>

---

## 3분 만에 실행하기

```powershell
git clone https://github.com/localfileai/localfile-ai.git
cd localfile-ai

npm install        # 1분
npm run setup      # 3분 — 가상환경 + 파이썬 의존성 + 정답 데이터셋 1,000쌍
```

그다음 **터미널 두 개**를 엽니다.

```powershell
npm run backend:dev      # 터미널 1 — FastAPI (127.0.0.1:8000)
npm run dev              # 터미널 2 — Electron 앱 창
```

막히면 언제든 이걸 먼저 돌리세요. 무엇이 빠졌는지 알려 줍니다.

```powershell
npm run doctor
```

### 요구사항

| | 버전 | 필수 여부 |
|---|---|---|
| Node.js | 20 이상 | **필수** |
| Python | 3.11 이상 | **필수** |
| [Ollama](https://ollama.com) | — | 선택 — 없어도 앱은 돌아갑니다 |

> **VS Code에서 `node`를 못 찾으면** Node 설치 후 VS Code를 재시작하세요.
> 실행 중인 창은 설치 이전 환경을 물려받습니다.

---

## 실제 검색까지 켜기 (선택)

Ollama가 있으면 **진짜 자연어 검색**이 켜집니다. 없으면 Mock 검색으로 화면은 그대로 돕니다.

```powershell
ollama pull qwen3-embedding:0.6b   # 임베딩 639MB — 검색에 필요 (3주차에 bge-m3에서 교체)
ollama pull exaone3.5:2.4b      # LLM 1.53GB — 2주차 추천에 필요

npm run index                   # 색인 생성 · GPU 약 2분 / CPU 약 50분
```

`npm run index`는 **한 번만** 하면 됩니다. 중간에 끊으면 색인이 불완전해지니 끝까지 두세요.

색인이 끝나면 앱의 검색창 위 토글이 `실제 검색`로 활성화되고,
그 아래에 `색인 1,000건`이 초록색으로 표시됩니다.

검색해 볼 문장입니다.

```
공개키 암호화 정리한 거
OSPF BGP 비교한 문서
퀵소트 시간복잡도 정리
```

`정리_16.pdf`, `무제.pdf`, `aaa_11.txt` 같은 **지저분한 이름이 나오는 게 정상**입니다.
파일명이 아니라 내용으로 찾은 것이라 그렇습니다.
결과의 **파일명을 클릭**하면 실제 문서 원문이 뜹니다.

---

## 화면에서 확인할 것

| 위치 | 동작 | 상태 |
|---|---|---|
| 검색창 (`실제 검색`) | 자연어로 1,000건 색인 검색 | **실제** · qwen3-embedding |
| 검색 결과 → 파일명 클릭 | 실제 문서 원문 미리보기 | **실제** · PyMuPDF |
| 우측 상단 `폴더 선택` | OS 폴더 창 → 그 폴더의 문서 실제 추출 | **실제** |
| 검색창 (`Mock`) | 하드코딩 4건 | Mock · 1주차 |
| `폴더 정리` 탭 | 파일명·폴더 추천 표, 체크 후 [적용] | Mock — **실제 파일은 바뀌지 않습니다** |

`폴더 선택`으로 아래 경로를 고르면 TSN 논문 5건이 실제로 추출됩니다.

```
backend\mock\pdf
```

---

## 지원 문서 형식

기획안 3장의 대상 확장자를 따릅니다.

| 형식 | 방식 |
|---|---|
| `pdf` | PyMuPDF로 **첫 페이지만** |
| `txt` `md` | 앞부분만 (페이지 개념 없음) |
| `docx` `pptx` `hwpx` | zip + XML 파싱 (외부 라이브러리 없이) |
| `hwp` | olefile로 BodyText 스트림 디코딩 |

`doc` · `ppt`(구형 OLE 이진 포맷)는 표준 파서가 없어 외부 변환 도구가 필요하므로
스캔 PDF·이미지와 함께 초기 MVP 범위에서 제외했습니다.

---

## 선정된 모델

1주차 실측으로 정했습니다. 근거는 [ADR-0002](docs/decisions/0002-model-selection.md). (BE1 · 강인혁)

| 용도 | 모델 | 근거 |
|---|---|---|
| **임베딩** (자연어 검색) | `qwen3-embedding:0.6b` | 3주차 교체 — 느낌 검색 +20%p, 크기 절반 (ADR-0002 §2 개정) |
| **로컬 LLM** (파일명·폴더 추천) | `exaone3.5:7.8b` | 파일명 88.5% · 한국어 100% 유지 · 학기 포함률 97.5% |
| 저사양 PC용 | `exaone3.5:2.4b` | GPU 없이 13초/파일 (7.8b는 81초) |

차선 `llama3.1:8b` · 제외 `qwen2.5:7b`(한국어 85%) · 제외 `EEVE-Korean-10.8B`(VRAM 초과)

> **오프라인**: 모델이 PC에 있으면 인터넷 없이 돕니다. Ollama는 `127.0.0.1`에
> 로컬 서버를 띄우고, 추론 중 외부로 나가는 연결은 없습니다.
> 인터넷은 모델을 처음 받을 때만 필요합니다.
>
> **저사양 PC**: GPU가 없으면 추천이 느립니다. 대책을 실측해 **81초 → 13초/파일**로
> 줄였습니다. → [ADR-0003](docs/decisions/0003-offline-and-low-spec.md)

---

## 구조

```
localfile-ai/
├─ electron/            메인 프로세스 · preload · IPC              FE1
├─ src/
│  ├─ App.tsx           FE1 폴더 인식 + FE2 레이아웃이 만나는 곳
│  ├─ components/       Sidebar · Header · MainView ·
│  │                    OrganizedView · AllFilesView · FileResultCard   FE2
│  └─ api/              organizeApi · searchApi · preprocessApi         FE2
├─ scripts/             setup · doctor · backend · dev (크로스플랫폼)
├─ docs/decisions/      ADR — 왜 그렇게 정했는지
└─ backend/                                                        BE1 + BE2
   ├─ app/
   │  ├─ api/routes/    health · mock · preprocess · search ·
   │  │                  organize · indexing · feedback · apply
   │  ├─ contracts/     ai.py(BE1 · 팀 공용 계약) · api.py(BE2 · API 형태)
   │  ├─ core/          config.py 설정 단일 출처 · warmup.py 웜업    BE1
   │  ├─ extraction/    문서 텍스트 추출 (기획안 7종 형식)           BE2
   │  ├─ fileops/       승인 후 파일 이동·개명 + 이력·undo (4주차)   BE1
   │  ├─ llm/           추천 프롬프트 · 검증 + 1회 재시도            BE1
   │  └─ rag/           qwen3 임베딩 · ChromaDB 검색 · 분류          BE1
   ├─ run.py·server.spec  server.exe 엔트리·빌드 사양 (4주차)        BE1
   ├─ scripts/          데이터셋 생성 · 임베딩 · 모델 비교           BE1
   ├─ tests/            추천 파이프라인 테스트 (Ollama 불필요)       BE1
   └─ mock/pdf/         추출 테스트용 실제 PDF 5건                  BE2
```

## API

| 엔드포인트 | 상태 | 담당 |
|---|---|---|
| `GET /health` | 실제 | BE2 |
| `POST /preprocess/extract-first-page` | **실제** | BE2 |
| `GET /search` · `GET /search/status` | **실제** — qwen3-embedding 임베딩 검색 | BE1 |
| `POST /organize` · `GET /organize/status` | **실제** — RAG + LLM 분류·파일명 추천 (3주차) | BE1 |
| `POST /index` · `GET /index/status` | **실제** — 사용자 폴더 색인. 색인 후 `/search`가 실파일 대상 (3주차) | BE1 |
| `POST /feedback` · `GET /feedback/status` | **실제** — 승인 결과를 예시로 축적, 분류 맞춤화 (3주차) | BE1 |
| `POST /apply` · `GET /apply/history` · `POST /apply/undo` | **실제** — 승인 후 파일 이동·개명. 충돌·경로·권한 검증 + 이력·되돌리기 (4주차) | BE1 (BE2 리뷰 필요) |
| `GET /mock/search` · `/mock/rename` · `/mock/move` | Mock | BE2 |
| `POST /mock/rename/apply` · `/mock/move/apply` | Mock (**파일 변경 없음** — 폴더 미선택 데모에서만 사용) | BE2 |

API 문서: http://127.0.0.1:8000/docs

## 데이터 계약

`backend/app/contracts/ai.py`가 팀 공용 단일 기준입니다 (BE1).

```powershell
cd backend
.venv\Scripts\python.exe app\contracts\ai.py     # 자체 테스트 32건
```

> ⚠️ 아직 `app/contracts/api.py`(BE2, API 응답 형태)와 필드명이 다릅니다.
> `recommended_filename` vs `recommended_name`, `reason` vs `summary` 등.
> Mock을 실제 LLM으로 바꾸는 2주차에 하나로 합쳐야 합니다.

---

## 명령어

| 명령 | 설명 |
|---|---|
| `npm run setup` | 클론 직후 1회 — 가상환경 + 의존성 + 데이터셋 |
| `npm run doctor` | 환경 점검. 빠진 것과 다음 할 일 표시 |
| `npm run dev` | Electron 앱 |
| `npm run backend:dev` | FastAPI 서버 |
| `npm run dataset` | 정답 데이터셋 1,000쌍 재생성 (약 2분) |
| `npm run index` | ChromaDB 색인 (GPU 2분 / CPU 50분) |
| `npm run backend:test` | 백엔드 단위 테스트 81건 (Ollama 불필요) |
| `npm run backend:build-exe` | server 실행 파일 빌드 — Windows에서 실행 (4주차) |
| `npm run typecheck` · `lint` · `build` | 검사·빌드 |

## 알려진 문제

| 문제 | 상태 |
|---|---|
| **경로에 한글이 있으면** ChromaDB가 절대경로로 색인을 못 엶 | 상대경로로 우회. `npm run backend:dev`로 실행할 것 |
| **Drag & Drop** 동작 미확인 | 실패 시 앱에 빨간 배너 표시. 콘솔의 `[preload]` 로그 확인 필요 |
| Ollama는 요청을 **직렬 처리** | 색인 중 검색은 수십 초 대기. 2주차에 큐 분리 필요 |

## 남은 범위

`SQLite` · `Watchdog 증분 인덱싱` (BE2 몫) · `setup.exe 패키징` (server.exe 빌드
준비는 완료 — `npm run backend:build-exe`) · FE 로딩 UI (FE1&2 몫)

`실제 파일 이동·이름 변경`(4주차)과 `LLM 추천 연동`(3주차)은 완료됐습니다 —
폴더를 선택하면 실제 AI 추천이, 적용 버튼은 실제 파일 변경(`POST /apply`)이 동작합니다.
주차별 기록: `docs/weekly/`
