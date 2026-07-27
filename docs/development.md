# 개발 환경

## 준비물

| | 버전 | 확인 |
|---|---|---|
| Node.js | 22 LTS | `node -v` |
| Python | 3.14 | `python --version` |
| Ollama | 0.32+ | `ollama --version` |
| Git | 2.40+ | `git --version` |

Windows는 PowerShell 기준으로 적었습니다. macOS·Linux는 활성화 명령만 다릅니다.

## 첫 설정

```powershell
git clone https://github.com/localfileai/localfile-ai.git
cd localfile-ai

# 모델 (합쳐서 약 6GB. 시간이 걸립니다)
ollama pull exaone3.5:7.8b
ollama pull bge-m3

# 백엔드
cd apps\server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[files,ai,dev]"

# 프론트엔드
cd ..\desktop
npm ci
```

### 자주 걸리는 것

**`.\.venv\Scripts\Activate.ps1` 실행 정책 오류**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`pip.exe` 가 차단됨**

일부 PC에서 Smart App Control이 `pip.exe` 직접 실행을 막습니다.
항상 `python -m pip` 형태로 쓰세요.

**Ollama 서버가 안 떠 있음**

```powershell
ollama serve      # 별도 터미널에서
curl http://localhost:11434/api/tags
```

## 실행

```powershell
cd apps\desktop
npm run dev          # Electron + FastAPI 동시 기동
```

서버만:

```powershell
cd apps\server
uvicorn app.main:app --reload --port 8000
```

- API 문서 http://localhost:8000/docs
- 헬스체크 http://localhost:8000/health

## 검사

PR을 올리기 전에 돌리세요. CI에서 도는 것과 같습니다.

```powershell
# 서버
cd apps\server
ruff check .
ruff format --check .      # 고치려면 ruff format .
pytest -q

# 데스크톱
cd apps\desktop
npm run lint
npm run typecheck
npm run build
```

### 테스트 마커

Ollama나 ChromaDB 실물이 필요한 테스트는 CI 러너에서 돌 수 없습니다.

```python
@pytest.mark.integration
def test_ollama_returns_valid_json():
    ...
```

```powershell
pytest -q                        # 전부 (로컬)
pytest -q -m "not integration"   # CI와 동일
pytest -q -m integration         # 무거운 것만
```

## 환경 변수

`apps/server/.env` (커밋 금지, `.env.example`을 복사해서 만드세요)

```ini
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=exaone3.5:7.8b
OLLAMA_FALLBACK_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3

CHROMA_PATH=./.data/chroma
SQLITE_PATH=./.data/localfile.db

# ChromaDB는 기본적으로 익명 사용 통계를 전송합니다.
# "문서가 PC를 떠나지 않는다"가 이 제품의 전제이므로 반드시 끕니다.
ANONYMIZED_TELEMETRY=False
```

## 실험 코드

BE1의 모델·임베딩 실험은 `apps/server/experiments/`에 있습니다.
프로덕션 코드와 린트 기준이 다릅니다 (탐색용이므로 느슨하게).

```powershell
cd apps\server\experiments
python analyze_label_signal.py          # 라벨 규칙 검증. 실패 시 exit 1
python test_models.py --sample 30 --seed 42
```

**실험은 한 번에 하나씩 돌립니다.** 동시에 돌리면 GPU 경합으로 응답 시간이
2배 이상 왜곡됩니다. 정확도는 영향받지 않지만 시간 지표가 못 쓰게 됩니다.

생성된 데이터셋과 결과 CSV는 `.gitignore`에 있습니다.
결론은 [ADR](decisions/)에 남기고, 재현 명령을 함께 적으세요.

## 디렉터리와 담당

| 경로 | 담당 |
|---|---|
| `apps/desktop/electron/` | FE1 |
| `apps/desktop/src/` | FE2 |
| `apps/server/app/api` `extraction` `watcher` `fileops` `db` | BE2 |
| `apps/server/app/rag` `llm` + `experiments/` | BE1 |
| `apps/server/app/contracts/` `packages/contracts/` | 전원 합의 |

[CODEOWNERS](../.github/CODEOWNERS)가 리뷰어를 자동 지정합니다.
남의 디렉터리를 고쳐야 하면 먼저 이슈로 이야기하세요.
