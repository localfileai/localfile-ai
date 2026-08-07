// 백엔드 venv 생성 / 서버 실행 스크립트.
//
// npm 스크립트에 셸 문법을 쓰면 Windows에서 실행되지 않습니다.
// (`env -u`, `if [ -x ... ]`, `python3`, `.venv/bin/python`은 모두 POSIX 전용)
// 이 프로젝트의 타깃은 Windows이므로 플랫폼 분기를 Node로 옮겼습니다.
//
//   node scripts/backend.mjs install   -> backend/.venv 생성 + requirements 설치
//   node scripts/backend.mjs dev       -> uvicorn 개발 서버 (127.0.0.1:8000)
//   node scripts/backend.mjs dataset   -> 정답 데이터셋 1,000쌍 생성 (BE1)
//   node scripts/backend.mjs index     -> ChromaDB 색인 (Ollama 필요)
//   node scripts/backend.mjs test      -> 백엔드 단위 테스트 (Ollama 불필요)
//   node scripts/backend.mjs build-exe -> PyInstaller로 server.exe 빌드 (Windows 권장)

import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const BACKEND = path.join(ROOT, 'backend')
const IS_WINDOWS = process.platform === 'win32'

/** venv 안의 python 실행 파일. Windows는 Scripts\, 그 외는 bin/ 이다. */
function venvPython() {
  return IS_WINDOWS
    ? path.join(BACKEND, '.venv', 'Scripts', 'python.exe')
    : path.join(BACKEND, '.venv', 'bin', 'python')
}

/**
 * 시스템 python 후보. 앞에서부터 실제로 실행되는 것을 쓴다.
 *
 * Windows는 `python`이 관례지만 Python.org 설치본만 있고 PATH에 없는 경우
 * `py` 런처로만 잡힙니다. macOS/Linux는 `python`이 2.x일 수 있어 `python3`이 먼저입니다.
 */
const SYSTEM_PYTHON_CANDIDATES = IS_WINDOWS
  ? [{ cmd: 'python', prefix: [] }, { cmd: 'py', prefix: ['-3'] }]
  : [{ cmd: 'python3', prefix: [] }, { cmd: 'python', prefix: [] }]

/**
 * 명령을 실행한다. `shell` 옵션은 쓰지 않는다 —
 * 인자 배열과 함께 쓰면 인자가 이스케이프 없이 이어붙어 주입 위험이 있고
 * Node가 DEP0190 경고를 낸다.
 */
function run(command, args) {
  console.log(`> ${command} ${args.join(' ')}`)
  const result = spawnSync(command, args, { cwd: BACKEND, stdio: 'inherit' })

  if (result.error) return { ok: false, notFound: result.error.code === 'ENOENT' }
  return { ok: result.status === 0, status: result.status }
}

/** 후보를 순서대로 시도해 처음 실행된 것의 결과를 돌려준다. */
function runSystemPython(args) {
  for (const { cmd, prefix } of SYSTEM_PYTHON_CANDIDATES) {
    const result = run(cmd, [...prefix, ...args])
    if (!result.notFound) return result
    console.log(`  (${cmd} 없음 — 다음 후보 시도)`)
  }

  console.error('\n[에러] Python 3을 찾을 수 없습니다.')
  console.error(`       시도한 명령: ${SYSTEM_PYTHON_CANDIDATES.map((c) => c.cmd).join(', ')}`)
  console.error('       https://www.python.org/downloads/ 에서 설치하고 PATH에 추가하세요.')
  process.exit(1)
}

function mustSucceed(result) {
  if (!result.ok) process.exit(result.status ?? 1)
}

const task = process.argv[2]

if (task === 'install') {
  mustSucceed(runSystemPython(['-m', 'venv', '.venv']))

  // pip.exe를 직접 부르면 Windows Smart App Control에 막히는 사례가 있어 -m pip를 쓴다.
  mustSucceed(run(venvPython(), ['-m', 'pip', 'install', '--upgrade', 'pip']))
  mustSucceed(run(venvPython(), ['-m', 'pip', 'install', '-r', 'requirements.txt']))

  console.log('\n백엔드 준비 완료. `npm run backend:dev` 로 서버를 띄우세요.')
} else if (task === 'dev') {
  const args = ['-m', 'uvicorn', 'main:app', '--reload', '--host', '127.0.0.1', '--port', '8000']

  if (existsSync(venvPython())) {
    mustSucceed(run(venvPython(), args))
  } else {
    console.warn('[경고] backend/.venv 가 없어 시스템 Python으로 실행합니다.')
    console.warn('       `npm run backend:install` 을 먼저 실행하는 편이 좋습니다.\n')
    mustSucceed(runSystemPython(args))
  }
} else if (task === 'dataset') {
  // BE1 산출물 ② — 정답 데이터 1,000쌍. Ollama가 필요 없다.
  console.log('정답 데이터셋 1,000쌍을 만듭니다. 약 2분 걸립니다.\n')
  mustSucceed(run(venvPython(), [
    'scripts/generate_dataset.py', '--output', 'dataset', '--overwrite',
  ]))
} else if (task === 'index') {
  // BE1 산출물 ① — ChromaDB 임베딩. Ollama와 bge-m3가 필요하다.
  console.log('ChromaDB 색인을 만듭니다.')
  console.log('GPU가 있으면 약 2분, CPU만 있으면 약 50분 걸립니다.')
  console.log('중간에 끊으면 색인이 불완전해지니 끝까지 두세요.\n')
  mustSucceed(run(venvPython(), ['scripts/embed_dataset.py']))
} else if (task === 'test') {
  // 추천 파이프라인·검증·재시도 로직 테스트. LLM을 가짜로 주입해 Ollama 없이 돈다.
  mustSucceed(run(venvPython(), ['-m', 'pytest', 'tests/', '-q']))
} else if (task === 'build-exe') {
  // 4주차 산출물 — backend 전체를 실행 파일 하나(dist/server.exe)로 묶는다.
  // PyInstaller는 실행한 OS용 실행 파일을 만들므로 Windows 배포본은 Windows에서 빌드해야 한다.
  console.log('server 실행 파일을 빌드합니다. 빌드 사양: backend/server.spec')
  console.log('처음이면 PyInstaller 설치까지 몇 분 걸립니다.\n')
  mustSucceed(run(venvPython(), ['-m', 'pip', 'install', 'pyinstaller']))
  mustSucceed(run(venvPython(), ['-m', 'PyInstaller', 'server.spec', '--noconfirm']))
  console.log('\n빌드 완료: backend/dist/server/ 폴더(server.exe + _internal)를 확인하세요.')
  console.log('Ollama·모델은 포함되지 않습니다 — 사용자 PC에 별도 설치가 필요합니다.')
} else {
  console.error('사용법: node scripts/backend.mjs <install|dev|dataset|index|test|build-exe>')
  process.exit(1)
}
