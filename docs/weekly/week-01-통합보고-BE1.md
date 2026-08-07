# 1주차 (2026-07-20 ~ 07-26) — 통합 결과물

**마일스톤 목표**: 데이터셋 확보 및 전처리 과정 파악 & 가짜 서버(Mock) 화면 연동

네 사람의 1주차 산출물을 한 저장소로 합쳤습니다. 결과물은
[`local-file-ai/`](local-file-ai/)에 있습니다.

| | 판정 |
|---|---|
| BE1 · 데이터셋 1,000쌍 + 임베딩 + 모델 선정 + 계약 설계 | **달성** |
| BE2 · 전처리 스크립트 + Mock API 서버 | **달성 · 요구 초과** |
| FE1 · 앱 창 + OS 폴더 경로 인식 + Drag & Drop | **달성 · 요구 초과** |
| FE2 · 레이아웃 + 검색 UI + Mock API 연동 | **달성 · 요구 초과** |
| **1주차 통합 결과물** — 폴더를 고르면 백엔드 데이터가 화면에 뜨는 프로토타입 | **달성** |

**개별 산출물은 네 개 다 완성돼 있었습니다.** 합쳐지지 않았을 뿐입니다.
실제로 이어 붙이는 데 필요한 수정은 **8곳**이었고, 그중 4곳은
**그대로는 컴파일되지 않거나 앱이 켜지지 않는 상태**였습니다 ([§3](#3-합치면서-고친-것)).

합친 뒤 `typecheck` · `lint` · `build` · 서버 기동 · Electron 기동 ·
API 호출 · 실제 PDF 추출까지 **전부 실행해 확인했습니다** ([§4](#4-검증)).

---

## 1. 무엇을 어디서 가져왔는가

| 파트 | 출처 | 상태 |
|---|---|---|
| **BE1 + BE2** | `github.com/localfileai/local-file-ai-backend` (`b4b60cf`) | 이미 한 저장소로 합쳐져 있었음 |
| **FE1** | `ts파일.zip` (electron 4개 파일) + `hongham/local-file-ai-app` 스캐폴딩 | 앱 셸 |
| **FE2** | `1_layout_and_styles.zip` · `2_search_and_filter_ui.zip` · `3_mock_api_integration.zip` | 컴포넌트 6종 + API 클라이언트 3종 |
| **FE2 아이콘** | zip에 없어 팀 자산에서 회수 (`component-10~17.svg`) | Figma 내보내기 |

BE1의 작업은 **이미 BE2 저장소에 들어와 있었습니다.** BE1이 07-27에 직접
PR을 올렸습니다(`e3a65d9`, InhyeokKang). 백엔드는 사실상 통합이 끝난 상태였고,
남은 일은 프론트엔드 두 사람의 결과물을 붙이는 것이었습니다.

## 1-1. 계획서 항목 전수 감사

계획서 3장 [1주차]의 파트별 항목 13개를 병합본 파일과 1:1로 대조했습니다.
**기억이 아니라 파일 존재·실행 결과로 확인한 것입니다.**

| 파트 | 계획서 항목 | 병합본 위치 | 상태 |
|---|---|---|---|
| **BE1** ① | ChromaDB 세팅 및 임베딩 로컬 환경 세팅 | `backend/scripts/embed_dataset.py` | ✅ CLI 정상 동작 |
| **BE1** ② | 데이터셋 약 1,000쌍 생성 및 DB 임베딩 | `backend/scripts/generate_dataset.py` | ✅ 20건 스모크 생성 성공 |
| **BE1** ③ | 베이스 모델 선정 및 프롬프트 테스트 | `backend/scripts/test_models.py` + [ADR-0002](local-file-ai/docs/decisions/0002-model-selection.md) | ✅ CLI 정상 · **선정 결과 기록 추가** |
| **BE1** ④ | RAG 적용 데이터 포맷 구조 설계 | `backend/app/contracts/ai.py` | ✅ 테스트 23건 통과 |
| **BE2** ① | PyMuPDF로 PDF·TXT '첫 페이지만' 추출 스크립트 | `app/extraction/service.py` · `scripts/extract_first_page.py` | ✅ 실제 PDF 5건 검증 |
| **BE2** ② | BE1과 함께 정답 데이터 1,000쌍 구축 보조 | — | ❌ **미수행** (BE1 단독) |
| **BE2** ③ | 하드코딩 더미 응답 Mock API 서버(FastAPI) | `app/api/routes/mock.py` | ✅ 7종 전건 200 |
| **FE1** ① | Electron+Vite+React+TS 초기 프로젝트 · 독립 앱 창 | `electron/main.ts` · `vite.config.ts` | ✅ 창 기동 확인 |
| **FE1** ② | OS 폴더 선택 창 + IPC로 경로를 React state로 | `main.ts` · `preload.ts` · `App.tsx` | ✅ 코드 반영 |
| **FE1** ③ | Drag & Drop 이벤트 로직 | `preload.ts` · `App.tsx` | 🟡 코드 반영 · **동작 미확인** |
| **FE2** ① | Tailwind 세팅 · 레이아웃(사이드바, 메인) | `components/Sidebar.tsx` · `Header.tsx` | ✅ CSS 32.97 kB 생성 |
| **FE2** ② | 자연어 검색창 및 결과 리스트 UI 마크업 | `components/MainView.tsx` · `FileResultCard.tsx` | ✅ |
| **FE2** ③ | BE2 Mock API와 통신해 더미 데이터 화면 표시 | `src/api/*.ts` | ✅ `rename=4 move=3 files=8` |

**✅ 11개 완전 반영 · 🟡 1개 동작 미확인 · ❌ 1개 미수행**

### BE1 산출물 4개는 계획서 4개 항목과 1:1로 맞습니다

BE1 보고서의 산출물 표가 계획서 항목과 정확히 대응하고, **넷 다 병합본에서 실행됩니다.**

| 계획서 항목 | BE1 산출물 파일 | 병합본 경로 | 실행 확인 |
|---|---|---|---|
| ① ChromaDB 세팅·임베딩 환경 | `embed_dataset.py` | `backend/scripts/embed_dataset.py` | `--help` 정상 |
| ② 데이터셋 1,000쌍 + DB 임베딩 | `generate_dataset.py` | `backend/scripts/generate_dataset.py` | 20건 생성 성공 |
| ③ 베이스 모델 선정 | `test_models.py` | `backend/scripts/test_models.py` | `--help` 정상 |
| ④ RAG 데이터 포맷 구조 | `schemas.py` | `backend/app/contracts/ai.py` | 테스트 23건 통과 |

`schemas.py`가 `app/contracts/ai.py`로 이동했는데도 `test_models.py`가 깨지지 않습니다.
`sys.path`에 프로젝트 루트를 넣고 `from app.contracts.ai import ...`로 이미 고쳐져 있습니다.

```python
# scripts/test_models.py L32-36
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
...
from app.contracts.ai import MAX_FIRST_PAGE_CHARS, FileSuggestion
```

생성기 실제 실행 결과입니다.

```
python scripts/generate_dataset.py --output dataset_smoke --count 20 --overwrite
→ 20쌍 · 첫 페이지 추출 20/20 성공 · pdf 5 / txt 6 / md 9
→ 정답 3종 모두 채워짐:
   검색키워드 "동적 계획법|그리디|최적 부분 구조"
   분류폴더   lecture
   추천파일명 알고리즘_동적_계획법과_그리디_비교_강의자료_2026-1.pdf
```

### ③의 결론이 빠져 있었습니다 — 추가했습니다

`test_models.py`가 돌아간다고 항목이 반영된 게 아닙니다. **BE1 ③의 산출물은
"선정"이라는 결정**인데, 병합본에는 그 결정이 어디에도 없었습니다.

```python
# scripts/test_models.py — 후보 목록일 뿐, 무엇이 선정됐는지 알 수 없음
DEFAULT_MODELS = ["exaone3.5:7.8b", "qwen2.5:7b", "llama3.1:8b"]
```

`docs/`도 없고 근거인 `model_test_results.csv`는 `.gitignore` 대상이라
**코드만 봐서는 `exaone3.5:7.8b`가 선정됐다는 사실을 알 수 없는 상태**였습니다.
README도 `ollama pull exaone3.5:7.8b`라고만 적어 설치 안내처럼 보였습니다.

두 모델의 처지가 달랐습니다.

| 결정 | 반영 상태 (수정 전) |
|---|---|
| 임베딩 `bge-m3` | ✅ `embed_dataset.py`의 `DEFAULT_MODEL`로 코드에 고정 |
| LLM `exaone3.5:7.8b` | ❌ 후보 3종 중 하나로만 등장 |

→ **`docs/decisions/0002-model-selection.md`를 추가했습니다.** BE1의 1주차 실측을
   그대로 옮겼습니다 — 1·2차 측정표, 파일명 구성요소별 포함률, 한국어 유지율,
   임베딩 모델 비교, 검색 품질 23건, 재현 명령, 재검토 시점.
→ README 최상단에 **"선정된 모델"** 표를 넣어 결론이 먼저 보이게 했습니다.
→ ADR에 **"결정이 코드 어디에 반영돼 있는가"** 표를 넣어, 1주차에는 LLM을 런타임에서
   쓰지 않아 설정 파일이 없다는 점과 2주차에 `OLLAMA_GENERATE_MODEL` /
   `OLLAMA_EMBED_MODEL` 기본값으로 고정해야 한다는 점을 명시했습니다.

> 문서 번호를 `0002`로 맞춘 이유: `localfileai/localfile-ai`의 ADR-0002가 같은 결정을
> 다루지만 **8종 카테고리 데이터셋** 기준이라 수치가 다릅니다(분류 70.0% 등).
> 이 병합본 코드는 **6종** 기준이므로 새로 쓴 문서의 수치가 현재 코드와 맞습니다.
> 두 저장소를 합칠 때 섞지 말아야 합니다. `ADR-0001`(모노레포)은 그쪽에만 있습니다.

### 생성 산출물은 저장소에 없습니다 (정상)

`dataset/` `chroma_db/` `model_test_results.csv` `search_eval.json`은 `.gitignore`
대상입니다. 수백 MB를 커밋할 이유가 없고, 명령으로 다시 만들 수 있습니다.

**대신 BE1 보고서의 수치는 재현하지 않았습니다.** 임베딩과 모델 비교에 Ollama가
필요해서입니다. Recall@5 100%, exaone3.5 파일명 88.5% 같은 값은 **본인 보고 기준**입니다.

> 보조 도구 `verify_dataset.py` `eval_search.py` `show_samples.py` `probe_failures.py`는
> BE1 보고서의 "팀에 보여줄 것" 명령 목록에 나오지만 **계획서가 요구한 산출물은 아닙니다.**
> 있으면 위 수치를 팀이 직접 재현할 수 있으니 받아 두면 좋습니다 —
> 필수가 아니라 편의입니다.

### 팀 통합 목표 대비

| 계획서 통합 목표 | 결과 |
|---|---|
| 백엔드: 1,000쌍 생성 및 DB 임베딩 완료 | ✅ 생성기·임베딩 코드 반영 (데이터는 명령으로 복원) |
| 프론트엔드: 빈 화면이지만 켜지고 폴더 경로를 OS로부터 인식 | ✅ **초과** — 빈 화면이 아니라 완성된 3화면 |
| 통합 결과물: 폴더 고르고 버튼 누르면 더미 데이터가 화면에 출력 | ✅ 달성 |

> 한 가지 뉘앙스: 계획서는 "폴더를 고르고 버튼을 누르면 더미 데이터가 출력"이라고
> 적었지만, `/mock/*`은 하드코딩이라 **폴더 선택과 더미 데이터 사이에 인과가 없습니다.**
> 앱 시작 시 한 번 불러옵니다. 대신 폴더 선택은 **실제 추출**을 구동합니다(§3-9).
> 폴더가 Mock 데이터를 바꾸게 하려면 실제 인덱싱이 필요하고, 그건 2주차입니다.

## 1-2. 추가 구현 — 실제 자연어 검색 (2주차 선행)

> **범위 표시**: 계획서상 이건 **2주차** 항목입니다.
> 1주차 마일스톤은 "백엔드의 **가짜 데이터**를 받아오는 초기 앱"이고,
> "가짜 데이터 대신 기본 AI 모델과 진짜 DB를 연결하여 검색과 추천이 실제로 동작"은
> 2주차 결과물입니다. BE2의 2주차 항목도 "Mock API를 실제 Ollama 연동으로 교체"입니다.
>
> 그런데 1주차 병합만으로는 **BE1의 기여가 앱과 완전히 끊겨 있습니다.**
> 검색이 하드코딩 4줄이고, 1,000쌍과 선정한 두 모델을 앱이 쓰지 않습니다.
> BE1(강인혁) 요청으로 이 연결을 선행 구현했습니다.
> **1주차 Mock 경로(`/mock/*`)는 그대로 남겨 두어 1주차 결과물 주장은 유지됩니다.**

### 무엇이 실제로 도는가

```
검색창에 자연어 입력
  → bge-m3 로 질의를 1024차원 벡터화        (BE1 선정 임베딩 모델)
  → ChromaDB `file_documents` 유사도 검색   (BE1 scripts/embed_dataset.py 가 만든 색인)
  → BE1 계약 SearchResponse 로 검증해 응답  (app/contracts/ai.py — 지금까지 죽은 코드였음)
  → 결과 카드 클릭 → 실제 파일 원문 미리보기 (BE2 extraction/service.py)
```

**모델 역할을 구분해야 합니다.** 사용자가 "파일을 찾을 때 선정한 모델이 쓰여야"라고 할 때,
검색에 쓰이는 것은 LLM이 아니라 임베딩 모델입니다.

| 기능 | 쓰이는 모델 | 이번에 연결됨 |
|---|---|---|
| ① 자연어 파일 검색 | **`bge-m3`** (임베딩) | ✅ |
| ②③ 분류 · 파일명 추천 | `exaone3.5:7.8b` (LLM) | ❌ 2주차 (`/mock/*` 유지) |

**파인튜닝은 하지 않습니다.** 기획안 §1이 RAG를 채택했습니다 — 사전 학습된 모델을
그대로 쓰고 유사 문서를 프롬프트에 주입하는 방식입니다. "탑재"는 가중치 변경이 아니라
연동입니다. (계획안 파이프라인 다이어그램의 "파인튜닝이 완료된 로컬 LLM"이라는 표현은
본문 §1의 RAG 결정과 어긋나므로 팀에서 문구를 정리해야 합니다.)

### 추가한 파일

| 파일 | 역할 |
|---|---|
| `backend/app/rag/embedding.py` | Ollama `bge-m3` 어댑터. BE1 스크립트와 **같은 모델·같은 컬렉션** |
| `backend/app/rag/search.py` | 유사도 검색. 결과를 BE1 계약 `SearchResponse`로 검증 |
| `backend/app/api/routes/search.py` | `GET /search` · `GET /search/status` |
| `src/api/searchApi.ts` | `fetchRealSearchResults` · `fetchSearchStatus` 추가 |
| `src/components/MainView.tsx` | 엔진 전환(실제/Mock), 색인 상태 표시, 실패 이유 표시 |

색인은 **BE1의 스크립트가 그대로 담당**합니다(`scripts/embed_dataset.py`).
앱은 같은 컬렉션을 읽기만 합니다. 즉 BE1의 산출물이 앱의 색인 파이프라인입니다.

### 화면에서 1주차와 2주차를 구분해 둔 이유

검색창 위에 엔진 토글을 뒀습니다.

- **`실제 검색 · bge-m3`** — 이번에 붙인 것. 색인이 준비돼야 활성화됩니다
- **`Mock · 1주차`** — 계획서상 1주차 결과물. 그대로 남아 있습니다

색인이 없으면 토글이 비활성화되고 이유가 표시됩니다
(`벡터 색인이 없습니다`, `임베딩 모델이 없습니다: bge-m3` 등). 결과 패널에도
어느 엔진이 답했는지 배지로 남습니다. 데모할 때 무엇이 진짜인지 헷갈리지 않게 하려는 것입니다.

### 성능 실측 — 2주차 계획에 직접 영향이 있습니다

BE1 보고서는 **RTX 3060 Ti** 기준이고, 이번 검증 PC는 **AMD 내장 그래픽**이라
Ollama가 CPU로 돕니다. 그래서 GPU 유무의 영향을 작업별로 분리해 볼 수 있었습니다.

| 작업 | BE1 (RTX 3060 Ti) | 이 PC (CPU) | 격차 |
|---|---|---|---|
| 문서 임베딩 (색인) | 8.3건/s | 0.22건/s (4.6초/건) | **38배** |
| 질의 임베딩 (검색) | 2.3초 | 2.8초 | **1.2배** |
| **LLM 추천 (기능②③)** | **4.19초/파일** | **81.1초/파일** (중위) | **19배** |

#### ① 질의 지연의 96%는 모델 계산이 아니라 요청 오버헤드다

부하 없는 상태에서 한 요청에 담는 질의 수를 늘려 재봤습니다.

```
질의  1건 (요청 1회): 2.806초
질의  5건 (요청 1회): 3.183초  -> 건당 0.637초
질의 10건 (요청 1회): 3.790초  -> 건당 0.379초

  추정 요청당 고정비용 = 2.696초
  추정 질의당 계산비용 = 0.109초
  -> 질의 지연의 96.1%가 고정 오버헤드
```

질의를 9개 더 넣어도 1초만 늘어납니다. **실제 임베딩 계산은 0.11초**이고
나머지 2.7초는 페이로드 크기와 무관한 고정 비용입니다.

**BE1 보고서의 "질의당 2.3초는 대부분 질의 임베딩 시간"은 원인 지목이 틀렸습니다.**
그래서 3주차 최적화 방향이 달라집니다.

| 안 통하는 대책 | 근거 |
|---|---|
| GPU 붙이기 | BE1의 GPU 2.3초 vs 이 PC CPU 2.8초 — 0.5초 차이뿐 |
| 더 작은 임베딩 모델 | 계산이 이미 0.11초라 줄일 여지가 없음 |

→ **줄여야 할 것은 요청당 오버헤드입니다.** 커넥션 재사용(`requests.Session`),
   모델 상주(`keep_alive`), 배치 처리가 실효 있는 대책입니다.

#### ② Ollama는 요청을 직렬 처리한다 — 색인 중 검색은 막힌다

색인이 도는 중에 질의를 보내니 **47.4초**가 걸렸습니다. 계산이 아니라
진행 중인 색인 배치(16건 × 4.6초 ≈ 74초)가 끝나기를 기다린 큐 대기입니다.
2주차에 증분 인덱싱(Watchdog)을 붙이면 **사용자가 검색하는 동안 색인이 돌아
검색이 수십 초 멈추는** 상황이 생깁니다. 색인 우선순위를 낮추거나 큐를 분리해야 합니다.

#### ③ 가장 큰 위험 — 외장 GPU 없는 PC에서 기능②③은 쓸 수 없다

`exaone3.5:7.8b`로 실제 추천을 3건 돌렸습니다(BE1과 같은 프롬프트 형태).

```
[1/3]  116.4초  생성토큰 124  temp_5.pdf   -> lecture / 동적_계획법과_그리디_비교_알고리즘_2026-1.pdf
[2/3]   75.7초  생성토큰 134  asdf 2.txt   -> assignment / 알고리즘_동적계획법그리디비교_과제_2025-2.txt
[3/3]   81.1초  생성토큰 154  스캔(2).md    -> report / 데이터베이스_트랜잭션_동시성제어_실험보고서_2024-2.md

평균 91.1초 · 중위 81.1초 · 계약 통과 3/3 · BE1 GPU 대비 19배
파일 30개 폴더 예상: 40.5분
```

**추천 품질 자체는 정상입니다** — 세 건 모두 BE1 계약을 통과했고 분류·파일명도 타당합니다.
문제는 속도입니다.

왜 LLM만 이렇게 느린지는 구조 차이입니다.

| | `bge-m3` | `exaone3.5:7.8b` |
|---|---|---|
| 아키텍처 | **bert (인코더)** | **exaone (디코더)** |
| 파라미터 | 566.70M | 7.8B |
| 양자화 / 크기 | F16 · 약 1.13GB | Q4_K_M · 약 4.44GB |

인코더는 입력 전체를 **한 번의 순전파**로 처리합니다. 디코더는 출력 토큰마다
**가중치 전체를 메모리에서 다시 읽습니다.** 130토큰이면 4.44GB를 130번 훑어
약 577GB 전송이고, 이건 연산량이 아니라 **메모리 대역폭** 문제입니다
(CPU 약 50GB/s vs 3060 Ti 약 448GB/s).

**기획안 타깃은 "Windows를 사용하는 20대 대학생"입니다.** 상당수가 외장 GPU가 없고,
그 PC에서 폴더 하나(30개)를 정리하는 데 40분이 걸립니다. 2주차에 Mock을 실제 LLM으로
교체하는 순간 부딪힙니다.

검토할 대책입니다.

#### ④ 해결책을 실측했습니다 — 81초 → 13초

두 가지를 재서 확인했습니다. 상세는 [ADR-0003](local-file-ai/docs/decisions/0003-offline-and-low-spec.md).

**분류(기능②)는 LLM이 필요 없습니다.** 이미 계산한 임베딩으로 최근접 이웃의
카테고리를 다수결하면 됩니다. 추가 비용 0입니다.

처음 100%가 나왔는데 **데이터셋 인공물**이었습니다 — top-1 이웃이 100% 같은 주제·
같은 유형의 쌍둥이(거리 0.0176)였습니다. 생성기가 120조합으로 1,000건을 만들어
조합당 8건씩 본문이 거의 같습니다. **같은 주제를 전부 배제**해 다시 재니:

| 방식 | 정확도 | 파일당 비용 |
|---|---|---|
| 무작위 (6종) | 16.7% | — |
| **k-NN k=3 (같은 주제 배제)** | **96.0%** | **0초** |
| exaone3.5:7.8b (GPU) | 95.0% | 4.19초 |
| exaone3.5:7.8b (CPU) | 95.0% | 81.1초 |

**LLM과 동등하거나 낫고 공짜입니다.** 단, 이 데이터셋은 본문에 `문서 유형:`이
글자로 적혀 있어 실전 정확도는 다시 재야 합니다.

**남는 파일명 생성은 출력 축소 + 소형 모델로 줄입니다.**

| 모델 | 출력 계약 | 토큰 | 중위 시간 |
|---|---|---|---|
| `exaone3.5:7.8b` | full (5필드) | 143 | 47.8초 |
| `exaone3.5:7.8b` | slim (파일명만) | 31 | 29.7초 |
| `exaone3.5:2.4b` | full | 172 | 23.9초 |
| **`exaone3.5:2.4b`** | **slim** | **31** | **13.0초** |

디코더는 출력 토큰마다 가중치 전체를 다시 읽으므로 생성 시간이 출력 길이에 비례합니다.
분류를 k-NN이 맡으면 LLM은 파일명 한 줄만 만들면 됩니다.

**사양별 동작 계층 권고**

| 사양 | ① 검색 | ② 분류 | ③ 파일명 | 30개 폴더 |
|---|---|---|---|---|
| **GPU 없음** | `bge-m3` 2.8초 | k-NN 0초 | `2.4b` slim 13초 | **약 6.5분** |
| **GPU 8GB+** | 동일 | k-NN 0초 | `7.8b` full 4.19초 | 약 2분 |

기존 40.5분 → 6.5분입니다. `exaone3.5:2.4b`(1.53GB)는 같은 계열이라 한국어가
유지됩니다. **다만 품질은 속도만 잰 것이라 `test_models.py`로 7.8b와 같은 기준
재측정이 필요합니다** — slim 계약에서 학기가 빠진 사례가 관찰됐습니다.

→ **2주차 시작 전 BE1·AI 결정 필요.**

### 데이터셋 재현 결과 — BE1 보고서와 완전 일치

### 실제로 확인한 것 (전부 실행)

| 항목 | 결과 |
|---|---|
| `bge-m3` 내려받기 | 1.08GB · F16 · BERT 인코더 · 566.70M 파라미터 |
| 1,000건 색인 | **완료** · 2,994초(약 50분) · `chroma_db/` 28.2MB |
| `GET /search/status` | `{ready: true, indexed_documents: 1000}` |
| `GET /search` | 3개 질의 모두 정답 주제 1위 |
| `POST /preprocess/extract-first-page` | 검색 1위 파일의 실제 원문 추출 성공 |
| 앱 렌더러 → 백엔드 | `GET /search/status` 200 · `GET /search?q=...` 200 |
| typecheck · lint · build | 전부 통과 (CSS 33.65 kB) |

BE1 보고서와 같은 질의 3건입니다. **1,000건 색인 기준**입니다.

```
"OSPF BGP 비교한 문서"     1위 aaa_11.txt      score 0.6851  라우팅 프로토콜 비교
"공개키 암호화 정리한 거"   1위 정리_16.pdf     score 0.6779  대칭키와 공개키 암호
"퀵소트 시간복잡도 정리"    1위 무제.pdf        score 0.6687  정렬 알고리즘 성능 분석
```

**`aaa_11.txt` `정리_16.pdf` `무제.pdf` 같은 지저분한 이름을 내용으로 찾았습니다.**
기획안의 문제 정의(`최종.pdf`, `발표자료 2.pdf`)가 실제로 해결되는 것을 확인한 셈입니다.

거리도 BE1 보고서와 맞습니다 — "공개키 암호화 정리한 거"의 distance가
보고서 **0.3218**, 재현 **0.3221**입니다.

렌더러가 실제로 호출한 기록입니다(앱 안에서).

```
127.0.0.1 - "GET /search/status HTTP/1.1"                    200 OK
127.0.0.1 - "GET /search?q=<공개키 암호화 정리한 거>&top_k=3"   200 OK
127.0.0.1 - "POST /preprocess/extract-first-page"            200 OK
```

### ⚠️ 고친 버그 — 경로에 한글이 있으면 ChromaDB가 색인을 못 읽는다

색인은 성공했는데 검색이 이 오류로 계속 실패했습니다.

```
Error constructing hnsw segment reader: Error loading hnsw index
```

원인을 좁혀 보니 **경로에 비ASCII 문자(한글)가 있을 때 절대 경로로는 열리지 않습니다.**
같은 색인을 상대 경로로 열면 정상입니다.

```
cwd = C:\Users\blues\LocalFileAI-1주차-결과물\local-file-ai\backend   (한글 포함)
  상대경로 'chroma_db'                    -> OK   count=1000
  절대경로 'C:\...\1주차-결과물\...\chroma_db' -> 실패 (hnsw 로드 오류)
```

ChromaDB 1.5.9의 Rust HNSW 리더 문제로 보입니다.
→ `_chroma_path_for_client()`가 경로에 비ASCII가 있으면 **상대 경로로 바꿔** 넘깁니다.

**팀에 공유해야 합니다.** 프로젝트를 한글이 든 폴더(`바탕화면`, `내 문서`, 학번·이름 폴더)에
두면 그대로 겪습니다. 2주차에 BE2가 ChromaDB를 붙일 때도 같은 함정이 있습니다.

> 처음에는 "요청마다 `PersistentClient`를 새로 만들어서"라고 잘못 짚었습니다.
> 그건 별개로 성능상 좋지 않아 **프로세스당 1개로 캐시**하도록 함께 고쳤습니다
> (`threading.Lock`으로 보호, 실패는 캐시하지 않음). 근본 원인은 한글 경로였습니다.

### 데이터셋 재현 결과 — BE1 보고서와 완전 일치

`generate_dataset.py`를 기본 시드(`20260727`)로 다시 돌렸습니다.

| 항목 | BE1 보고서 | 재현 |
|---|---|---|
| 확장자 | pdf 412 · md 311 · txt 277 | **동일** |
| 정답 폴더 | lecture 181 · exam_prep 180 · assignment 175 · report 168 · reference 155 · project 141 | **동일** |
| 첫 페이지 추출 | 1,000/1,000 성공 | **동일** |

②의 산출물이 결정적으로 재현됩니다.

## 2. 합친 결과

```
local-file-ai/
├─ electron/            main.ts · preload.ts · electron-env.d.ts      FE1
├─ src/
│  ├─ App.tsx           ← 새로 작성. FE1과 FE2가 만나는 지점
│  ├─ types.ts          ← 새로 작성. Menu 타입 공용화
│  ├─ components/       Sidebar · Header · MainView · OrganizedView ·
│  │                    AllFilesView · FileResultCard                 FE2
│  └─ api/              organizeApi · searchApi · preprocessApi       FE2
├─ public/              component-10~17.svg                           FE2
├─ scripts/backend.mjs  ← 새로 작성. 크로스플랫폼 venv/서버 실행
└─ backend/             app/ · scripts/ · mock/                    BE1+BE2
```

동작 흐름입니다. **네 사람의 코드가 이 한 줄에서 만납니다.**

```
[폴더 선택] 클릭 또는 Drag & Drop
  → FE1  electron/main.ts   dialog:openDirectory (OS 네이티브 창)
  → FE1  electron/preload.ts window.api.selectFolder / getPathForFile
  → 통합  src/App.tsx        selectedPath 상태
  → FE2  Header · Sidebar   경로와 폴더명 표시
  → FE2  src/api/*.ts       fetch → 127.0.0.1:8000
  → BE2  /mock/* /preprocess/*
  → BE1  app/contracts/ai.py 응답 형식 검증 기준
```

### 실행

```powershell
cd local-file-ai
npm install ; npm run backend:install     # 최초 1회

npm run backend:dev    # 터미널 1
npm run dev            # 터미널 2 — Electron 창
```

Electron이 백엔드를 자동 기동하는 것은 계획서상 **2주차 FE1 항목**이라
1주차 범위에서는 터미널 두 개로 두었습니다.

---

## 3. 합치면서 고친 것

6곳입니다. 각각 왜 필요했는지 적었습니다.

### 3-1. `PreviewItem`이 없어서 FE2 코드가 컴파일되지 않았다 (차단)

`FileResultCard.tsx`(zip 2)가 이렇게 import합니다.

```ts
import { getPreprocessPreview, PreviewItem } from '../api/preprocessApi';
```

그런데 `preprocessApi.ts`(zip 3)는 `PreprocessPreviewResponse`만 export하고
**`PreviewItem`을 정의하지 않았습니다.** zip 2와 zip 3이 서로 다른 시점의
코드였던 것으로 보입니다.

→ 백엔드 `ExtractedDocument`의 필드를 그대로 옮겨 `PreviewItem`을 정의했습니다.

### 3-2. 미리보기 모달에 JSON 원문이 뜬다

`FileResultCard`는 응답에서 `first_page_text`를 읽습니다.

```ts
const extractedText = res.first_page_text || res.text || res.content
  || (typeof res === 'string' ? res : JSON.stringify(res, null, 2));
```

백엔드 `ExtractPathResponse`는 `{ count, items[] }`입니다.
세 후보가 전부 `undefined`라 **마지막 `JSON.stringify`가 실행됩니다.**
미리보기 창에 문서 텍스트가 아니라 응답 JSON이 그대로 노출됩니다.

→ `preprocessApi`에서 `items[0].preview_text`를 `first_page_text`로 평탄화했습니다.
   추출 실패 시 `error` 사유를, 지원 확장자가 없으면 안내 문구를 넣습니다.
   **백엔드 계약은 건드리지 않았습니다** — 불일치가 FE 쪽에 있으므로 어댑터로 해결.

### 3-3. `Header`가 'files' 탭을 모르고, [폴더 선택] 버튼에 onClick이 없다

```ts
interface HeaderProps { currentMenu: 'search' | 'organize'; }   // 'files' 누락
```

FE2의 `App.jsx`는 `<Header />`로 **props를 아예 넘기지 않고** 있었고,
Sidebar는 'files' 탭을 갖고 있습니다. 타입이 맞지 않습니다.
그리고 [폴더 선택] 버튼은 마크업만 있고 핸들러가 없었습니다 —
**여기가 FE1의 IPC가 들어갈 자리입니다.**

→ `Menu` 타입으로 통일, 'files' 제목 추가, `onSelectFolder`·`selectedPath` props 추가,
   버튼에 `onClick` 연결. 인식한 경로를 헤더에 코드칩으로 표시합니다.

### 3-4. Sidebar의 폴더명이 'Documents'로 하드코딩돼 있다

FE1이 경로를 인식해도 화면에 반영될 곳이 없었습니다.

→ `folderName` prop 추가(기본값 `'Documents'`). App이 `selectedPath`의
   마지막 세그먼트를 넘깁니다.

### 3-5. Tailwind 설정이 두 갈래고, FE1의 index.css가 FE2 디자인을 깨뜨린다

| | FE1 | FE2 |
|---|---|---|
| 방식 | `@tailwindcss/vite` 플러그인 (**v4**) | `tailwind.config.js` + `postcss.config.js` (**v3 관례**) |
| `index.css` | `@import "tailwindcss"` + Vite 템플릿 스타일 | `@import "tailwindcss"` 한 줄 |

두 문제가 있었습니다.

1. `postcss.config.js`가 `@tailwindcss/postcss`를 참조하는데 `package.json`에
   그 패키지가 없습니다. → 빌드 실패.
2. FE1의 `index.css`는 Vite 템플릿 그대로입니다.
   `background-color: #242424`, `body { display:flex; place-items:center }`,
   `button { background-color:#1a1a1a; padding:0.6em 1.2em }`.
   Tailwind v4는 유틸리티를 `@layer`에 넣으므로 **레이어 밖의 이 element 규칙이
   우선합니다.** FE2의 `bg-white`, 버튼 스타일이 전부 덮여 화면이 깨집니다.

→ v4 방식(`@tailwindcss/vite`)으로 통일하고 `tailwind.config.js`·`postcss.config.js`를
   버렸습니다. `index.css`는 FE2 버전(한 줄)을 채택했습니다.
   FE2의 `App.css`도 버렸습니다 — Vite 템플릿 데모용(`.counter`, `.hero`)이고 쓰이지 않습니다.

### 3-6. npm 스크립트가 Windows에서 실행되지 않는다

기획안의 타깃은 **Windows 사용 대학생**이고 4주차 결과물은 `setup.exe`입니다.
그런데 백엔드 실행에 필요한 명령이 POSIX 전용 문법이었습니다
(`python3`, `.venv/bin/python`, `if [ -x ... ]`).

→ 플랫폼 분기를 `scripts/backend.mjs`(Node)로 옮겼습니다.
   Windows는 `.venv\Scripts\python.exe`와 `python`(없으면 `py -3`),
   그 외는 `bin/python`과 `python3`. `pip.exe` 직접 호출이 Smart App Control에
   막히는 사례가 있어 항상 `python -m pip`를 씁니다.

### 3-7. `ELECTRON_RUN_AS_NODE` — 앱이 아예 켜지지 않았다 (차단)

**이건 실제로 앱을 띄워 보고 나서야 찾았습니다.** 첫 `npm run dev`가 이렇게 죽었습니다.

```
SyntaxError: The requested module 'electron' does not provide an export named 'BrowserWindow'
Node.js v20.16.0
```

원인은 환경변수 `ELECTRON_RUN_AS_NODE=1`입니다. 이 변수가 있으면
`electron.exe`가 GUI 런타임이 아니라 **순수 Node로** 동작합니다. 그러면
`import { BrowserWindow } from 'electron'`이 실행 파일 경로만 export하는
CJS 셰임으로 해석돼 위 에러가 납니다. 트레이스백의 `Node.js v20.16.0`이
Electron 30이 내장한 Node 버전이라는 게 단서였습니다.

**VS Code가 자식 프로세스에 이 변수를 물려줍니다** (확장 호스트 환경).
실제로 확인했습니다.

```
ELECTRON_RUN_AS_NODE = 1
VSCODE_CRASH_REPORTER_PROCESS_TYPE = extensionHost
```

즉 **VS Code 터미널에서 `npm run dev`를 하면 앱이 안 켜집니다.**
팀 전원이 VS Code를 쓸 테니 사실상 항상 걸립니다.

> **앞선 분석을 정정합니다.** 팀원의 시험 병합본에 있던
> `"dev": "env -u ELECTRON_RUN_AS_NODE vite"`를 저는 "POSIX 전용이라 Windows에서
> 안 된다"고만 지적했습니다. 이식성 지적 자체는 맞지만, **그 플래그는 이 실제
> 문제를 고치던 것이었습니다.** 이식성만 보고 걷어내면서 의도까지 지웠고,
> 그래서 첫 실행이 실패했습니다.

→ `scripts/dev.mjs`로 되살렸습니다. vite를 띄우기 전에 이 변수를 지우고,
   vite가 스폰하는 Electron이 그 환경을 물려받게 합니다.
   `env` 명령이 없는 Windows에서도 동작합니다.

수정 후 재실행 결과입니다.

```
[dev] ELECTRON_RUN_AS_NODE 를 해제합니다 (VS Code 등에서 상속됨).
VITE v5.4.21  ready in 1198 ms
→ electron 프로세스 4개, 창 제목 "LocalFile AI"
```

### 3-8. 타입체크·린트가 잡아낸 FE2 코드의 실제 버그

`npm run typecheck`를 처음 돌렸을 때 2건이 나왔습니다. **둘 다 FE2 코드입니다.**

```
src/components/MainView.tsx(62,76): error TS2304: Cannot find name 't'.
src/components/OrganizedView.tsx(175,3): error TS6133: 'currentFiles' is declared but its value is never read.
```

첫 번째는 **런타임 버그**입니다.

```ts
// MainView.tsx — 검색 대상 필터 토글
prev.includes(target) ? prev.filter((t) => t !== target) : [...prev, t]
//                                                                   ↑ 존재하지 않는 이름
```

`t`는 바로 앞 `filter` 콜백의 인자라 이 위치에 없습니다.
바로 위 확장자 토글(55행)은 `[...prev, type]`로 올바르게 쓰고 있어 단순 오타입니다.
**검색 대상 칩을 누르면 터집니다.** 타입체크가 잡아 줬습니다.

→ `[...prev, target]`으로 수정.
→ `OrganizedView`의 `currentFiles`는 구조 분해에서만 제거(props 타입에는 유지).
   전체 목록은 `AllFilesView` 담당이라 이 컴포넌트에서 쓰지 않습니다.

린트는 `no-explicit-any` 4건이었습니다. FE2의 API 클라이언트가
`(item: any, index: number)`로 백엔드 응답을 매핑하고 있었습니다.

→ 백엔드 응답 형태를 `RawRenameItem` · `RawMoveItem` · `RawCurrentFile` ·
   `RawSearchItem`으로 정의했습니다. 필드는 전부 optional입니다 —
   계약이 아직 둘이라([§5-4](#5-4-계약이-여전히-둘이다--2주차-최우선)) 어느 쪽 필드가
   와도 화면이 죽지 않게 후보를 열어 둔 FE2의 원래 의도를 유지하기 위해서입니다.
   중복되던 `confidence` 변환 로직도 `toConfidenceString()` 하나로 모았습니다.
   **2주차에 계약을 합치면 이 타입들을 정확한 필드만 남기고 좁혀야 합니다.**

### 3-9. 실제 클릭해 보고 나서 찾은 것 두 개

앱을 켜서 눌러 보기 전까지는 드러나지 않았던 문제입니다.

**① 미리보기가 폴더 경로에 확장자를 붙여 보내고 있었다 (FE2 버그)**

`FileResultCard`가 백엔드에 보내던 경로입니다.

```ts
let targetPath = item.path || '';        // "Documents/연구/TSN"  ← 폴더 경로
if (!hasExtension) targetPath += '.pdf'  // "Documents/연구/TSN.pdf"
```

`item.path`는 **폴더**고 파일명은 `item.title`에 따로 있습니다.
파일명을 붙이지 않고 폴더에 확장자를 붙여 보내니 **항상 실패합니다.**

여기에 더해 **`selectedPath`가 `MainView`·`FileResultCard`까지 내려가지 않았습니다.**
폴더를 골라도 미리보기에는 아무 영향이 없었습니다.

→ 경로 조립을 `선택폴더 + 실제 파일명`으로 고치고, `selectedPath`를 내려보냈습니다.
   실패 시 시도한 경로와 이유를 화면에 적습니다.

**② 1주차의 유일한 실기능이 UI에서 도달 불가였다**

검색 결과는 하드코딩 Mock이라 파일명이 실제로 존재하지 않습니다. 즉 경로를 고쳐도
Mock 결과를 눌러서는 추출을 볼 수 없습니다. **실제 추출은 API로만 확인 가능한 상태**였습니다.

→ `MainView`에 **"선택한 폴더의 실제 문서"** 섹션을 추가했습니다.
   폴더를 고르면 `POST /preprocess/extract-first-page`로 그 폴더의 PDF·TXT·MD를
   실제로 추출해 목록으로 보여주고, `원문`을 누르면 텍스트가 펼쳐집니다.
   `preprocessApi.listFolderDocuments()`를 새로 뺐습니다.

실행 중인 앱에서 확인한 결과입니다 (렌더러 콘솔).

```
[검증-추출] items=5 error="" first="(TSN)Implementation_and_Evaluation_…pdf" text=1498자
```

### 3-10. Drag & Drop — 원인 후보를 모두 막고 실패를 드러냈다

**GUI 드래그를 재현할 수 없어 근본 원인을 확정하지는 못했습니다.**
확인한 것과 고친 것만 적습니다.

먼저 배제한 것: `webUtils`가 Electron 30에 없어서가 **아닙니다.**
`node_modules/electron/electron.d.ts`에 `getPathForFile(file: File): string`이 있습니다.

고친 원인 후보 셋입니다.

| 후보 | 내용 |
|---|---|
| `dragenter` 미처리 | Chromium은 `dragenter`/`dragover` 중 하나에서 `preventDefault()`를 해야 그 요소를 유효한 드롭 대상으로 봅니다. `dragover`만 있었습니다 |
| `dragleave` 오작동 | 자식 요소를 넘나들 때마다 발생해 드래그 중에 상태가 꺼졌습니다. 깊이 카운터로 창을 완전히 벗어났을 때만 끄게 했습니다 |
| **경로 추출 실패가 조용히 묻힘** | `webUtils.getPathForFile`이 contextBridge를 건너온 File에서 예외를 던지거나 빈 문자열을 반환하면, `files.map(...)`이 통째로 터지고 **아무 일도 없었던 것처럼 보입니다.** 가장 유력한 원인입니다 |

→ preload에서 `webUtils.getPathForFile` → `File.path`(Electron 30에 남아 있고 32에서 제거)
   순으로 폴백하고, 둘 다 실패하면 빈 문자열을 돌려줍니다.
→ 앱은 빈 결과를 무시하지 않고 **빨간 배너로 알립니다** — 어느 파일이 실패했는지와
   콘솔의 `[preload]` 로그를 보라는 안내를 함께 띄웁니다.

**아직 미해결입니다.** 다시 시도해 보고 배너 문구나 콘솔(`Ctrl+Shift+I`)의
`[preload]` 로그를 알려 주시면 원인을 좁힐 수 있습니다.

### 그 밖의 기계적 수정

| 대상 | 내용 |
|---|---|
| `AllFilesView.tsx` | `({ currentFiles = [] })` 무타입 → `AllFilesViewProps` 추가 (strict 모드 implicit any) |
| `AllFilesView` · `FileResultCard` · `MainView` | 쓰지 않는 `React` import 제거 (`jsx: react-jsx` + `noUnusedLocals`) |
| `src/types.ts` | `Menu`를 분리. App↔Header/Sidebar 순환 import 방지 |
| `index.html` | 제목 `Vite + React + TS` → `LocalFile AI`, 없는 `/vite.svg` 참조 제거 |
| `electron-builder.json5` | `appId: "YourAppID"` · `productName: "YourAppName"` 템플릿 기본값 교체 |
| `package.json` | `typecheck` 스크립트 추가, `build`에서 `electron-builder` 분리(`dist`로) |
| `.gitignore` | 프론트·백엔드 통합. `backend/.venv`, 실험 산출물 제외 |

`package.json`의 `name`·`version`은 **FE1의 `package-lock.json`과 맞추려고
`local-file-ai-app` / `0.0.0`으로 유지했습니다.** 바꾸면 `npm ci`가
"package.json과 package-lock.json이 맞지 않는다"로 실패합니다.

---

## 4. 검증

**전부 실제로 실행해 확인했습니다.** 정식 설치된
Node.js **v24.18.1** (`C:\Program Files\nodejs`) · npm 11.16.0 기준이고,
`node_modules`를 지우고 `npm ci`부터 다시 돌린 결과입니다.

### 통합이 실제로 동작한다는 증거

앱을 띄운 뒤 uvicorn 액세스 로그입니다. **Electron 렌더러가 스스로 백엔드를
호출했습니다** — curl로 두드린 게 아닙니다.

```
127.0.0.1 - "GET /health HTTP/1.1"        200 OK
127.0.0.1 - "GET /mock/rename HTTP/1.1"   200 OK
127.0.0.1 - "GET /mock/move HTTP/1.1"     200 OK
127.0.0.1 - "GET /mock/rename HTTP/1.1"   200 OK   ← StrictMode 이중 호출
127.0.0.1 - "GET /mock/move HTTP/1.1"     200 OK
```

`App.tsx`의 `loadOrganizeData()`가 마운트 시 FE2의 API 클라이언트로
BE2의 백엔드를 호출한 것입니다. **1주차 통합 결과물이 앱 안에서 성립합니다.**

(같은 요청이 두 번 찍히는 건 React StrictMode가 개발 모드에서 effect를
두 번 실행하기 때문입니다. 정상입니다.)

### 프론트엔드

| 항목 | 결과 |
|---|---|
| `npm ci` (node_modules 삭제 후) | **성공** — 482 패키지, 48초 |
| `npm run typecheck` (`tsc --noEmit`) | **PASS** (초기 2건 오류 → 수정) |
| `npm run lint` (`--max-warnings 0`) | **PASS** (초기 4건 오류 → 수정) |
| `npm run build` (`tsc && vite build`) | **PASS** — 40 모듈, JS 185.65 kB · **CSS 31.63 kB** |
| `npm run dev` → Electron 창 | **기동 확인** — 창 제목 `LocalFile AI`, 프로세스 4개 |
| Vite dev 서버 | `http://localhost:5173/` **HTTP 200**, `index.html` 정상 서빙 |

CSS가 31.63 kB 생성됐다는 건 **Tailwind v4가 실제로 동작한다**는 뜻입니다
(§3-5의 설정 통합이 맞았다는 확인).

> Electron 창이 떴고 렌더러가 `index.html`을 로드한 것까지 확인했습니다.
> 다만 **창 내부를 눈으로 보지는 못했습니다.** 폴더 선택 창이 실제로 뜨는지,
> 추천 목록이 그려지는지는 직접 클릭해 확인해 주세요.

### 백엔드

| 항목 | 결과 |
|---|---|
| 전체 `.py` 구문 검사 (`compileall`) | **PASS** |
| `npm run backend:install` | **성공** — venv 생성 + fastapi·uvicorn·PyMuPDF·chromadb 설치 |
| `npm run backend:dev` → uvicorn | **기동 확인** — `Application startup complete` |
| `GET /health` | **200** `{"status":"ok"}` |
| BE1 계약 자체 테스트 (`app/contracts/ai.py`) | **23건 통과** |
| 승인 없는 파일 변경 요청 차단 | **차단됨** (`ApplyRequest(approved=False)` → ValidationError) |
| `Category` 6종 · 허용 확장자 3종 | `lecture assignment report reference project exam_prep` / `pdf txt md` |

### 앱이 실제로 호출하는 경로 (전건 200)

FE가 호출하는 엔드포인트 7개가 백엔드에 모두 있고, 전부 응답했습니다.

```
GET  /mock/rename        200  count=4   최종.pdf -> 가치가게_캡스톤_최종발표_2025.pdf (conf 96)
GET  /mock/move          200  current_files=8  recommendations=3
GET  /mock/search?q=TSN  200  count=1   TSN_스케줄링_발표자료.pdf (score 87)
POST /mock/rename/apply  200  {"applied": 2, "status": "ok"}
```

`Origin: http://localhost:5173`으로 호출해 **CORS 헤더도 확인했습니다**
(`access-control-allow-origin: http://localhost:5173`). 렌더러의 `fetch`가 막히지 않습니다.

### 실제 PDF 추출 — 1주차에서 Mock이 아닌 유일한 기능

`mock/pdf/`의 TSN 논문 **5건 전부 추출 성공, 실패 0건**입니다.

```
POST /preprocess/extract-first-page   200   count=5

- (TSN)Implementation_and_Evaluation_of_a_Time-Sensitive_Net…   error 없음
  "Received 22 January 2026, accepted 31 January 2026, date of publication…"
- Ethernet_Trends_AutomobilElektronik_201712_PressArticle_KO    error 없음
  "01 차량의 Ethernet 적용사례가 증가함에 따라 발전하는 분야는 다양해진다…"
- NeSTiNg_Simulating_IEEE_Time-sensitive_Networking_TSN_in_O…   error 없음
  "NeSTiNg: Simulating IEEE Time-sensitive Networking (TSN) in OMNeT++…"
```

**한국어 PDF도 깨지지 않고 추출됩니다.** PyMuPDF 경로가 실제로 동작합니다.
MD·TXT도 별도로 확인했고, DOCX는 MVP 범위대로 정상적으로 걸러집니다.

### 아직 확인하지 못한 것

- **창 내부 동작** — 폴더 선택 창 실제 표시, 드롭 경로 인식, 추천 표 렌더링.
  프로세스와 HTTP 레벨까지만 확인했습니다.
- **BE1 실험 스크립트** — `generate_dataset.py` · `embed_dataset.py` ·
  `test_models.py`. Ollama가 필요하고 모델 내려받기에 시간이 걸려 돌리지 않았습니다.
  BE1 보고서의 수치(Recall@5 100%, exaone3.5 파일명 88.5% 등)는 **본인 보고 기준**입니다.

---

## 5. 합치는 과정에서 발견한 것

### 5-1. FE2는 BE2의 Mock API에 정확히 붙어 있었다

FE2 보고서에 Flask(`포트 5000`, `/api/search`) 예시 코드가 실려 있어 다른 서버에
붙인 것처럼 보였지만, **실제 코드는 BE2의 FastAPI Mock을 정확히 호출합니다.**
`http://127.0.0.1:8000/mock/*`, 응답 필드도 `{count, items}` 구조에 맞춰
`item.old`/`item.next`/`item.from_`/`item.to`를 읽습니다.
보고서의 Flask 코드는 초기 규격 협의용 예시였던 것으로 보입니다.

FE2의 API 클라이언트는 방어적으로 작성돼 있습니다.

```ts
currentName: item.old || item.currentName || '이름 없음',
const val = item.confidence > 1 ? item.confidence : item.confidence * 100;
```

계약이 흔들려도 화면이 죽지 않게 만든 흔적입니다. `confidence`가 `0.91`이든
`96`이든 같은 결과를 냅니다 — [§6](#6-2주차에-먼저-정할-것)의 단위 문제를
FE가 임시로 흡수하고 있는 셈입니다.

### 5-2. BE1 보고서의 테스트 건수가 실제와 다르다

보고서는 계약 자체 테스트를 **24건**이라고 적었는데 실행 결과는 **23건**입니다.
파일은 동일합니다(14,577 바이트). 결론에 영향은 없지만 수치는 맞춰야 합니다.

### 5-3. UTF-8 BOM이 추출 텍스트에 남는다

BOM이 붙은 `.txt`/`.md`를 추출하면 텍스트 맨 앞에 `U+FEFF`가 남습니다.
`normalize_pdf_text`의 NFKC 정규화는 BOM을 제거하지 않습니다.

```
preview: ﻿# 라우팅 프로토콜 비교 문서 유형: 실험 보고서 ...
         ↑ U+FEFF
```

Windows 도구(메모장, PowerShell `Out-File`)가 BOM을 붙이는 일이 흔하므로
실제 사용자 파일에서 나옵니다. 임베딩 품질에 큰 영향은 없지만
검색 하이라이트나 파일명 추천 프롬프트 앞에 보이지 않는 문자가 섞입니다.
→ `normalize_pdf_text` 첫 줄에서 `lstrip('﻿')` 한 번으로 끝나는 문제입니다.

### 5-4. 계약이 여전히 둘이다 — 2주차 최우선

`app/contracts/ai.py`(BE1)가 팀 공용 기준인데, 실제 API 응답은
`app/contracts/api.py`(BE2)를 씁니다. 같은 것을 다르게 부릅니다.

| | `ai.py` (BE1 · LLM 출력 계약) | `api.py` (BE2 · API 응답) |
|---|---|---|
| 파일명 | `recommended_filename` | `recommended_name` |
| 근거 | `reason` (1~200자) | `summary` |
| 분류 | `category: Category` (6종 Enum) | `tags: list[str]` (자유 문자열) |
| 신뢰도 | `confidence: float` 0.0~1.0 | `confidence: int` 0~100 |
| 승인 | `approved: bool` (**True 강제**) | `ids: list[str]` (승인 개념 없음) |

**1주차에는 문제가 드러나지 않습니다.** `/mock/*`이 하드코딩 값을 돌려주고
실제 파일을 건드리지 않기 때문입니다. Mock을 실제 LLM으로 바꾸는 순간
FE 화면이 깨지고, `approved` 강제도 사라집니다.

`ai.py`의 `FileRef`·`SearchQuery`·`SearchResponse`·`AnalysisInput`·
`OrganizeResponse`·`FailedFile`·`ApplyRequest`는 현재 **아무도 import하지 않습니다.**

### 5-5. 텍스트 추출이 두 곳에 있다

계획서상 PyMuPDF 추출은 **BE2 담당**입니다. 그런데 BE1의
`scripts/generate_dataset.py`가 자체 `extract_first_page()`와 `normalize_text()`를
갖고 있습니다. BE2의 `normalize_pdf_text()`가 하는 NFKC·합자·하이픈 복원을
BE1 쪽은 하지 않습니다.

같은 PDF에서 두 함수가 **다른 텍스트를 뽑습니다.** 임베딩과 LLM 입력이
서로 다른 전처리를 거치면 검색 품질과 추천 정확도가 어긋납니다.
BE1도 보고서에서 같은 지적을 남겼습니다("2주차 전에 역할 경계를 맞춰야 합니다").

→ 실험 코드가 `app.extraction.service`를 import하도록 정리. 담당은 BE2.

### 5-6. 기획안과 MVP 범위가 다르다

기획안 3장은 대상 확장자를 **PDF·DOCX·DOC·HWP·HWPX·PPT·PPTX**로 적고 있습니다.
현재 구현은 **PDF·TXT·MD 3종**입니다(`ALLOWED_EXTENSIONS`, `SUPPORTED_TEXT_EXTENSIONS`
양쪽 모두). 팀이 의식적으로 좁힌 결정으로 보이지만 기획안에 반영돼 있지 않습니다.

TXT·MD는 기획안 목록에 아예 없는데 구현에는 있고, DOCX·HWP는 반대입니다.
어느 쪽이 맞는지 정해야 합니다.

---

## 6. 2주차에 먼저 정할 것

### 차단 항목

- [ ] **계약 하나로 합치기.** `ai.py`를 API 경계까지 쓸지, 내부 가드로 둘지.
      `confidence` 단위를 `float` 0.0~1.0으로 고정 — **전원** (§5-4)
- [ ] **`approved` 플래그를 실제 엔드포인트에 강제.** 3주차에 실제 파일을 건드리기
      전에 들어가야 합니다 — **BE2**
- [ ] 확장자 범위 확정 (기획안 7종 vs 구현 3종) — **전원** (§5-6)
- [ ] **창 내부 동작 직접 확인** — 폴더 선택 창, 드롭, 추천 표 렌더링.
      프로세스·HTTP 레벨까지만 검증했습니다 — **FE1 · FE2**

### 파트별

**BE1** — RAG 프롬프트 엔지니어링 / 검색 평가셋 강화(지금 Recall@5 100%는 쉬운
평가셋 결과) / 질의 2.3초 단축 / `ValidationError` 시 1회 재시도(`exaone3.5` 채택의
전제 조건) / 확장자 자동 보정 후처리(없으면 JSON 유효율 62.5%로 하락)

**BE2** — Mock을 실제 Ollama 연동으로 교체 / ChromaDB 연동 / SQLite 뼈대 /
Watchdog 감지(자기가 만든 변경은 무시 처리 필요) / BOM 제거 (§5-3) /
추출 담당 경계 정리 (§5-5)

**FE1** — Electron 실행·종료 시 FastAPI 프로세스 동시 관리(`child_process`).
`scripts/backend.mjs`의 플랫폼 분기 로직을 그대로 쓸 수 있습니다 /
백엔드 미기동 시 UI 처리 — 지금은 콘솔 에러만 남고 화면은 빈 목록

**FE2** — 미리보기 표 컴포넌트 / 에러 모달(현재 API 실패가 `console.error` 후
빈 배열로 조용히 끝남) / `confidence` 임계값 결정 / `fileType` 유니온
(`'PDF'|'TXT'|'MD'`)을 확정된 확장자 범위에 맞추기

### 미해결 논의

| # | 항목 | 현재 | 결정 주체 |
|---|---|---|---|
| 1 | `recommended_folder` 타입 | 문자열 `"lecture/운영체제/2025-1"` | BE2 · FE2 |
| 2 | `confidence` 임계값 | 미정 | FE2, BE1 참고 |
| 3 | 실패 파일 표현 | `FailedFile` 정의만 있고 미사용 | BE2 · FE2 |
| 4 | `reason` 200자 유지 여부 | exaone이 3/30 위반 | BE1 · FE2 |
| 5 | `first_page_text` 상한 | `ai.py` 2,000자 vs 추출 API 기본 1,000자 | BE1 · BE2 |
| 6 | 지원 확장자 | 기획안 7종 vs 구현 3종 | 전원 |

---

## 부록. 출처와 검증 방법

| 확인 대상 | 위치 | 커밋 |
|---|---|---|
| BE1 + BE2 백엔드 | `localfileai/local-file-ai-backend` | `b4b60cf` |
| FE1 electron 4개 파일 | `Downloads/ts파일.zip` | — |
| FE1 스캐폴딩 | `hongham/local-file-ai-app` `feature/native-folder-dialog-and-drag-drop` | `e383bf9` |
| FE2 컴포넌트·API | `Downloads/1~3_*.zip` | — |
| FE2 아이콘 | `localfileai/local-file-ai` `public/` | `b27d45d` |

**팀원이 시험 삼아 합쳐 본 `localfileai/local-file-ai`(`b27d45d`)는 참고만 했습니다.**
아이콘 8개만 가져왔습니다. 그 저장소는 커밋 11건이 전부 07-29 하루에 BE2 단독으로
올라간 것이고, SQLite·Watchdog·Ollama 연동·실제 파일 이름 변경까지 들어 있어
**2·3주차 범위입니다.** 1주차 결과물로 쓰기에 맞지 않습니다.
기본 LLM이 `qwen2.5:7b`로 잡혀 있는 점도 문제입니다 — BE1의 실측과 ADR-0002가
모두 기각한 모델입니다(한국어 유지 85%, 40건 중 6건을 영어로 번역).

또 하나: `localfileai/localfile-ai`(`a7a5004`)에는 이 통합본에 없는 문서가 있습니다.
**ADR 2건(모노레포 결정, 모델 선정), `data-contract.md`, CI 2종, CODEOWNERS,
이슈/PR 템플릿, 계약 테스트 17건.** 특히 ADR-0002는 §5-4와 위 모델 문제의
판단 근거이므로 정본 저장소로 옮기는 편이 좋습니다.

### 실행 환경

```
Node   v24.18.1 (LTS Krypton) — C:\Program Files\nodejs
npm    11.16.0
Python 3.13.14 (backend/.venv)
OS     Windows 11 Pro
```

Node는 시스템 PATH(`HKLM\...\Environment`)에 정상 등록돼 있습니다.

> **VS Code를 재시작해야 터미널에서 `node`가 잡힙니다.** 실행 중인 VS Code는
> 설치 전 환경을 물려주므로 통합 터미널의 PATH가 갱신되지 않습니다.
> 검증할 때는 `C:\Program Files\nodejs`를 세션 PATH 앞에 붙여 우회했습니다.

> `npm ci` 중 npm 11의 allow-scripts 정책이 `electron`·`esbuild`의 postinstall을
> 건너뛴다는 경고가 나옵니다. 두 바이너리는 이미 패키지에 포함돼 있어
> 빌드·실행에 영향이 없었습니다(빌드·앱 기동 모두 확인). 문제가 생기면
> `npm approve-scripts` 로 허용하면 됩니다.

### 재현 명령

```powershell
cd local-file-ai

npm ci
npm run typecheck        # PASS
npm run lint             # PASS
npm run build            # PASS

npm run backend:install  # venv + 의존성
npm run backend:dev      # 터미널 1 — http://127.0.0.1:8000
npm run dev              # 터미널 2 — Electron 창

# 백엔드 단독 검증
cd backend
.venv\Scripts\python.exe app\contracts\ai.py    # 계약 테스트 23건
```
