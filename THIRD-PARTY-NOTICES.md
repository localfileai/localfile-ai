# 제3자 라이선스 고지

LocalFile AI는 다른 사람들이 만든 소프트웨어와 AI 모델 위에서 동작합니다.
그 구성 요소들에는 각자의 라이선스가 적용되며, 이 저장소의
[LICENSE](LICENSE)가 그것을 대체하지 않습니다.

MIT·Apache-2.0·BSD 계열은 **배포물에 저작권 고지를 포함할 것**을 요구합니다.
`Setup.exe`를 배포하는 이상 이 문서가 그 고지에 해당합니다.

---

## ⚠️ 먼저 확인해야 할 것 — PyMuPDF (AGPL-3.0)

**PDF 텍스트 추출에 쓰는 PyMuPDF는 AGPL-3.0과 Artifex 상용 라이선스의
이중 라이선스입니다.** 설치된 패키지가 스스로 그렇게 밝힙니다.

```
PyMuPDF  1.28.0  Dual Licensed - GNU AFFERO GPL 3.0 or Artifex commercial
```

AGPL-3.0은 **결합 저작물을 배포(convey)하면 그 전체를 AGPL-3.0으로 공개하고
대응 소스를 제공할 것**을 요구하며, 수령자에게 추가 제한을 붙이는 것을 금지합니다
(AGPL-3.0 §10).

우리는 `Setup.exe` 안에 PyInstaller로 묶은 `server.exe`를 넣어 배포하고,
거기에 PyMuPDF가 들어갑니다. 즉 **지금 배포 방식은 저장소 라이선스가
MIT였을 때도, 사용 제한 라이선스로 바꾼 뒤에도 AGPL-3.0과 충돌합니다.**
(MIT는 AGPL 코드를 MIT로 재라이선스할 수 없어서, 사용 제한 라이선스는
"재배포·수정 금지"가 §10에 걸려서입니다.)

### 선택지

| 안 | 내용 | 평가 |
|---|---|---|
| **A. PyMuPDF를 교체** | `pypdf`(BSD-3-Clause) 또는 `pdfminer.six`(MIT)로 바꾼다 | ★★★ **권장.** 충돌이 사라지고 라이선스가 깔끔해진다 |
| B. 배포물을 AGPL-3.0으로 | `Setup.exe`와 소스 전체를 AGPL-3.0으로 공개 | 사용 제한 목적과 정면으로 충돌 |
| C. 설치본 배포 중단 | 소스만 공개. AGPL 의무는 "배포"에서 발생한다 | 설치본을 받아 쓰게 하려던 방향과 어긋난다 |
| D. Artifex 상용 라이선스 | 유료 (연 단위 계약) | 학생 프로젝트 규모에서 검토 대상 아님 |

**A를 권합니다.** PyMuPDF는 `requirements.txt` 기준 "PDF 첫 페이지" 텍스트
추출에만 쓰이고, `pypdf`로 대체 가능한 범위입니다. 다만 추출 품질이 바뀌므로
3주차에 쓴 것과 같은 방식으로 한국어 PDF 추출 결과를 비교한 뒤 교체해야 합니다.

**이 항목이 정리되기 전까지는 `Setup.exe`를 공개 배포하지 않는 편이 안전합니다.**
추출 담당(BE2)과 상의가 필요한 사안입니다.

---

## AI 모델

앱이 실행 중에 Ollama를 통해 내려받습니다. 저장소나 설치본에 포함되지 않습니다.

| 모델 | 용도 | 라이선스 | 상업 이용 |
|---|---|---|---|
| [`qwen3-embedding:0.6b`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 검색·분류 | Apache-2.0 | ✅ |
| [`nomic-embed-text`](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | 예비 검색 엔진 | Apache-2.0 | ✅ |
| [`exaone3.5:2.4b`](https://github.com/LG-AI-EXAONE/EXAONE-3.5) | 파일명 추천 (경량) | EXAONE AI Model License 1.1 — **NC** | ❌ |
| [`exaone3.5:7.8b`](https://github.com/LG-AI-EXAONE/EXAONE-3.5) | 파일명 추천 (표준) | EXAONE AI Model License 1.1 — **NC** | ❌ |

EXAONE은 연구·비상업 목적으로만 사용할 수 있습니다. 상업적 이용은
LG AI Research(`contact_us@lgresearch.ai`)와 별도 계약이 필요합니다.
이 프로젝트는 비상업 프로젝트이므로 현재 구성에 문제가 없습니다.

---

## 런타임

| 구성 요소 | 용도 | 라이선스 |
|---|---|---|
| [Ollama](https://github.com/ollama/ollama) | 모델 실행기 (사용자 PC에 별도 설치) | MIT |
| [Electron](https://github.com/electron/electron) | 데스크톱 셸 | MIT |
| [Node.js](https://github.com/nodejs/node) | Electron 런타임 | MIT |
| [Chromium](https://www.chromium.org/) | Electron 렌더러 | BSD-3-Clause 외 ([전문](https://chromium.googlesource.com/chromium/src/+/main/LICENSE)) |

---

## 프런트엔드

| 패키지 | 라이선스 |
|---|---|
| [React](https://github.com/facebook/react) · [React DOM](https://github.com/facebook/react) | MIT |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | MIT |
| [Vite](https://github.com/vitejs/vite) | MIT |
| [TypeScript](https://github.com/microsoft/TypeScript) | Apache-2.0 |
| [electron-builder](https://github.com/electron-userland/electron-builder) | MIT |
| [ESLint](https://github.com/eslint/eslint) | MIT |
| [vite-plugin-electron](https://github.com/electron-vite/vite-plugin-electron) | MIT |

---

## 백엔드

| 패키지 | 용도 | 라이선스 |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | HTTP API | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI 서버 | BSD-3-Clause |
| [Pydantic](https://github.com/pydantic/pydantic) | 검증·계약 | MIT |
| [ChromaDB](https://github.com/chroma-core/chroma) | 벡터 저장·검색 | Apache-2.0 |
| [Requests](https://github.com/psf/requests) | Ollama HTTP 호출 | Apache-2.0 |
| [httpx](https://github.com/encode/httpx) | 테스트 클라이언트 | BSD-3-Clause |
| [olefile](https://github.com/decalage2/olefile) | 구형 HWP 파싱 | BSD-2-Clause |
| [ReportLab](https://github.com/MrBitBucketSteveHolden/reportlab) | 실험용 데이터셋 PDF 생성 | BSD-3-Clause |
| [pytest](https://github.com/pytest-dev/pytest) | 테스트 | MIT |
| [eval_type_backport](https://github.com/alexmojaki/eval_type_backport) | 타입 힌트 호환 | MIT |
| **[PyMuPDF](https://github.com/pymupdf/PyMuPDF)** | **PDF 텍스트 추출** | **AGPL-3.0 / Artifex 상용 — 위 경고 참조** |

---

## 빌드 도구

| 도구 | 라이선스 | 비고 |
|---|---|---|
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0 + 배포 예외 | 예외 조항이 **독점 앱을 묶어 배포하는 것을 허용**합니다. 문제 없습니다 |

---

## 갱신 방법

의존성을 추가·변경하면 이 문서도 함께 고쳐야 합니다.
설치된 패키지의 라이선스는 이렇게 확인합니다.

```bash
# Python
python -c "import importlib.metadata as m; \
  print(m.metadata('PyMuPDF').get('License'))"

# Node
npx license-checker --summary
```

관련 문서: [ADR-0004 라이선스와 유료화](docs/decisions/0004-license-and-commercialization.md)
