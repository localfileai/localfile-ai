/**
 * Ollama(모델 실행기) 준비 — 사용자 개입 없이 끝내는 것이 목표다.
 *
 * 모델을 받는 것은 백엔드가 하지만(`POST /setup/models`), **실행기 자체가
 * 없으면 받을 곳도 없다.** 그 준비를 이 모듈이 맡는다.
 *
 * ## 왜 무설치(portable)본이 기본 경로인가
 *
 * 처음에는 공식 설치본(OllamaSetup.exe)을 무인 실행하는 것이 기본이었다.
 * 실제 PC들에서 서로 다른 이유로 세 번 실패했다.
 *
 *   1) 응답은 하는데 `llama-server binary not found` — 설치본이 깨져 있었다
 *   2) `spawn UNKNOWN` — 실행에 관리자 승인(UAC)이 필요해 직접 실행이 즉사했다
 *   3) ShellExecute로 권한을 넘겼더니: Inno 설치본의 비관리자 스텁이 관리자
 *      사본을 띄우고 **즉시 종료**해서, 대기 로직이 설치가 끝난 줄 알고
 *      지나갔고, 무인 모드는 설치 후 실행기를 시작하지도 않는다
 *
 * 무설치본은 이 문제가 전부 없다: 앱 데이터 폴더에 풀고 앱이 자식 프로세스로
 * `serve`를 띄운다. 관리자 권한도, 설치 마법사도, 자동 시작 등록도 필요 없다.
 * 실행기는 앱이 뜰 때 같이 뜨고(main.ts) 꺼질 때 같이 꺼진다. 다운로드가
 * 700MB → 1.4GB로 커지는 대신 **결정적으로 동작한다**.
 *
 * 공식 설치본은 두 경우에만 쓴다.
 *   - 예비: 무설치본 다운로드·해제가 실패한 PC
 *   - 복구(repair): 깨진 **시스템 설치**가 포트를 잡고 있을 때 — 덮어써야 한다
 *
 * 전 과정을 setup.log(앱 데이터 폴더)에 남긴다. 남의 PC에서 실패하면
 * 스크린샷이 아니라 이 파일이 진단이다.
 */
import { shell, app } from 'electron'
import { execFile, spawn, type ChildProcess } from 'node:child_process'
import { createWriteStream, existsSync, readdirSync } from 'node:fs'
import { mkdir, open, readdir, unlink } from 'node:fs/promises'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { slog } from './log'

const DOWNLOAD_PAGE = 'https://ollama.com/download'

/** 무설치(portable) 배포본 — 기본 경로. */
const PORTABLE_ZIP_URLS = [
  'https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip',
]
/** 공식 설치본 — 예비·복구 경로. 앞이 막혀도 뒤가 있다. */
const INSTALLER_URLS = [
  'https://ollama.com/download/OllamaSetup.exe',
  'https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe',
]

/** 소스 하나당 내려받기 재시도 횟수. */
const DOWNLOAD_ATTEMPTS = 2

export type InstallProgress = {
  phase: 'downloading' | 'installing' | 'ready' | 'opened-page' | 'failed'
  percent: number
  detail: string
}

export type InstallOptions = {
  /** 이미 응답 중이어도 다시 준비한다 (시스템 설치가 깨졌을 때). */
  repair?: boolean
}

const ready = (detail: string): InstallProgress => ({ phase: 'ready', percent: 100, detail })

/** 실행기가 응답하는지. HTTP가 되는지만 본다 — 모델이 도는지는 백엔드가 판정한다. */
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

/** 실행기가 뜰 때까지 기다린다. onTick으로 경과를 알려 멈춘 것처럼 보이지 않게 한다. */
async function waitUntilAlive(
  timeoutMs: number,
  onTick?: (elapsedSec: number) => void,
): Promise<boolean> {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    if (await ollamaAlive()) return true
    onTick?.(Math.round((Date.now() - startedAt) / 1000))
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return false
}

/** 연결이 안 되면 이만큼 기다리고 포기한다. */
const CONNECT_TIMEOUT_MS = 30_000
/**
 * 데이터가 이만큼 끊기면 죽은 연결로 본다.
 *
 * 전체 시간에 상한을 두면 안 된다 — 1.4GB짜리라 느린 회선에서는 정상적으로도
 * 수십 분 걸린다. 대신 "흐르고 있는가"만 본다. 이 감시가 없으면 연결이
 * 조용히 끊겼을 때 promise가 영영 안 끝나고, 화면은 스피너만 돌며 굳는다.
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
    slog('download ok', url, `${received} bytes`)
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
        slog('download failed', url, lastError.message)
        await unlink(target).catch(() => undefined)
        onProgress({
          phase: 'downloading',
          percent: 0,
          detail: `내려받기에 실패해 다시 시도합니다… (${lastError.message})`,
        })
        await new Promise((resolve) => setTimeout(resolve, 2000 * attempt))
      }
    }
  }
  throw lastError
}

/** 받은 파일이 기대한 형식인지 첫 바이트로 확인한다. 차단 페이지가 200으로
 *  HTML을 돌려주는 경우를 실행·해제 전에 잡는다. */
async function assertMagic(target: string, magic: string, label: string): Promise<void> {
  const handle = await open(target, 'r')
  try {
    const { buffer } = await handle.read(Buffer.alloc(magic.length), 0, magic.length, 0)
    if (buffer.toString('latin1') !== magic) {
      throw new Error(`${label}이 올바른 형식이 아닙니다 (네트워크 차단 페이지일 수 있습니다)`)
    }
  } finally {
    await handle.close()
  }
}

// ---------------------------------------------------------------------------
// 실행기 프로세스 관리 — 무설치본이든 설치본이든, 스스로 안 뜨면 앱이 띄운다.
// ---------------------------------------------------------------------------

function portableDir(): string {
  return path.join(app.getPath('userData'), 'ollama-portable')
}

/** 풀어 놓은 폴더에서 ollama.exe를 찾는다. 압축 도구나 배포 방식에 따라
 *  하위 폴더에 풀릴 수 있어 몇 단계 내려가며 찾는다. */
function findPortableExe(dir = portableDir(), depth = 3): string | null {
  if (!existsSync(dir)) return null
  const direct = path.join(dir, 'ollama.exe')
  if (existsSync(direct)) return direct
  if (depth <= 0) return null
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      const found = findPortableExe(path.join(dir, entry.name), depth - 1)
      if (found) return found
    }
  } catch {
    // 읽기 실패는 "없음"과 같다
  }
  return null
}

/** 설치본이 실행기를 깔아 두는 곳들. 사용자별 설치가 기본이고, 관리자 권한으로
 *  깔린 시스템 전체 설치가 그다음이다. */
function findInstalledExe(): string | null {
  const candidates = [
    process.env.LOCALAPPDATA
      && path.join(process.env.LOCALAPPDATA, 'Programs', 'Ollama', 'ollama.exe'),
    'C:\\Program Files\\Ollama\\ollama.exe',
    'C:\\Program Files (x86)\\Ollama\\ollama.exe',
  ]
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate
  }
  return null
}

let managedServe: ChildProcess | null = null

/** 실행기(serve)를 앱의 자식 프로세스로 띄운다. 이미 떠 있으면 그대로 둔다.
 *
 *  왜 앱이 직접 띄우는가: 무인 설치는 파일만 깔고 실행기를 시작하지 않고,
 *  무설치본에는 애초에 자동 시작이라는 개념이 없다. 시작해 주는 주체가
 *  앱뿐이다.
 */
async function spawnServeFrom(exe: string, waitMs = 20_000): Promise<boolean> {
  if (await ollamaAlive()) return true

  // 이전에 우리가 띄운 것이 좀비로 남았으면 정리한다.
  if (managedServe && !managedServe.killed) managedServe.kill()

  slog('spawn serve', exe)
  managedServe = spawn(exe, ['serve'], {
    // 실행기가 lib/를 자기 위치 기준으로 찾으므로 작업 폴더를 맞춰 준다.
    cwd: path.dirname(exe),
    stdio: 'ignore',
    windowsHide: true,
    env: { ...process.env },
  })
  managedServe.on('error', (error) => {
    slog('serve spawn error', error.message)
    managedServe = null
  })
  managedServe.on('exit', (code) => {
    slog('serve exit', code)
    managedServe = null
  })
  return waitUntilAlive(waitMs)
}

/** 무설치 실행기를 띄운다. 무설치본이 없으면 false. */
async function spawnPortableServe(): Promise<boolean> {
  const exe = findPortableExe()
  if (!exe) return false
  return spawnServeFrom(exe)
}

/** 설치된 실행기를 띄운다. 설치돼 있지 않으면 false. */
async function spawnInstalledServe(waitMs = 20_000): Promise<boolean> {
  const exe = findInstalledExe()
  slog('installed exe', exe ?? 'none')
  if (!exe) return false
  return spawnServeFrom(exe, waitMs)
}

/** 시스템에 떠 있는 실행기들을 강제로 내린다. 복구에서 설치본까지 실패했을 때,
 *  깨진 시스템 실행기가 포트를 잡은 채로는 무설치본도 못 뜨기 때문이다. */
async function killSystemOllama(): Promise<void> {
  for (const image of ['ollama app.exe', 'ollama.exe', 'llama-server.exe']) {
    await new Promise<void>((resolve) => {
      execFile('taskkill', ['/IM', image, '/F'], { windowsHide: true }, () => resolve())
    })
  }
  await new Promise((resolve) => setTimeout(resolve, 1500))
  slog('killed system ollama processes')
}

// ---------------------------------------------------------------------------
// 무설치(portable) 설치 — 기본 경로
// ---------------------------------------------------------------------------

/** zip을 앱 데이터 폴더에 푼다.
 *
 *  tar.exe(Windows 10+ 내장 bsdtar)를 먼저 쓴다 — 1.4GB짜리 zip을 스트리밍으로
 *  풀어 빠르고, 실패하면 확실하게 실패한다. PowerShell Expand-Archive는 예비인데
 *  반드시 오류를 종결 오류로 승격시킨다 — 기본 설정에서는 파일 몇 개를 못
 *  풀어도 exit 0으로 끝나서, "성공했는데 실행 파일이 없는" 상태를 실제 PC에서
 *  만들었다.
 */
async function extractPortableZip(zipPath: string): Promise<void> {
  await mkdir(portableDir(), { recursive: true })

  const runExtractor = (file: string, args: string[]) =>
    new Promise<void>((resolve, reject) => {
      execFile(file, args, { windowsHide: true, maxBuffer: 8 * 1024 * 1024 },
        (error, _stdout, stderr) => (error
          ? reject(new Error(`${path.basename(file)}: ${String(stderr || error.message).slice(0, 200)}`))
          : resolve()))
    })

  try {
    await runExtractor('tar.exe', ['-xf', zipPath, '-C', portableDir()])
    slog('extracted with tar')
  } catch (tarError) {
    slog('tar failed', (tarError as Error).message)
    try {
      await runExtractor('powershell.exe', [
        '-NoProfile', '-NonInteractive', '-Command',
        `$ErrorActionPreference = 'Stop'; ` +
        `Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${portableDir()}' -Force`,
      ])
      slog('extracted with Expand-Archive')
    } catch (psError) {
      throw new Error(`압축을 풀지 못했습니다 (tar: ${(tarError as Error).message} ` +
                      `/ powershell: ${(psError as Error).message})`)
    }
  }

  if (!findPortableExe()) {
    // 다음에 이 오류를 볼 때 원인을 알 수 있게, 뭐가 풀렸는지를 남긴다.
    const entries = await readdir(portableDir()).catch(() => [] as string[])
    slog('extracted but exe missing', entries)
    throw new Error(
      `압축은 풀렸는데 실행 파일이 보이지 않습니다 (내용: ${entries.slice(0, 10).join(', ') || '비어 있음'})`)
  }
}

/** 무설치 배포본을 받아 풀고 serve까지 띄운다. 성공하면 true. */
async function installPortable(
  onProgress: (progress: InstallProgress) => void,
): Promise<boolean> {
  const zipPath = path.join(app.getPath('temp'), 'ollama-portable.zip')
  try {
    await downloadFromAnySource(PORTABLE_ZIP_URLS, zipPath, '문서 분석 도구', onProgress)
    await assertMagic(zipPath, 'PK', '문서 분석 도구')
    onProgress({ phase: 'installing', percent: 100, detail: '문서 분석 도구를 준비하는 중입니다… (1~2분)' })
    await extractPortableZip(zipPath)
    onProgress({ phase: 'installing', percent: 100, detail: '문서 분석 도구를 시작하는 중입니다…' })
    return await spawnPortableServe()
  } finally {
    await unlink(zipPath).catch(() => undefined)
  }
}

// ---------------------------------------------------------------------------
// 공식 설치본 — 예비·복구 경로
// ---------------------------------------------------------------------------

const SILENT_ARGS = ['/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES']

/** 설치 프로그램을 무인 모드로 실행한다. 완료·실패를 정확히 알 수 없는 경로다 —
 *  권한 상승 스텁이 관리자 사본을 띄우고 즉시 종료하는 설치본이 있어서,
 *  "프로세스가 끝났다 = 설치가 끝났다"가 성립하지 않는다. 그래서 호출부가
 *  설치 결과를 파일 존재로 재확인한다. */
async function runInstaller(
  target: string,
  onProgress: (progress: InstallProgress) => void,
): Promise<void> {
  try {
    await new Promise<void>((resolve, reject) => {
      execFile(target, SILENT_ARGS, (error) => (error ? reject(error) : resolve()))
    })
    slog('installer ran directly')
    return
  } catch (directError) {
    slog('direct run failed', (directError as Error).message)
    // 직접 실행은 관리자 승인(UAC)이 필요한 설치본에서 ERROR_ELEVATION_REQUIRED
    // (Node 표기로 "spawn UNKNOWN")로 죽는다. ShellExecute(Start-Process)로
    // 넘기면 Windows가 권한 확인 창을 띄워 준다.
    onProgress({
      phase: 'installing',
      percent: 100,
      detail: '권한 확인 창이 뜨면 [예]를 눌러 주세요…',
    })
    await new Promise<void>((resolve, reject) => {
      execFile(
        'powershell.exe',
        [
          '-NoProfile', '-NonInteractive', '-Command',
          `$p = Start-Process -FilePath '${target}' ` +
          `-ArgumentList '${SILENT_ARGS.join("','")}' -Wait -PassThru; exit $p.ExitCode`,
        ],
        { windowsHide: true },
        (shellError) => (shellError
          ? reject(new Error(
              `설치를 실행하지 못했습니다 ` +
              `(직접: ${(directError as Error).message} / 권한 상승: ${shellError.message})`))
          : resolve()),
      )
    })
    slog('installer ran via Start-Process')
  }
}

/** 공식 설치본으로 설치하고 실행까지 확인한다. 실패하면 던진다. */
async function installViaInstaller(
  onProgress: (progress: InstallProgress) => void,
  repair: boolean,
): Promise<InstallProgress> {
  const target = path.join(app.getPath('temp'), 'OllamaSetup.exe')
  try {
    await downloadFromAnySource(INSTALLER_URLS, target, '문서 분석 도구 설치 파일', onProgress)
    await assertMagic(target, 'MZ', '문서 분석 도구 설치 파일')

    onProgress({
      phase: 'installing',
      percent: 100,
      detail: repair
        ? '문서 분석 도구를 다시 설치하는 중입니다… (몇 분 걸릴 수 있습니다)'
        : '문서 분석 도구를 설치하는 중입니다…',
    })
    await runInstaller(target, onProgress)

    // 설치 프로그램이 끝났다고 실행기가 뜨는 것도, 심지어 설치가 끝난 것도
    // 아니다 (권한 상승 스텁은 즉시 종료하고 진짜 설치는 뒤에서 돈다).
    // 파일이 나타나고 실행기가 응답할 때까지, 스폰을 섞어 가며 재확인한다.
    for (let round = 1; round <= 8; round += 1) {
      onProgress({
        phase: 'installing',
        percent: 100,
        detail: `설치를 마무리하는 중입니다… (${round}/8)`,
      })
      if (await waitUntilAlive(5_000)) return ready('문서 분석 도구 준비가 끝났습니다.')
      if (await spawnInstalledServe(10_000).catch(() => false)) {
        return ready('문서 분석 도구 준비가 끝났습니다.')
      }
    }
    throw new Error('설치는 끝났지만 실행기가 시작되지 않습니다')
  } finally {
    await unlink(target).catch(() => undefined)
  }
}

// ---------------------------------------------------------------------------

/**
 * 앱 시작 시 부른다(main.ts) — 실행기가 준비돼 있는데 안 떠 있으면 앱이 직접
 * 띄운다. 아무것도 없으면 조용히 넘어간다 (준비 화면이 설치부터 맡는다).
 */
export async function startPortableOllamaIfPresent(): Promise<void> {
  if (process.platform !== 'win32') return
  try {
    if (await ollamaAlive()) return
    if (await spawnInstalledServe()) return
    await spawnPortableServe()
  } catch (error) {
    slog('startup spawn failed', (error as Error).message)
  }
}

/** 앱 종료 시 부른다 — 우리가 띄운 serve만 정리한다. 시스템 실행기는 건드리지 않는다. */
export function stopPortableOllama(): void {
  if (managedServe && !managedServe.killed) managedServe.kill()
  managedServe = null
}

/**
 * 실행기를 사용자 개입 없이 준비한다.
 *
 * 순서: 이미 떠 있나 → 깔린 걸 띄우면 되나 → **무설치본 설치(기본)** →
 * 공식 설치본(예비). 복구(repair)는 깨진 시스템 설치가 포트를 잡고 있으므로
 * 설치본 덮어쓰기부터 하고, 그것도 안 되면 시스템 실행기를 내리고 무설치본으로
 * 갈아탄다.
 *
 * Windows에서는 브라우저를 열지 않는다 — 실패해도 화면에 이유와 [다시 시도]가
 * 남는 편이, 링크를 열고 사용자에게 떠넘기는 것보다 낫다.
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
      detail: '브라우저에서 Ollama 설치 페이지를 열었습니다. 설치 후 [다시 시도]를 눌러 주세요.',
    }
  }

  slog('installOllama start', { repair: Boolean(options.repair) })

  if (!options.repair) {
    if (await ollamaAlive()) {
      slog('already alive')
      return ready('문서 분석 도구가 이미 준비돼 있습니다.')
    }
    // 깔려 있는데 안 떠 있을 뿐인 PC — 받을 것 없이 띄우기만 하면 된다.
    if (await spawnInstalledServe().catch(() => false)) {
      return ready('문서 분석 도구를 시작했습니다.')
    }
    if (await spawnPortableServe().catch(() => false)) {
      return ready('문서 분석 도구를 시작했습니다.')
    }
  } else {
    // 복구: 깨진 시스템 설치가 포트를 잡고 있다 — 덮어쓰는 것이 우선이다.
    try {
      return await installViaInstaller(onProgress, true)
    } catch (error) {
      slog('repair via installer failed', (error as Error).message)
      // 설치본으로 못 고치면 시스템 실행기를 내리고 무설치본으로 갈아탄다.
      await killSystemOllama()
    }
  }

  // 기본 경로: 무설치본. 관리자 권한 창도, 설치 프로그램의 변덕도 없다.
  let portableError = ''
  try {
    if (await installPortable(onProgress)) {
      slog('portable install ok')
      return ready('문서 분석 도구 준비가 끝났습니다.')
    }
    portableError = '준비는 됐지만 실행 확인에 실패했습니다'
    slog('portable spawned but not alive')
  } catch (error) {
    portableError = (error as Error).message
    slog('portable install failed', portableError)
  }

  // 예비: 공식 설치본.
  try {
    return await installViaInstaller(onProgress, Boolean(options.repair))
  } catch (error) {
    slog('installer fallback failed', (error as Error).message)
    return {
      phase: 'failed',
      percent: 0,
      detail:
        '문서 분석 도구를 자동으로 준비하지 못했습니다. 인터넷 연결을 확인하고 ' +
        `[다시 시도]를 눌러 주세요. (무설치본: ${portableError} ` +
        `/ 설치본: ${(error as Error).message})`,
    }
  }
}
