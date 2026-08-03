# 3주차 — 모델 최적화 · 추천 경로 실제 연결 · 검증/재시도 (BE1)

- **작성**: 강인혁 (BE1 · AI/DB)
- **기준 브랜치**: `week1-integration` 위에 작업
- **작업 환경**: 클라우드 세션 (Ollama·색인 없음 → 코드/테스트/문서만. 실기기 측정은 아래 "로컬에서 돌릴 것" 참고)

## 계획서 3주차 BE1 항목별 산출물

| 계획서 항목 | 산출물 | 실행 |
|---|---|---|
| **① 유사도 검색 API** — 자연어 검색어로 ChromaDB에서 유사 문서 검색 | ⓐ `GET /search`·`/search/status` (2주차 선행 구현 + 3주차 지연 최적화) ⓑ **어려운 평가셋 40문항** `scripts/data/search_eval_hard.jsonl` — 핵심어를 안 쓴 paraphrase 20 + 구어체 keyword 20, 주제 20종 전수 커버 ⓒ **평가 스크립트** `scripts/eval_search.py` — Top-1 · Recall@5 · MRR · P@5 · 지연을 난이도별로 출력 | `python scripts/eval_search.py` (Ollama+색인 필요, 약 3분) |
| **② 모델 최적화** — 생성 속도·결과물 품질 | ⓐ 최적화 코드 4종: Session 재사용+`keep_alive`(`rag/embedding.py`·`llm/client.py`), RAG·k-NN **단일 임베딩 질의**(`rag/retrieve.py`), **slim 모드**(k-NN 분류+소형 모델), 설정 단일화(`core/config.py`) ⓑ **전/후 벤치마크** `scripts/bench_optimization.py` — [A] 커넥션·keep_alive [B] 질의 1번vs2번 [C] k-NN 정확도(저장 벡터 재사용, Ollama 불필요) [D] full vs slim 시간·토큰 | `python scripts/bench_optimization.py` (+`--with-llm`) |
| **③ Pydantic 검증 + 재시도** — 형식 깨진 응답 대비 | ⓐ 파이프라인 `app/llm/suggest.py` — 확장자 자동 보정 → 위반 제약 명시 1회 재시도 → 실패 시 `failed[]` ⓑ **동작 시연 결과** [`assets/week03-retry-demo.txt`](assets/week03-retry-demo.txt) — 실제 실패 유형 5종 전 과정, **5/5 기대대로 동작 확인 완료** ⓒ 단위 테스트 25건 **통과 확인 완료** ⓓ `test_models.py --retry` — 실기기 구제율 측정 옵션 | `python scripts/demo_retry.py` · `npm run backend:test` (둘 다 Ollama 불필요) |

2주차 이월분인 **추천 경로 연결**(`/mock/*` 하드코딩 → 실제 RAG+LLM)도 이번에 구현했다: `POST /organize`.
③의 시연과 테스트는 실행까지 완료했고, ①ⓑⓒ와 ②ⓑ의 **수치 채우기**만 Ollama가 있는 로컬 PC 몫이다
(이 클라우드 환경은 ollama.com·HuggingFace가 네트워크 정책으로 차단되어 모델을 받을 수 없다).

## 새로 생긴 것

```
backend/app/
├─ core/config.py        Ollama·모델 설정 단일 출처 (ADR-0002 §3 후속 조치)
├─ llm/
│  ├─ client.py          Ollama generate 클라이언트 (Session 재사용 · keep_alive)
│  ├─ prompts.py         full/slim 프롬프트 · 위반 목록 포맷 · 재시도 프롬프트
│  └─ suggest.py         ★ 검증 + 1회 재시도 파이프라인 ★
├─ rag/retrieve.py       유사 예시 + k-NN 분류를 임베딩 질의 한 번으로 조회
└─ api/routes/organize.py  POST /organize · GET /organize/status
backend/tests/           25건 — LLM·컬렉션을 가짜로 주입해 Ollama 없이 돈다
```

- 계약 추가: `contracts/ai.py`에 `OrganizeRequest` (path · mode · max_files · use_rag). 자체 테스트 26→30건
- `npm run backend:test` 추가

## `POST /organize` — 실제 추천 경로

```
추출(BE2 extraction) → RAG 조회 → LLM 생성 → 검증+재시도 → OrganizeResponse
```

```jsonc
// 요청
{ "path": "C:/Users/me/Downloads", "mode": "full", "max_files": 20, "use_rag": true }
// 응답: contracts/ai.py의 OrganizeResponse (FE '미리보기 표' 데이터)
```

- 파일 변경은 하지 않는다. 승인 후 이동/이름 변경은 계획서상 BE2의 apply API 몫
- Ollama·모델이 없으면 503 + 이유 (`GET /organize/status`로 사전 확인 가능)
- 파일 단위 실패는 억지 추천 없이 `failed[]`에 이유와 함께 남긴다

### 검증 + 재시도 (ADR-0002가 exaone 채택의 전제 조건으로 못박은 것)

1. **확장자 자동 보정** — exaone의 유일한 대량 탈락 원인(1차 측정 JSON 유효율 62.5%)이
   확장자 누락이었다. 원본 확장자는 백엔드가 아는 값이라 후처리로 붙인다. 재시도보다 먼저 적용되므로
   이 사례는 **LLM 재호출 없이** 해결된다 (CPU에서 호출당 수십 초 절약).
2. **위반 명시 1회 재시도** — 그래도 `FileSuggestion` 검증에 실패하면 "어느 필드가 어떤 제약을
   어겼는지"를 이전 출력과 함께 보여 주고 정확히 1회 재시도한다. 또 실패하면 `failed[]`로.

## 모델 최적화 (계획서 3주차 항목)

| 조치 | 근거 | 기대 효과 |
|---|---|---|
| `requests.Session` 재사용 + `keep_alive: 10m` (임베딩·생성 공통) | ADR-0002 §5: 질의 지연의 96%가 요청당 고정 오버헤드, GPU·모델 축소로 안 줄어듦 | 검색 체감 지연 감소 (실기기 측정 필요) |
| RAG 예시 + k-NN 분류를 **임베딩 질의 한 번**으로 | CPU 질의당 약 2.8초 → 두 번 질의하면 두 배 | 추천 파일당 임베딩 비용 절반 |
| **slim 모드** (`mode: "slim"`) — 분류는 k-NN(k=3, 96.0%), LLM은 파일명만(2.4b) | ADR-0002 §5-1: 81.1초 → 13.0초/파일 | GPU 없는 PC 대응 |
| 설정 단일화 (`core/config.py`) | ADR-0002 §3 "설정 한 곳에 모을 것" | 모델 교체 실험이 env 변수 하나 |

slim 모드는 **2.4b 파일명 품질 재측정 전이라 기본값이 아니다** (`LOCAL_FILE_AI_RECOMMEND_MODE`로 변경 가능).

## 테스트

```
npm run backend:test        # 25건, Ollama 불필요
```

- 재시도: 정상 응답은 재시도 없음 / 확장자 누락은 보정으로 해결(재호출 없음) /
  위반 시 위반 필드가 재시도 프롬프트에 포함 / 재시도 실패 시 이유와 함께 실패 / 재시도는 정확히 1회
- slim 조립: k-NN 분류 + 파일명 합성, 금지 문자 재시도
- retrieve: 단일 질의로 예시+투표, 자기 자신 제외, 계약 밖 카테고리 무시
- API: 503(모델 없음) · 400(경로 오류) · 422(모르는 mode) · full/slim 정상 경로 · failed 분리

## 클라우드 대체 모델 실측 — 검색 스택 전체를 실제로 돌린 결과

이 세션은 Ollama·bge-m3를 받을 수 없어(네트워크 정책), 열려 있는 경로(GCS)로
`intfloat/multilingual-e5-large`(ONNX·1024차원 다국어)를 받아 **Ollama 호환 심 서버**
(`scripts/ollama_embed_shim.py`)에 물리고, 앱 코드 수정 없이 전 과정을 실행했다:

> 데이터셋 1,000쌍 생성 → ChromaDB 1,000건 전수 색인(999.6초) → 평가·벤치마크 →
> **실제 FastAPI 서버 라이브 검색** ([전 과정 캡처](assets/week03-live-api-demo.txt))

⚠️ **아래 수치는 대체 모델(e5) 기준이다.** bge-m3 수치가 아니며, 실기기 측정을
대신하지 않는다. 파이프라인·평가셋·API가 실제로 동작함을 실증하는 것이 목적이다.

### ① 검색 품질 — 어려운 평가셋 40건 ([전체 출력](assets/week03-search-eval-e5.txt))

| 난이도 | 건수 | Top-1 | Recall@5 | MRR | P@5 |
|---|---|---|---|---|---|
| keyword (구어체+핵심어 1개) | 20 | **100.0%** | 100.0% | 1.000 | 100.0% |
| paraphrase (핵심어 없음) | 20 | **75.0%** | 90.0% | 0.812 | 82.0% |
| 전체 | 40 | 87.5% | 95.0% | 0.906 | 91.0% |

- **1주차 "쉬운 평가셋 100%"의 실체가 드러났다**: 핵심어를 빼면 Top-1이 75%로 떨어진다.
  이 격차가 ADR-0002 §2 단서("평가셋이 쉽다")의 정량화다. bge-m3로 같은 평가를 돌려
  이 표와 나란히 놓는 것이 실기기 측정의 핵심이다.
- 라이브 데모에서도 동일하게 재현: "메모리 모자랄 때 디스크를 대신 쓰는 기법" →
  `무제.docx`(가상 메모리 강의자료) 정답, "테이블 나눠서 중복 없애는 방법" → 오답(정렬 계획서).

### ② 최적화 벤치마크 ([전체 출력](assets/week03-bench-e5.txt))

| 항목 | 결과 | 판정 |
|---|---|---|
| [B] RAG 예시+분류 질의 1번 vs 2번 | **115ms → 55ms (정확히 절반)** | 설계 효과 실증. 실기기(질의당 2.8s)에선 파일당 약 2.8초 절약 |
| [C] k-NN 분류 (같은 주제 배제, 전수 1,000건) | k=1: 62.8% · k=3: 61.5% · k=5: 63.0% (기준선 17.5%) | ⚠️ **발견 — 아래 참고** |
| [A] 커넥션 재사용 | 심이 로컬 ONNX라 왕복 자체가 55ms → 차이 3ms로 측정 불가 | 실기기(고정 오버헤드 2.7s) 전용 측정 |

> **[C]의 발견**: bge-m3 k-NN이 96.0%였는데 e5는 62%다. 같은 데이터·같은 프로토콜에서
> 임베딩 모델만 바꿨는데 33%p 차이 — **k-NN 분류 정확도는 임베딩 모델에 강하게 의존한다.**
> slim 모드의 "분류는 k-NN(96%)" 전제는 bge-m3에서만 확인된 것이므로, 임베딩 모델을
> 바꾸는 일이 생기면 k-NN 정확도부터 다시 재야 한다. (ADR-0002 §5-1에 없던 제약 조건)

### ③ 검증+재시도 — 이 환경에서 완결

시연 5/5·테스트 25건 통과 (위 산출물 표 참고). `/organize/status` 라이브 응답도
생성 모델이 없는 환경에서 `ready:false`와 설치 안내를 정확히 돌려준다 (그레이스풀 처리 실증).

## ⚠️ 로컬 PC(Ollama 있는 곳)에서 돌릴 것 — 수치 채우기

클라우드 세션은 모델을 받을 수 없어 수치 측정만 남았다. 전부 `backend/`에서:

```powershell
# [산출물 ①] 어려운 평가셋 검색 품질 — keyword vs paraphrase 격차가 핵심 지표
.venv\Scripts\python.exe scripts\eval_search.py

# [산출물 ②] 최적화 전/후 벤치마크 — A(커넥션) B(단일질의) C(k-NN) + D(full vs slim)
.venv\Scripts\python.exe scripts\bench_optimization.py --with-llm

# RAG 효과 측정 (2주차 이월 — ADR-0002 §6 재검토 조건)
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --autofix-extension
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --autofix-extension --with-rag

# [산출물 ③] 재시도 실기기 구제율 (요약에 "재시도 n건 중 m건 구제" 출력)
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --retry

# exaone3.5:2.4b 품질 재측정 (slim 기본값 채택 여부 결정)
.venv\Scripts\python.exe scripts\test_models.py --sample 40 --seed 42 --autofix-extension --models exaone3.5:2.4b exaone3.5:7.8b

# 실제 추천 API 동작 확인 (서버는 npm run backend:dev 로)
curl -X POST http://127.0.0.1:8000/organize -H "Content-Type: application/json" ^
     -d "{\"path\": \"C:/Users/blues/Documents/테스트폴더\", \"max_files\": 3}"
curl http://127.0.0.1:8000/organize/status
```

판단 기준
- 평가셋: paraphrase가 keyword 대비 얼마나 떨어지는가 = 문자 일치가 아닌 의미 검색 능력.
  1주차 쉬운 평가셋 100%와 함께 기록해야 정직한 검색 품질이 된다 (ADR-0002 §2 단서 해소)
- RAG: ADR-0002가 잡은 목표 구간 "관례 제공 시 20%→70%" 사이 어디에 떨어지는지
- 2.4b: 파일명 점수·학기 포함률·한국어 유지율이 7.8b 대비 얼마나 빠지는지 (ADR-0002 §5-1)

## 미해결 (이월)

- **계약 이원화** — `contracts/ai.py`(BE1) vs `contracts/api.py`(BE2). `/organize`는 ai.py를 쓰지만
  FE의 `organizeApi.ts`는 아직 `/mock/*` 필드명 기준. FE 바인딩(FE2 3주차 항목)과 함께 정리 필요
- **FE 연결** — `/organize` 응답을 미리보기 표에 바인딩하는 것은 FE2 3주차 항목. 승인 후 apply API는 BE2
- **Ollama 직렬 처리** — 색인·검색·추천이 서로를 막는 문제. 큐 분리 미착수
- **브랜치 구조** — `main`(모노레포) vs `week1-integration`(플랫). 머지 전 팀 논의 필요 (ADR-0001)
- k-NN 실전 정확도 / Drag & Drop 동작 확인 (기존 이월 항목 유지)
