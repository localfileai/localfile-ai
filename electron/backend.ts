/**
 * 백엔드(server.exe) 수명 관리 — 5주차 배포본.
 *
 * 지금까지는 사용자가 터미널을 하나 더 열어 `npm run backend:dev`를 쳐야 했다.
 * 설치형 앱에서는 그럴 수 없으므로, 앱이 켜질 때 백엔드를 자식 프로세스로
 * 띄우고 앱이 꺼질 때 함께 정리한다.
 *
 * 개발 모드에서는 아무것도 하지 않는다 — `scripts/dev.mjs`가 이미 uvicorn을
 * 띄우고 있어 두 번 띄우면 포트가 충돌한다.
 */
import { app } from 'electron'
import { spawn, execFile, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'

export const BACKEND_ORIGIN = 'http://127.0.0.1:8000'

export type BackendState = {
  /** starting: 뜨는 중 · ready: 응답함 · failed: 실패(detail에 이유) · external: 개발 서버 사용 */
  status: 'starting' | 'ready' | 'failed' | 'external'
  detail: string
}

let child: ChildProcess | null = null
let state: BackendState = { status: 'starting', detail: '' }
const listeners = new Set<(next: BackendState) => void>()

function setState(next: BackendState) {
  state = next
  listeners.forEach((listener) => listener(next))
}

export function getBackendState(): BackendState {
  return state
}

export function onBackendState(listener: (next: BackendState) => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 동봉된 실행 파일 경로. 개발 모드이거나 파일이 없으면 null. */
function packagedBackend(): string | null {
  if (!app.isPackaged) return null
  const name = process.platform === 'win32' ? 'server.exe' : 'server'
  const candidate = path.join(process.resourcesPath, 'backend', name)
  return existsSync(candidate) ? candidate : null
}

async function ping(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_ORIGIN}/health`, {
      signal: AbortSignal.timeout(2000),
    })
    return response.ok
  } catch {
    return false
  }
}

/**
 * 백엔드가 응답할 때까지 기다린다.
 * 색인이 크면 첫 기동에 시간이 걸리므로 넉넉히 잡는다.
 */
async function waitUntilReady(timeoutMs = 90_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await ping()) return true
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  return false
}

export async function startBackend(): Promise<void> {
  // 이미 떠 있으면(개발 서버 등) 그걸 쓴다. 두 번 띄우지 않는다.
  if (await ping()) {
    setState({ status: 'external', detail: '이미 실행 중인 백엔드에 연결했습니다.' })
    return
  }

  const executable = packagedBackend()
  if (!executable) {
    if (app.isPackaged) {
      setState({
        status: 'failed',
        detail: '백엔드 실행 파일을 찾을 수 없습니다. 설치본이 손상됐을 수 있습니다.',
      })
      return
    }
    // 개발 모드: `scripts/dev.mjs`가 띄우는 uvicorn이 올라올 때까지 기다린다.
    // 서버 기동이 앱보다 몇 초 늦는 것이 정상이라 바로 실패로 단정하지 않는다.
    setState({ status: 'starting', detail: '개발 서버(uvicorn)를 기다리는 중입니다…' })
    setState(
      (await waitUntilReady(30_000))
        ? { status: 'external', detail: '개발 서버에 연결했습니다.' }
        : {
            status: 'failed',
            detail: '개발 모드입니다. 다른 터미널에서 `npm run backend:dev`를 실행하세요.',
          },
    )
    return
  }

  setState({ status: 'starting', detail: '앱을 시작하는 중입니다…' })

  child = spawn(executable, [], {
    // 색인·작업 이력을 사용자 데이터 폴더에 저장하게 한다.
    // (Program Files 아래는 쓰기 권한이 없다 — backend/app/core/config.py 참고)
    env: { ...process.env, LOCAL_FILE_AI_HOME: app.getPath('userData') },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  child.stderr?.on('data', (chunk) => console.log('[backend]', String(chunk).trimEnd()))
  child.on('exit', (code) => {
    child = null
    if (state.status !== 'failed') {
      setState({ status: 'failed', detail: `앱 구성 요소가 예기치 않게 종료됐습니다 (코드 ${code}). 앱을 다시 실행해 주세요.` })
    }
  })

  if (await waitUntilReady()) {
    setState({ status: 'ready', detail: '' })
  } else {
    setState({ status: 'failed', detail: '앱 시작이 늦어지고 있습니다. 앱을 다시 실행해 주세요.' })
  }
}

/**
 * 백엔드를 정리한다.
 *
 * PyInstaller onefile은 부트로더(부모)가 실제 파이썬 프로세스(자식)를 띄우는
 * 구조라, 부모만 죽이면 자식이 남아 포트를 붙잡는다. Windows에서는
 * `taskkill /T`로 프로세스 트리를 통째로 정리해야 한다.
 */
export function stopBackend(): void {
  const target = child
  if (!target?.pid) return
  child = null

  if (process.platform === 'win32') {
    execFile('taskkill', ['/pid', String(target.pid), '/T', '/F'], () => undefined)
  } else {
    target.kill('SIGTERM')
  }
}
