// 실행 환경을 점검하고, 빠진 것과 다음에 할 일을 알려 준다.
//
//   npm run doctor
//
// 팀원이 클론 직후 무엇이 준비됐고 무엇이 남았는지 한 번에 보게 하는 것이 목적이다.

import { spawnSync } from 'node:child_process'
import { existsSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const BACKEND = path.join(ROOT, 'backend')
const IS_WINDOWS = process.platform === 'win32'

const OK = '  [ O ]'
const NO = '  [ X ]'
const WARN = '  [ ! ]'

const todo = []

function venvPython() {
  return IS_WINDOWS
    ? path.join(BACKEND, '.venv', 'Scripts', 'python.exe')
    : path.join(BACKEND, '.venv', 'bin', 'python')
}

function folderSize(dir) {
  if (!existsSync(dir)) return 0
  let total = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    total += entry.isDirectory() ? folderSize(full) : statSync(full).size
  }
  return total
}

function mb(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

console.log('')
console.log('LocalFile AI · 환경 점검')
console.log('='.repeat(58))

// --- 1. 기본 도구 ---
console.log('\n[1] 기본 도구')
console.log(`${OK} Node.js ${process.version}`)

const python = existsSync(venvPython())
if (python) {
  const version = spawnSync(venvPython(), ['--version'], { encoding: 'utf8' })
  console.log(`${OK} 백엔드 가상환경 ${(version.stdout || version.stderr || '').trim()}`)
} else {
  console.log(`${NO} 백엔드 가상환경 없음 (backend/.venv)`)
  todo.push('npm run setup')
}

// --- 2. 의존성 ---
console.log('\n[2] 의존성')
if (existsSync(path.join(ROOT, 'node_modules'))) {
  console.log(`${OK} node_modules`)
} else {
  console.log(`${NO} node_modules 없음`)
  todo.push('npm install')
}

if (python) {
  const check = spawnSync(
    venvPython(),
    ['-c', 'import fastapi, fitz, chromadb, olefile; print("ok")'],
    { encoding: 'utf8', cwd: BACKEND },
  )
  if (check.stdout && check.stdout.includes('ok')) {
    console.log(`${OK} 파이썬 패키지 (fastapi · PyMuPDF · chromadb · olefile)`)
  } else {
    console.log(`${NO} 파이썬 패키지 일부 누락`)
    todo.push('npm run setup')
  }
}

// --- 3. 데이터 ---
console.log('\n[3] 데이터 (BE1 산출물)')
const datasetCsv = path.join(BACKEND, 'dataset', 'dataset.csv')
if (existsSync(datasetCsv)) {
  const files = path.join(BACKEND, 'dataset', 'files')
  console.log(`${OK} 정답 데이터셋 (${mb(folderSize(path.join(BACKEND, 'dataset')))})`)
  if (!existsSync(files)) console.log(`${WARN}   files/ 폴더가 없습니다`)
} else {
  console.log(`${NO} 정답 데이터셋 없음`)
  todo.push('npm run dataset      (약 2분)')
}

const chroma = path.join(BACKEND, 'chroma_db')
if (existsSync(chroma)) {
  console.log(`${OK} 벡터 색인 (${mb(folderSize(chroma))})`)
} else {
  console.log(`${WARN} 벡터 색인 없음 — 실제 검색이 비활성화됩니다 (Mock 검색은 동작)`)
  todo.push('npm run index        (GPU 약 2분 / CPU 약 50분)')
}

// --- 4. Ollama ---
console.log('\n[4] Ollama (실제 검색·추천용. 없어도 앱은 실행됩니다)')
try {
  const response = await fetch('http://localhost:11434/api/tags', {
    signal: AbortSignal.timeout(3000),
  })
  const body = await response.json()
  const names = (body.models || []).map((m) => m.name)
  console.log(`${OK} 서버 실행 중 · 모델 ${names.length}개`)

  for (const need of ['bge-m3', 'exaone3.5:2.4b']) {
    const found = names.some((n) => n.split(':')[0] === need.split(':')[0])
    if (found) {
      console.log(`${OK}   ${need}`)
    } else {
      console.log(`${NO}   ${need} 없음`)
      todo.push(`ollama pull ${need}`)
    }
  }
} catch {
  console.log(`${WARN} 서버에 연결할 수 없습니다 (http://localhost:11434)`)
  console.log('        Ollama를 설치·실행하면 실제 검색이 켜집니다. https://ollama.com')
}

// --- 5. 경로 주의 ---
console.log('\n[5] 경로')
if (/[^\x00-\x7F]/.test(ROOT)) {
  console.log(`${WARN} 경로에 한글이 있습니다`)
  console.log('        ChromaDB가 한글 절대경로를 열지 못해 상대경로로 우회합니다.')
  console.log('        반드시 `npm run backend:dev` 로 실행하세요 (직접 uvicorn 실행 시 실패).')
} else {
  console.log(`${OK} 경로에 비ASCII 문자 없음`)
}

// --- 정리 ---
console.log('\n' + '='.repeat(58))
if (todo.length === 0) {
  console.log('모두 준비됐습니다. 터미널 두 개에서 실행하세요.')
  console.log('')
  console.log('  터미널 1 :  npm run backend:dev')
  console.log('  터미널 2 :  npm run dev')
} else {
  console.log('남은 작업:')
  for (const item of todo) console.log(`  - ${item}`)
}
console.log('')
