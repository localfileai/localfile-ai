# 제3자 라이선스 고지

LocalFile AI는 다른 사람들이 만든 소프트웨어와 AI 모델 위에서 동작합니다.
그 구성 요소들에는 각자의 라이선스가 적용되며, 이 저장소의
[LICENSE](LICENSE)가 그것을 대체하지 않습니다.

MIT·Apache-2.0·BSD 계열은 **배포물에 저작권 고지를 포함할 것**을 요구합니다.
`Setup.exe`를 배포하는 이상 이 문서가 그 고지에 해당합니다.

---

## ✅ 해결됨 — PyMuPDF(AGPL-3.0) → PDFium(BSD/Apache)

한때 PDF 처리에 PyMuPDF를 썼습니다. 그런데 설치된 패키지가 스스로 이렇게
밝힙니다.

```
PyMuPDF  1.28.0  Dual Licensed - GNU AFFERO GPL 3.0 or Artifex commercial
```

AGPL-3.0은 **결합 저작물을 배포(convey)하면 그 전체를 AGPL-3.0으로 공개하고
대응 소스를 제공할 것**을 요구하며, 수령자에게 추가 제한을 붙이는 것을
금지합니다(§10). 우리는 `Setup.exe` 안에 PyInstaller로 묶은 `server.exe`를
넣어 배포하므로, **저장소 라이선스가 MIT였을 때도 이미 충돌하고 있었습니다.**
사용 제한 라이선스로 바꾸면서 발생한 문제가 아니라 원래 있던 문제였습니다.

**[pypdfium2](https://github.com/pypdfium2-team/pypdfium2)로 교체해서
해결했습니다.** Google이 Chromium에서 쓰는 PDFium의 파이썬 바인딩이고,
BSD-3-Clause / Apache-2.0 중 선택해 쓸 수 있습니다. 텍스트 추출과 페이지
렌더링을 모두 지원해 두 용도를 한 번에 대체합니다.

### 라이선스만 보고 갈아타지 않았습니다

저장소의 PDF 385건으로 두 엔진의 첫 페이지 추출 결과를 비교했습니다.

| 항목 | 결과 |
|---|---|
| 비교 대상 | 385건 |
| 완전히 같음 | **380건 (98.7%)** |
| 99% 이상 같음 | 382건 (99.2%) |
| **한글 글자 수** | MuPDF 361 / PDFium 361 — **100% 일치** |
| 한쪽만 텍스트가 나온 경우 | **0건** |

차이가 난 5건은 전부 영문 논문이었고 원인은 리거처였습니다
(`trafﬁc` → `traffic`). PDFium이 ASCII로 정규화하는 쪽이라 **검색·파일명
생성에는 오히려 낫습니다.** 줄바꿈이 CRLF로 나오는 차이는 추출 어댑터에서
LF로 맞춰 이전 동작을 그대로 유지합니다.

### PNG 인코딩을 직접 하는 이유

PDFium은 픽셀 바이트만 돌려주고 PNG는 만들어 주지 않습니다. Pillow를 쓰면
한 줄이지만 설치본에 수 MB짜리 이미지 라이브러리가 통째로 들어갑니다.
필요한 것이 "RGB 바이트 → PNG" 하나뿐이라 `app/core/png.py`에 표준 라이브러리
(`zlib`·`struct`)만으로 직접 썼습니다. 규격 준수는 `tests/test_png.py`에서
CRC 검증과 Pillow 왕복 읽기로 확인합니다.

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
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | PDF 텍스트 추출 · 미리보기 렌더링 | BSD-3-Clause 또는 Apache-2.0 |
| └ [PDFium](https://pdfium.googlesource.com/pdfium/) | 위 패키지에 포함된 렌더링 엔진 | BSD-3-Clause |

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
  print(m.metadata('pypdfium2').get('License'))"

# Node
npx license-checker --summary
```

관련 문서: [ADR-0004 라이선스와 유료화](docs/decisions/0004-license-and-commercialization.md)
