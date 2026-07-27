# 데이터 계약

[`apps/server/app/contracts/schemas.py`](../apps/server/app/contracts/schemas.py)가
**단일 기준**입니다. BE1(LLM 출력), BE2(API 응답), FE2(화면 렌더링)가 모두 이걸 봅니다.

한 명이 바꾸면 나머지 셋이 깨집니다. 그래서
[계약 변경 제안 이슈](../.github/ISSUE_TEMPLATE/contract.yml)로 먼저 합의합니다.

## 현재 스키마

```
Category(StrEnum)     project · assignment · essay · research
                      lecture · reference · practice · team_project

SimilarExample        first_page_text, category, relative_path, file_name
  (RAG 검색 결과)

FileAnalysisInput     file_name, extension,
  (LLM 입력)          first_page_text        ≤ 1,500자
                      similar_examples       ≤ 3건, 기본 []

FileOrganizeOutput    category               Category
  (LLM 출력 계약)      recommended_folder     ≥ 1자  "assignment/database/2025_1학기"
                      recommended_filename   ≥ 1자
                      confidence             0.0 ~ 1.0
                      reason                 1 ~ 200자

FileRecommendation    original_path, original_name, result: FileOrganizeOutput

OrganizeResponse      total_files, success_count,
  (API 응답 계약)      failed_files: list[str],
                      recommendations: list[FileRecommendation]
```

모든 모델이 `extra="forbid"`입니다. LLM이 계약에 없는 필드를 덧붙이면
검증 단계에서 걸러집니다.

`Category`는 `StrEnum`이라 f-string에 그대로 넣으면 값이 나옵니다
(`f"{Category.ASSIGNMENT}"` → `"assignment"`). 프롬프트 조립 시 `.value`가 필요 없습니다.

검증 동작은 [`tests/test_contracts.py`](../apps/server/tests/test_contracts.py)의
17개 테스트로 고정돼 있습니다. 계약을 바꾸면 여기가 먼저 빨개집니다.

## 검증과 재시도

`exaone3.5:7.8b`는 90건 중 5건(5.6%)에서 형식 제약을 어겼습니다.
파싱 실패가 아니라 전부 형식 문제였습니다.

| 위반 | 건수 |
|---|---|
| `reason` 200자 초과 (`string_too_long`) | 3 |
| `category`에 Enum 밖 값 (`enum`) | 2 |

**`ValidationError` 시 1회 재시도는 필수입니다.** 재시도 프롬프트에는
위반한 제약을 명시하세요 (예: "reason은 200자 이내로 작성하세요").
이 처리 없이 exaone을 쓰는 것은 [ADR-0002](decisions/0002-model-selection.md)의
전제를 어기는 것입니다.

재시도 후에도 실패하면 해당 파일을 `failed_files`에 넣고 넘어갑니다. 앱은 멈추지 않습니다.

## TypeScript 타입

프론트엔드 타입은 위 Pydantic 모델에서 **생성**합니다.

```bash
python scripts/generate_contracts.py     # → packages/contracts/index.ts
```

> 생성 스크립트는 2주차에 계약이 안정된 뒤 붙입니다.
> 그전까지는 FE가 임시 타입을 쓰되, `packages/contracts/`가 아닌
> 각자 파일에 두고 TODO를 남기세요.

**손으로 인터페이스를 다시 쓰지 마세요.** 백엔드와 프론트엔드가 조용히
갈라지는 가장 흔한 경로입니다. 컴파일은 통과하는데 런타임에 `undefined`가 나옵니다.

## ⚠️ 계약이 둘로 갈라져 있습니다

1주차에 BE1과 BE2가 각자 계약을 만들었고, 둘이 같은 것을 다르게 부르고 있습니다.
**2주차 최우선 과제입니다.**

| | `contracts/schemas.py` (BE1) | `contracts/api.py` (BE2) |
|---|---|---|
| 용도 | LLM 출력 검증 | FE와 맞춘 Mock 응답 |
| 추천 결과 | `FileOrganizeOutput` | `MockAnalyzeResponse` |
| 폴더 | `recommended_folder: str` | `recommended_folder: str` |
| 파일명 | `recommended_filename: str` | `recommended_name: str` ← 이름 다름 |
| 신뢰도 | `confidence: float` 0.0~1.0 | `confidence: float` 0.0~1.0, 일부 `int` 0~100 ← 단위 다름 |
| 근거 | `reason: str` ≤200자 | `summary: str` ← 의미 다름 |
| 카테고리 | `category: Category` (8종 Enum) | `tags: list[str]` ← 자유 문자열 |

`confidence`가 특히 위험합니다. `MockAnalyzeResponse`는 `0.91`인데
`RenameRecommendation`·`MoveRecommendation`은 `96`입니다. FE가 어느 쪽 기준으로
게이지를 그리느냐에 따라 조용히 100배 틀립니다.

Mock을 실제 LLM으로 교체하는 순간 FE 화면이 깨집니다. 지금은 Mock이 하드코딩된
값을 돌려주고 있어서 드러나지 않을 뿐입니다.

→ 2주차 시작 전에 **계약 변경 제안 이슈**로 하나로 합칠 것.

## 미해결 논의

2주차 구현 전에 정해야 합니다.

### 1. `recommended_folder` — 문자열 vs 배열

현재는 `"assignment/database/2025_1학기"` 문자열입니다.

배열(`list[str]`)이 나은 경우:
- FE가 경로를 세그먼트 단위로 렌더링하거나, 사용자가 중간 단계만 수정하게 할 때
- 경로 구분자(`/` vs `\`) 처리 부담이 줄어듭니다

→ **BE2·FE2 결정 필요**

### 2. `confidence` 임계값

몇 점 미만을 "확인 필요"로 표시할지. UI 표현과 함께 정해야 합니다.

→ **FE2 결정, BE1 참고 의견**

### 3. 실패 파일 표현

현재 `failed_files: list[str]` — 경로만 있습니다.
사용자에게 "왜 실패했는지"를 보여주려면 `list[FailedFile]`로 승격해야 합니다.

```python
class FailedFile(BaseModel):
    path: str
    reason: Literal["extraction_failed", "validation_failed", "file_locked", "permission_denied"]
    detail: str | None = None
```

→ **BE2·FE2 결정 필요**

### 4. `reason` 200자 제한 유지 여부

exaone이 3/30 위반했습니다. 유지한다면 프롬프트에 글자 수를 명시하고
재시도 로직을 반드시 넣어야 합니다. 늘린다면 UI에서 어떻게 줄일지 정해야 합니다.

→ **BE1·FE2 결정 필요**

### 5. `first_page_text` 1,500자 절단 기준

속도를 위해 자르고 있는데, 표지만 있는 PDF는 본문 신호가 하나도 안 들어옵니다.
분량 기준이 아니라 "의미 있는 첫 문단" 기준이 나을 수 있습니다.

→ **BE1·BE2 재검토**
