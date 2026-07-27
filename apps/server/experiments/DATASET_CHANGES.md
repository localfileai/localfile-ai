# 데이터셋 생성기 변경 공지 (2026-07-26)

대상: LocalFile AI 팀 전원 (BE1 / BE2 / FE)
파일: `generate_student_dataset.py`
원본 백업: `generate_student_dataset.py.orig` (변경 전 그대로)

---

## 한 줄 요약

`category` 라벨이 **문서 내용과 무관한 무작위 값**이었습니다. 이 상태로는 분류 정확도를
측정해도 항상 무작위 수준이 나와 모델 비교·RAG 개선 효과 측정이 불가능합니다.
생성기를 고쳐 **문서에 명시된 두 신호로 category가 결정**되도록 바꿨습니다.

## 왜 고쳤나

1주차 모델 비교 실험에서 exaone3.5:7.8b와 qwen2.5:7b가 **둘 다 정확도 10.0%**로
동률이 나왔습니다. 무작위 기준선(1/8 = 12.5%)보다도 낮습니다.

원인을 추적해 보니 변경 전 생성기의 이 줄이었습니다.

```python
# generate_student_dataset.py (변경 전)
category = rng.choice(TOP_LEVEL_CATEGORIES)   # 문서 제목·내용과 완전히 독립
```

문서 제목도 `title = rng.choice(KOREAN_TITLES)`로 따로 뽑히기 때문에,
`category`와 문서 사이에 아무 관계가 없었습니다. 실측 결과입니다.

```
H(category)              = 2.9963 bit
H(category | 문서 유형)   = 2.9599 bit
정보 이득                = 0.0364 bit  (전체의 1.2%)
가능한 최고 정확도        = 17.0%   (무작위 12.5%)
```

즉 **어떤 모델을 써도 정확도가 무작위 수준일 수밖에 없는 과제**였습니다.
모델이 나빴던 게 아니라 지표가 망가져 있었습니다.

## 무엇을 바꿨나

### 1. category 결정 규칙 도입

`category`는 이제 **(문서 유형 × 수행 형태)** 로 결정됩니다. 둘 다 문서 본문에
글자로 적혀 있어서 읽으면 알 수 있는 값입니다.

```python
# generate_student_dataset.py (변경 후)
category = resolve_category(context["document_type"], context["work_mode"])
```

| 문서 유형 | 개인 수행 | 팀 수행 |
|---|---|---|
| 과제 | `assignment` | `team_project` |
| 보고서 | `essay` | `assignment` |
| 프로젝트 | `project` | `team_project` |
| 설계 문서 | `project` | `reference` |
| 실험 결과 | `practice` | `practice` |
| 조사 자료 | `research` | `research` |
| 발표 초안 | `lecture` | `lecture` |
| 논문 요약 | `reference` | `essay` |

16칸을 8개 category에 정확히 2칸씩 배정해 분포 균형을 맞췄습니다.

**설계 의도**: 한 신호만으로는 못 맞히게 했습니다.

| 아는 것 | 정확도 상한 (실측) |
|---|---|
| 아무것도 모름 (무작위) | 12.5% |
| 최빈 category만 찍기 | 15.3% |
| 문서 유형만 읽음 | 72.8% |
| 문서 유형 + 수행 형태 둘 다 읽음 | **100.0%** |

`analyze_label_signal.py`로 언제든 재검증할 수 있습니다 (실패 시 exit code 1).

> **주의 — 일부러 남겨둔 부분**
> `보고서+팀 → assignment`, `논문 요약+팀 → essay` 두 칸은 의미적으로 자명하지 않습니다.
> 프롬프트 설명만으로는 맞힐 수 없고, **유사 예시를 봐야** 알 수 있는 "조직 고유 관례"입니다.
> 이건 실수가 아니라 의도입니다. 2주차 RAG(`similar_examples`)가 실제로 효과가 있는지
> 측정하려면 예시 없이는 못 푸는 부분이 있어야 하기 때문입니다.
> 프롬프트만 쓰는 현재 방식의 현실적 상한은 약 85%입니다.

### 2. 문서 본문에 신호 추가

**10개 파일 형식 전부**에 `문서 유형`, `수행 형태`가 들어갑니다. 팀 문서에는 팀원 명단도 붙습니다.

| 형식 | 추가된 위치 |
|---|---|
| txt / md / docx / pdf / html | 머리말 메타데이터 블록 |
| py | 모듈 docstring |
| sql | 상단 주석 |
| json | `metadata.document_type`, `metadata.work_mode`, `metadata.team_members` |
| ipynb | 첫 markdown 셀 |
| csv | `document_type`, `work_mode` **컬럼** (본문이 없는 형식이라 컬럼으로 처리) |

예시 (txt/md/pdf/docx):
```
과목명: 정보보안
학기: 2025_2학기
문서 유형: 실험 결과
수행 형태: 팀 수행 (4인)
전공 분야: network
세부 주제: ...
작성자: 정다은
팀원: 정다은, 최현우, 김민준, 최유진
```

### 3. `file_metadata.csv` 컬럼 2개 추가

⚠️ **CSV를 읽는 코드가 있다면 확인이 필요합니다.**

`category` 다음에 `document_type`, `work_mode`가 삽입됐습니다.

```
index, file_name, extension, relative_path, absolute_path, category,
document_type, work_mode,          <-- 신규
subject, subtopic, semester, course, document_title, size_bytes,
created_at, modified_at, sha256, first_page_text, extraction_status
```

- **컬럼명으로 읽으면(`csv.DictReader`) 영향 없습니다.**
- 위치 인덱스로 읽는 코드는 6번 이후가 두 칸씩 밀립니다.

### 4. `dataset_summary.json`에 라벨 모드 기록

어느 방식으로 만든 데이터셋인지 파일만 보고 구분할 수 있게 했습니다.

```json
"label_mode": "content_derived",
"label_rule": "category = CATEGORY_RULES[(document_type, work_mode)]  # 문서 내용에서 결정",
"document_type_counts": { ... },
"work_mode_counts": { "팀": 515, "개인": 485 }
```

### 5. 구버전 재현용 플래그

이전 데이터셋을 다시 만들어야 할 때만 씁니다. 실행하면 경고를 출력합니다.

```powershell
python generate_student_dataset.py generate --count 1000 --output .\old --legacy-random-category
```

## 결과

동일 조건(샘플 30건, seed 42, temperature 0.1, **프롬프트 무수정**) 재실험:

| 모델 | 변경 전 | 변경 후 (관례 미제공) | 변경 후 (관례 제공) |
|---|---|---|---|
| exaone3.5:7.8b | 10.0% | 20.0% | **70.0%** |
| qwen2.5:7b | 10.0% | 20.0% | 63.3% |
| *이론적 상한* | *17.0%* | *100.0%* | *100.0%* |

세 가지가 확인됐습니다.

1. **지표가 살아났습니다.** 변경 전에는 상한 자체가 17.0%라 무엇을 해도 개선을
   측정할 수 없었습니다. 이제 상한이 100%라 개선 여지를 수치로 잡을 수 있습니다.
2. **모델 간 차이가 드러납니다.** 변경 전에는 두 모델이 10.0%로 동률이라 선정
   근거가 없었습니다. 관례를 제공하면 6.7%p 차이가 납니다.
3. **RAG로 메울 여지가 정량화됐습니다.** 관례를 알려주는 것만으로 20.0% → 70.0%,
   50%p가 오릅니다. 2주차 RAG의 목표 구간이 이 사이입니다.

모델 선정 근거와 최신 수치는 `README.md`의 "실험 결과 요약"에 있습니다.

> ⚠️ 1주차 초기에 공유한 `qwen2.5:7b` 권장은 **무효**입니다. 무작위 라벨
> 데이터셋에서 나온 판단이었습니다. 현재 권장은 `exaone3.5:7.8b`입니다.

## 각 팀에 필요한 조치

| 대상 | 조치 |
|---|---|
| **BE1** | 없음 (본인 작업) |
| **BE2** | `file_metadata.csv`를 Mock 데이터로 쓴다면 컬럼 2개 추가를 반영. `DictReader`면 조치 불필요 |
| **FE** | 없음. `schemas.py`의 API 계약은 **변경 없음** |
| **전원** | 기존에 받아간 `student_dataset/`가 있다면 폐기하고 재생성 권장 |

재생성 명령:
```powershell
python generate_student_dataset.py generate --count 1000 --output .\student_dataset --overwrite
python verify_dataset.py          # 행 수 / 상태값 / 분포 / 한글 인코딩
python analyze_label_signal.py    # 라벨 규칙 검증 (실패 시 exit 1)
```

## 바뀌지 않은 것

- `schemas.py`의 모든 스키마 (API 계약 그대로)
- `Category` Enum의 8개 값과 이름
- CLI 사용법 (`generate` / `scan` 서브커맨드, 기존 옵션 전부)
- `extraction_status`의 성공 값 `"success"`
- 기본 시드 `20260722`, 기본 파일 수 1000
- `scan` 서브커맨드가 만드는 CSV 형식
