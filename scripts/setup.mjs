// 클론 직후 한 번만 실행하는 준비 스크립트.
//
//   npm run setup
//
// 하는 일
//   1. backend/.venv 생성 + 파이썬 의존성 설치
//   2. 정답 데이터셋 1,000쌍 생성 (BE1 산출물 ②)
//   3. 환경 점검 결과 출력
//
// 벡터 색인(`npm run index`)은 Ollama가 필요하고 CPU에서 오래 걸려 여기 넣지 않았다.
// 색인이 없어도 앱은 Mock 검색으로 정상 실행된다.

import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const BACKEND = path.join(ROOT, 'backend')
const IS_WINDOWS = process.platform === 'win32'

function step(number, title) {
  console.log('')
  console.log('='.repeat(58))
  console.log(`[${number}/3] ${title}`)
  console.log('='.repeat(58))
}

function node(args) {
  const result = spawnSync(process.execPath, args, { cwd: ROOT, stdio: 'inherit' })
  if (result.status !== 0) {
    console.error('\n[중단] 위 단계에서 실패했습니다.')
    process.exit(result.status ?? 1)
  }
}

const venvPython = IS_WINDOWS
  ? path.join(BACKEND, '.venv', 'Scripts', 'python.exe')
  : path.join(BACKEND, '.venv', 'bin', 'python')

step(1, '백엔드 가상환경과 파이썬 의존성')
if (existsSync(venvPython)) {
  console.log('backend/.venv 가 이미 있습니다. 의존성만 확인합니다.\n')
}
node([path.join('scripts', 'backend.mjs'), 'install'])

step(2, '정답 데이터셋 1,000쌍 (BE1 산출물)')
if (existsSync(path.join(BACKEND, 'dataset', 'dataset.csv'))) {
  console.log('dataset/ 이 이미 있습니다. 건너뜁니다.')
  console.log('다시 만들려면: npm run dataset')
} else {
  node([path.join('scripts', 'backend.mjs'), 'dataset'])
}

step(3, '환경 점검')
node([path.join('scripts', 'doctor.mjs')])
