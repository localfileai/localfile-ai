# 제3자 라이선스 고지

LocalFile AI는 다른 사람들이 만든 소프트웨어와 AI 모델 위에서 동작합니다.
그 구성 요소들에는 각자의 라이선스가 적용되며, 이 저장소의
[LICENSE](LICENSE)가 그것을 대체하지 않습니다.

MIT·Apache-2.0·BSD 계열은 **배포물에 저작권 고지를 포함할 것**을 요구합니다.
설치본(`Setup.exe`)을 배포하기 시작하면 이 문서가 그 고지에 해당합니다.

---

## ⚠️ 설치본 배포 전에 정리해야 할 것 — PyMuPDF (AGPL-3.0)

PDF 텍스트 추출에 쓰는 **PyMuPDF는 AGPL-3.0과 Artifex 상용 라이선스의
이중 라이선스**입니다. 설치된 패키지가 스스로 그렇게 밝힙니다.

```
PyMuPDF  1.28.0  Dual Licensed - GNU AFFERO GPL 3.0 or Artifex commercial
```

AGPL-3.0은 **결합 저작물을 배포(convey)하면 그 전체를 AGPL-3.0으로 공개하고
대응 소스를 제공할 것**을 요구하며, 수령자에게 추가 제한을 붙이는 것을
금지합니다(§10). 즉 PyMuPDF를 넣은 채로 설치본을 배포하면, 이 저장소의
사용 제한 라이선스("재배포·수정 금지")와 정면으로 충돌합니다.

**지금 당장 위반은 아닙니다.** AGPL 의무는 *배포*에서 발생하는데, `main`은
아직 데스크톱 설치본을 만들지 않습니다. 다만 5주차에 `electron-builder`로
`Setup.exe`를 만들기 시작하면 그 순간부터 문제가 됩니다.

### 해결책 — PDFium으로 교체

작업 브랜치에서 **[pypdfium2](https://github.com/pypdfium2-team/pypdfium2)로
교체해 검증을 마쳤습니다.** Google이 Chromium에서 쓰는 PDF 엔진의 파이썬
바인딩이고, BSD-3-Clause / Apache-2.0 중 선택해 쓸 수 있습니다.

`pypdf`(BSD)도 후보였지만 **페이지 렌더링을 못 합니다.** 미리보기 썸네일까지
PyMuPDF를 쓰고 있어서, 추출과 렌더링을 모두 지원하는 PDFium이 맞습니다.

라이선스만 보고 갈아타지 않았습니다. PDF 385건으로 두 엔진의 첫 페이지
추출을 비교했습니다.

| 항목 | 결과 |
|---|---|
| 완전히 같음 | **380건 / 385건 (98.7%)** |
| 99% 이상 같음 | 382건 (99.2%) |
| **한글 글자 수** | MuPDF 361 / PDFium 361 — **100% 일치** |
| 한쪽만 텍스트가 나온 경우 | **0건** |

차이가 난 5건은 전부 영문 논문의 리거처였고(`trafﬁc` → `traffic`), PDFium이
ASCII로 정규화하는 쪽이라 검색·파일명 생성에는 오히려 낫습니다.

**이 교체는 별도 PR로 올라옵니다.** 이 PR은 라이선스 문서만 다룹니다.

---

## AI 모델

앱이 실행 중에 Ollama를 통해 내려받습니다. 저장소나 설치본에 포함되지 않습니다.

| 모델 | 용도 | 라이선스 | 상업 이용 |
|---|---|---|---|
| [`exaone3.5:7.8b`](https://github.com/LG-AI-EXAONE/EXAONE-3.5) | 정리 추천 ([ADR-0002](docs/decisions/0002-model-selection.md)) | EXAONE AI Model License 1.1 — **NC** | ❌ |
| [`qwen2.5:7b`](https://github.com/QwenLM/Qwen2.5) | fallback (ADR-0002) | Apache-2.0 | ✅ |
| 임베딩 모델 | 검색·분류 | 모델 확정 시 이 표에 추가할 것 | — |

EXAONE은 연구·비상업 목적으로만 사용할 수 있습니다. 상업적 이용은
LG AI Research(`contact_us@lgresearch.ai`)와 별도 계약이 필요합니다.
**이 프로젝트는 비상업 프로젝트이므로 현재 구성에 문제가 없습니다.**
유료화를 검토하게 되면 [ADR-0004](docs/decisions/0004-license.md) §4를 보세요.

---

## 런타임

| 구성 요소 | 용도 | 라이선스 |
|---|---|---|
| [Ollama](https://github.com/ollama/ollama) | 모델 실행기 (사용자 PC에 별도 설치) | MIT |
| [Electron](https://github.com/electron/electron) | 데스크톱 셸 (`apps/desktop`, 예정) | MIT |
| [Chromium](https://www.chromium.org/) | Electron 렌더러 | BSD-3-Clause 외 ([전문](https://chromium.googlesource.com/chromium/src/+/main/LICENSE)) |

---

## 백엔드 (`apps/server/pyproject.toml`)

| 패키지 | 용도 | 라이선스 |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | HTTP API | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI 서버 | BSD-3-Clause |
| [Pydantic](https://github.com/pydantic/pydantic) · [pydantic-settings](https://github.com/pydantic/pydantic-settings) | 검증·계약·설정 | MIT |
| [ChromaDB](https://github.com/chroma-core/chroma) | 벡터 저장·검색 | Apache-2.0 |
| [Requests](https://github.com/psf/requests) | Ollama HTTP 호출 | Apache-2.0 |
| [watchdog](https://github.com/gorakhargosh/watchdog) | 파일 변경 감시 | Apache-2.0 |
| **[PyMuPDF](https://github.com/pymupdf/PyMuPDF)** | **PDF 텍스트 추출** | **AGPL-3.0 / Artifex 상용 — 위 경고 참조** |

### 개발·테스트 전용 (배포물에 들어가지 않음)

| 패키지 | 라이선스 |
|---|---|
| [pytest](https://github.com/pytest-dev/pytest) | MIT |
| [httpx2](https://github.com/encode/httpx) | BSD-3-Clause |
| [Ruff](https://github.com/astral-sh/ruff) | MIT |
| [Hatchling](https://github.com/pypa/hatch) | MIT |

---

## 빌드 도구

| 도구 | 라이선스 | 비고 |
|---|---|---|
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0 + 배포 예외 | 예외 조항이 **독점 앱을 묶어 배포하는 것을 허용**합니다. 문제 없습니다 |
| [electron-builder](https://github.com/electron-userland/electron-builder) | MIT | |

---

## 갱신 방법

의존성을 추가·변경하면 이 문서도 함께 고쳐야 합니다.
설치된 패키지의 라이선스는 이렇게 확인합니다.

```bash
# Python
python -c "import importlib.metadata as m; print(m.metadata('pymupdf').get('License'))"

# Node
npx license-checker --summary
```

관련 문서: [ADR-0004 라이선스](docs/decisions/0004-license.md)
