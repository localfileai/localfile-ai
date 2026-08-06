/**
 * Ollama(모델 실행기) 설치·복구 도우미 — 5주차 배포본, 6주차 대폭 보강.
 *
 * 모델을 받는 것은 백엔드가 하지만(`POST /setup/models`), **Ollama 자체가
 * 없으면 받을 곳도 없다.** 그 설치를 이 모듈이 사용자 개입 없이 끝낸다.
 *
 * 실제 PC들에서 겪은 실패가 이 구조를 만들었다.
 *
 *  1) 낡거나 깨진 Ollama — 응답은 하는데 `llama-server binary not found`로
 *     모델을 못 돌린다. → `repair` 모드: 떠 있어도 설치본을 덮어씌운다.
 *  2) ollama.com 다운로드가 막힌 PC — 설치본을 못 받아 브라우저 링크를
 *     열었고, 사용자가 직접 설치해야 했다. → 이제 3중으로 시도한다:
 *
 *     ① ollama.com 공식 설치본 → 무인 설치
 *     ② GitHub 릴리스의 같은 설치본 → 무인 설치   (ollama.com만 막힌 경우)
 *     ③ GitHub 릴리스의 무설치(zip) 배포본 → 앱 데이터 폴더에 풀고
 *        앱이 직접 `ollama serve`를 띄운다                  (설치 자체가 안 되는 경우)
 *
 *     ③까지 가면 Ollama는 "설치된 프로그램"이 아니라 **앱이 관리하는 부속
 *     실행 파일**이 된다. 앱이 뜰 때 같이 뜨고(main.ts), 앱이 꺼지면 같이
 *     꺼진다. 사용자는 Ollama라는 것이 존재하는지도 몰라도 된다.
 *
 * 브라우저로 다운로드 페이지를 여는 것은 Windows가 아닌 OS에서만 남는다.
 */
import { shell, app } from 'electron'
import { execFile, spawn, type ChildProcess } from 'node:child_process'
import { createWriteStream, existsSync } from 'node:fs'
import { mkdir, unlink } from 'node:fs/promises'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const DOWNLOAD_PAGE = 'https://ollama.com/download'

/** 설치본을 받아 볼 곳들. 앞의 것이 막혀도 뒤가 있다. */
const INSTALLER_URLS = [
  'https://ollama.com/download/OllamaSetup.exe',
  'https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe',
]
/** 무설치(portable) 배포본. 설치 프로그램 실행 자체가 막힌 PC의 마지막 수단. */
const PORTABLE_ZIP_URL =
  'https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip'

/** 소스 하나당 내려받기 재시도 횟수. */
const DOWNLOAD_ATTEMPTS = 2

export type InstallProgress = {
  phase: 'downloading' | 'installing' | 'ready' | 'opened-page' | 'failed'
  percent: number
  detail: string
}

export type InstallOptions = {
  /** 이미 응답 중이어도 설치본을 덮어씌운다 (실행기가 깨졌을 때). */
  repair?: boolean
}

/** Ollama가 응답하는지. HTTP가 되는지만 본다 — 모델이 도는지는 백엔드가 판정한다. */
async function ollamaAlive(): Promise<boolean> {
  try {
    const response = await fetch('http://localhost:11434/api/tags', {
      signal: AbortSignal.timeout(2000),
    })
    return response.ok
  } catch {
    return false
  }
}

/** 설치가 끝나 서비스가 뜰 때까지 기다린다. */
async function waitUntilAlive(timeoutMs = 120_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await ollamaAlive()) return true
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return false
}

/** 연결이 안 되면 이만큼 기다리고 포기한다. */
const CONNECT_TIMEOUT_MS = 30_000
/**
 * 데이터가 이만큼 끊기면 죽은 연결로 본다.
 *
 * 전체 시간에 상한을 두면 안 된다 — 수백 MB짜리라 느린 회선에서는 정상적으로도
 * 10분 넘게 걸린다. 대신 "흐르고 있는가"만 본다. 이 감시가 없으면 연결이
 * 조용히 끊겼을 때 promise가 영영 안 끝나고, 화면은 버튼이 잠긴 채로 굳는다.
 */
const STALL_TIMEOUT_MS = 60_000

async function downloadFile(
  url: string,
  target: string,
  label: string,
  onProgress: (progress: InstallProgress) => void,
): Promise<void> {
  const controller = new AbortController()
  let stallTimer: NodeJS.Timeout | undefined
  const armStallTimer = () => {
    clearTimeout(stallTimer)
    stallTimer = setTimeout(() => controller.abort(), STALL_TIMEOUT_MS)
  }

  const connectTimer = setTimeout(() => controller.abort(), CONNECT_TIMEOUT_MS)
  try {
    const response = await fetch(url, { signal: controller.signal })
    clearTimeout(connectTimer)
    if (!response.ok || !response.body) {
      throw new Error(`${label}을 받을 수 없습니다 (HTTP ${response.status})`)
    }

    const total = Number(response.headers.get('content-length') || 0)
    let received = 0

    const source = Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0])
    source.on('data', (chunk: Buffer) => {
      received += chunk.length
      armStallTimer()
      onProgress({
        phase: 'downloading',
        percent: total ? (received / total) * 100 : 0,
        detail: `${label}을 내려받는 중입니다…`,
      })
    })

    armStallTimer()
    await pipeline(source, createWriteStream(target), { signal: controller.signal })
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`${label} 내려받기가 중간에 끊겼습니다 (응답 없음)`)
    }
    throw error
  } finally {
    clearTimeout(connectTimer)
    clearTimeout(stallTimer)
  }
}

/** 여러 소스에서 차례로 받아 본다. 전부 실패하면 마지막 오류를 올린다. */
async function downloadFromAnySource(
  urls: string[],
  target: string,
  label: string,
  onProgress: (progress: InstallProgress) => void,
): Promise<void> {
  let lastError: Error = new Error(`${label}을 받을 곳이 없습니다`)
  for (const url of urls) {
    for (let attempt = 1; attempt <= DOWNLOAD_ATTEMPTS; attempt += 1) {
      try {
        await downloadFile(url, target, label, onProgress)
        return
      } catch (error) {
        lastError = error as Error
        await unlink(target).catch(() => undefined)
        onProgress({
          phase: 'downloading',
          percent: 0,
          detail: `내려받기에 실패해 다른 경로로 다시 시도합니다… (${lastError.message})`,
        })
        await new Promise((resolve) => setTimeout(resolve, 2000 * attempt))
      }
    }
  }
  throw lastError
}

/** 설치 프로그램을 무인 모드로 실행한다. */
async function runInstaller(target: string): Promise<void> {
  // Ollama 설치본은 Inno Setup 계열이라 /VERYSILENT를 받는다. 배포 방식이
  // 바뀌어 이 옵션을 모르면 창이 뜨는데, 그때는 사용자가 [다음]만 누르면 되고
  // 대기 로직이 완료를 알아서 감지한다.
  await new Promise<void>((resolve) => {
    execFile(target, ['/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES'], () => resolve())
  })
}

// ---------------------------------------------------------------------------
// 무설치(portable) Ollama — 설치 프로그램이 통하지 않는 PC의 마지막 수단.
// 앱 데이터 폴더에 풀어 두고 앱이 직접 serve를 띄운다.
// ---------------------------------------------------------------------------

function portableDir(): string {
  return path.join(app.getPath('userData'), 'ollama-portable')
}

function portableExe(): string {
  return path.join(portableDir(), 'ollama.exe')
}

let managedServe: ChildProcess | null = null

/** 무설치 Ollama의 serve를 띄운다. 이미 떠 있으면 아무것도 안 한다. */
async function spawnPortableServe(): Promise<boolean> {
  if (!existsSync(portableExe())) return false
  if (await ollamaAlive()) return true

  // 이전에 우리가 띄운 것이 좀비로 남았으면 정리한다.
  if (managedServe && !managedServe.killed) managedServe.kill()

  managedServe = spawn(portableExe(), ['serve'], {
    stdio: 'ignore',
    windowsHide: true,
    env: { ...process.env },
  })
  managedServe.on('exit', () => {
    managedServe = null
  })
  return waitUntilAlive(60_000)
}

/** zip을 앱 데이터 폴더에 푼다. Windows에는 unzip이 없어 PowerShell을 쓴다. */
async function extractPortableZip(zipPath: string): Promise<void> {
  await mkdir(portableDir(), { recursive: true })
  await new Promise<void>((resolve, reject) => {
    execFile(
      'powershell.exe',
      [
        '-NoProfile', '-NonInteractive', '-Command',
        `Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${portableDir()}' -Force`,
      ],
      { windowsHide: true },
      (error) => (error ? reject(error) : resolve()),
    )
  })
  if (!existsSync(portableExe())) {
    throw new Error('압축은 풀렸는데 ollama.exe가 보이지 않습니다')
  }
}

/** 무설치 배포본을 받아 풀고 serve까지 띄운다. */
async function installPortable(
  onProgress: (progress: InstallProgress) => void,
): Promise<boolean> {
  const zipPath = path.join(app.getPath('temp'), 'ollama-portable.zip')
  try {
    await downloadFromAnySource([PORTABLE_ZIP_URL], zipPath, '문서 분석 도구', onProgress)
    onProgress({ phase: 'installing', percent: 100, detail: '실행기를 준비하는 중입니다… (1~2분)' })
    await extractPortableZip(zipPath)
    return await spawnPortableServe()
  } finally {
    await unlink(zipPath).catch(() => undefined)
  }
}

/**
 * 앱 시작 시 부른다(main.ts) — 무설치 Ollama를 쓰는 PC에서는 시스템 서비스가
 * 없으므로, serve를 앱이 매번 직접 띄워야 한다. 무설치본이 없는 PC에서는
 * 아무 일도 하지 않는다.
 */
export async function startPortableOllamaIfPresent(): Promise<void> {
  if (process.platform !== 'win32') return
  try {
    await spawnPortableServe()
  } catch {
    // 준비 화면의 installOllama 경로가 다시 시도한다.
  }
}

/** 앱 종료 시 부른다 — 우리가 띄운 serve만 정리한다. 시스템 Ollama는 건드리지 않는다. */
export function stopPortableOllama(): void {
  if (managedServe && !managedServe.killed) managedServe.kill()
  managedServe = null
}

// ---------------------------------------------------------------------------

/**
 * Ollama를 사용자 개입 없이 준비한다. 공식 설치본(2개 소스) → 무설치 배포본
 * 순서로 시도하고, Windows에서는 브라우저를 열지 않는다 — 실패해도 화면에
 * 이유와 [다시 시도]가 남는 편이, 링크를 열고 사용자에게 떠넘기는 것보다 낫다.
 *
 * `repair`를 주면 이미 응답 중이어도 다시 깐다 — 실행기 파일이 빠진 설치를
 * 되돌리는 유일한 방법이다.
 */
export async function installOllama(
  onProgress: (progress: InstallProgress) => void,
  options: InstallOptions = {},
): Promise<InstallProgress> {
  if (process.platform !== 'win32') {
    await shell.openExternal(DOWNLOAD_PAGE)
    return {
      phase: 'opened-page',
      percent: 100,
      detail: '브라우저에서 Ollama 설치 페이지를 열었습니다. 설치 후 [다시 확인]을 눌러 주세요.',
    }
  }

  if (!options.repair) {
    if (await ollamaAlive()) {
      return { phase: 'ready', percent: 100, detail: '문서 분석 도구가 이미 준비돼 있습니다.' }
    }
    // 지난번에 무설치본으로 깔아 둔 PC — 받을 것 없이 띄우기만 하면 된다.
    if (await spawnPortableServe().catch(() => false)) {
      return { phase: 'ready', percent: 100, detail: '문서 분석 도구를 시작했습니다.' }
    }
  }

  // 1·2차: 공식 설치본 무인 설치 (ollama.com → GitHub 순서)
  const target = path.join(app.getPath('temp'), 'OllamaSetup.exe')
  try {
    await downloadFromAnySource(INSTALLER_URLS, target, '문서 분석 도구 설치 파일', onProgress)

    onProgress({
      phase: 'installing',
      percent: 100,
      detail: options.repair
        ? '실행기를 다시 설치하는 중입니다… (몇 분 걸릴 수 있습니다)'
        : '실행기를 설치하는 중입니다…',
    })
    await runInstaller(target)

    onProgress({ phase: 'installing', percent: 100, detail: '설치를 마무리하는 중입니다…' })
    const alive = await waitUntilAlive()
    await unlink(target).catch(() => undefined)

    if (alive) {
      return { phase: 'ready', percent: 100, detail: '문서 분석 도구 준비가 끝났습니다.' }
    }
    // 설치는 됐다는데 안 뜬다 — 무설치본으로 넘어가지 말고 여기서 알린다.
    // (같은 포트를 두 실행기가 다투는 상태를 만들 수 있다.)
    return {
      phase: 'failed',
      percent: 100,
      detail: '실행기가 설치됐지만 아직 응답하지 않습니다. 잠시 뒤 [다시 확인]을 눌러 주세요.',
    }
  } catch (installerError) {
    await unlink(target).catch(() => undefined)

    // 3차: 무설치 배포본. 설치 프로그램 다운로드·실행이 모두 막힌 PC까지 커버한다.
    try {
      onProgress({
        phase: 'downloading',
        percent: 0,
        detail: '설치본이 막혀 있어 무설치 버전으로 전환합니다…',
      })
      if (await installPortable(onProgress)) {
        return { phase: 'ready', percent: 100, detail: '문서 분석 도구 준비가 끝났습니다.' }
      }
      return {
        phase: 'failed',
        percent: 100,
        detail: '실행기를 풀어 놓았지만 아직 응답하지 않습니다. 잠시 뒤 [다시 확인]을 눌러 주세요.',
      }
    } catch (portableError) {
      return {
        phase: 'failed',
        percent: 0,
        detail:
          '실행기를 자동으로 준비하지 못했습니다. 인터넷 연결을 확인하고 [다시 시도]를 눌러 주세요. ' +
          `(설치본: ${(installerError as Error).message} / 무설치본: ${(portableError as Error).message})`,
      }
    }
  }
}
