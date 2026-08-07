// 개발 서버 실행 스크립트 (vite + Electron).
//
// 왜 vite를 직접 부르지 않고 이 래퍼를 두는가:
//
// VS Code의 통합 터미널·확장 호스트는 자식 프로세스에 `ELECTRON_RUN_AS_NODE=1`을
// 물려줍니다. 이 변수가 설정돼 있으면 electron.exe가 GUI 런타임이 아니라
// **순수 Node로** 동작합니다. 그러면 메인 프로세스에서
//
//     import { app, BrowserWindow } from 'electron'
//
// 이 `node_modules/electron/index.js`(실행 파일 경로만 export하는 CJS 셰임)로
// 해석되어 다음 에러로 죽습니다.
//
//     SyntaxError: The requested module 'electron' does not provide
//                  an export named 'BrowserWindow'
//
// 그래서 vite를 띄우기 전에 이 변수를 지웁니다. vite가 스폰하는 Electron도
// 이 환경을 물려받습니다.
//
// POSIX에서는 `env -u ELECTRON_RUN_AS_NODE vite` 한 줄로 되지만 Windows에는
// `env` 명령이 없습니다. 타깃이 Windows이므로 Node로 옮겼습니다.

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const VITE_BIN = path.join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js')

if (!existsSync(VITE_BIN)) {
  console.error('[에러] vite를 찾을 수 없습니다. `npm install` 을 먼저 실행하세요.')
  process.exit(1)
}

const env = { ...process.env }
if (env.ELECTRON_RUN_AS_NODE) {
  console.log('[dev] ELECTRON_RUN_AS_NODE 를 해제합니다 (VS Code 등에서 상속됨).')
  delete env.ELECTRON_RUN_AS_NODE
}

// `npm run dev -- --host` 처럼 넘긴 인자를 그대로 전달합니다.
const args = process.argv.slice(2)

const child = spawn(process.execPath, [VITE_BIN, ...args], {
  cwd: ROOT,
  env,
  stdio: 'inherit',
})

child.on('exit', (code, signal) => {
  process.exit(signal ? 1 : code ?? 0)
})
