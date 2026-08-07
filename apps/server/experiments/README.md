# 실험

모델·임베딩·프롬프트 비교 실험 코드입니다. (BE1)

**프로덕션 코드가 아닙니다.** `app/`에서 여기를 import 하지 마세요.
린트 기준도 느슨합니다 (`pyproject.toml`의 per-file-ignores).
탐색용 코드에 프로덕션과 같은 잣대를 들이대면 실험을 안 하게 됩니다.

## 규칙

**결론은 여기 남기지 않습니다.** 실험 결과로 무언가를 정했다면
[docs/decisions/](../../../docs/decisions/)에 ADR로 쓰세요.
스크립트만 있으면 6개월 뒤에 아무도 무슨 결론이었는지 모릅니다.

**재현 가능해야 합니다.** seed, 표본 수, 모델 버전, 실행 명령을 ADR에 적으세요.

**한 번에 하나씩 돌립니다.** 동시에 돌리면 GPU 경합으로 응답 시간이 2배 이상
왜곡됩니다. 정확도는 영향받지 않지만 시간 지표가 못 쓰게 됩니다. 실제로 겪었습니다.

## 산출물은 커밋하지 않습니다

`.gitignore`에 있습니다.

```
student_dataset/     생성된 파일 1,000개
*.csv                건별 실험 결과
results/
```

수백 MB를 저장소에 넣을 이유가 없습니다. 필요하면 명령어로 다시 만듭니다.

## 파일

| 파일 | 역할 |
|---|---|
| `generate_student_dataset.py` | 합성 데이터셋 생성기 |
| `verify_dataset.py` | 행 수 · 상태값 · 분포 쏠림 · 한글 인코딩 검증 |
| `analyze_label_signal.py` | **라벨 규칙 검증.** category가 문서 내용에서 결정되는지 (실패 시 exit 1) |
| `DATASET_CHANGES.md` | 2026-07-26 라벨 규칙 수정 공지 |
| `test_models.py` | 모델 비교 — category 분류 |
| `test_models_subject.py` | 보조 실험 — subject 10분류 (본문 근거 충실도) |
| `summarize_runs.py` | 결과 CSV들을 모델별 지표·오답 패턴으로 요약 |
| `embed_dataset.py` | ChromaDB 임베딩 및 한국어 검색 검증 |

`schemas.py`는 여기 없습니다. 팀 공용 계약이므로 `app/contracts/schemas.py`로 올라갔고,
자체 테스트는 `tests/test_contracts.py`의 pytest로 옮겼습니다.
실험 코드에서는 `from app.contracts import ...`로 가져다 쓰세요.

## 순서

```powershell
# 1. 데이터셋 생성 및 검증
python generate_student_dataset.py generate --count 1000 --output .\student_dataset --overwrite
python verify_dataset.py
python analyze_label_signal.py          # 여기서 막히면 아래 실험은 전부 무의미합니다

# 2. 모델 비교 (Ollama 서버 필요)
ollama pull exaone3.5:7.8b
ollama pull qwen2.5:7b
python test_models.py --sample 30 --seed 42
python test_models.py --sample 30 --seed 42 --explain-rule --output model_test_results_with_rule.csv
python test_models_subject.py --sample 30 --seed 42
python summarize_runs.py

# 3. 임베딩 및 검색
python embed_dataset.py --limit 100
```

`analyze_label_signal.py`를 먼저 돌리세요. 라벨이 입력과 무관하면
그 위에서 하는 모든 모델 비교가 무효입니다. 1주차에 실제로 겪었습니다
([week-01.md](../../../docs/weekly/week-01.md), [ADR-0002](../../../docs/decisions/0002-model-selection.md)).
