/**
 * Ollama(모델 실행기) 설치·복구 도우미 — 5주차 배포본.
 *
 * 모델을 받는 것은 백엔드가 하지만(`POST /setup/models`), **Ollama 자체가
 * 없으면 받을 곳도 없다.** 설치는 관리자 권한이 필요한 데스크톱 작업이라
 * 메인 프로세스가 맡는다: 공식 설치본을 내려받아 실행까지 걸어 준다.
 *
 * 6주차 보강 — **떠 있다고 멀쩡한 것이 아니다.** 남의 PC에서 이런 상태를 봤다:
 *
 *     error starting llama-server: llama-server binary not found
 *     (checked: ...\Ollama\lib\ollama\llama-server.exe, ...)
 *
 * Ollama는 v0.32.5로 응답하고 `ollama pull`도 성공하는데, 정작 모델을 돌리는
 * 실행 파일이 설치본에서 빠져 있었다. 예전 코드는 "응답하면 끝"으로 보고
 * 그냥 돌아가 버려서, 사용자는 어떤 버튼을 눌러도 아무 일도 안 일어나는
 * 화면만 봤다. 그래서 `repair` 모드를 뒀다 — 떠 있어도 다시 깔아 덮어쓴다.
 *
 * 자동 설치가 정말 안 될 때만 마지막 수단으로 공식 다운로드 페이지를 연다.
 */
import { shell, app } from 'electron'
import { execFile } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import { unlink } from 'node:fs/promises'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const DOWNLOAD_PAGE = 'https://ollama.com/download'
const WINDOWS_INSTALLER = 'https://ollama.com/download/OllamaSetup.exe'

/** 내려받다 끊기는 일이 잦다. 페이지를 열어 사용자에게 떠넘기기 전에 다시 해 본다. */
const DOWNLOAD_ATTEMPTS = 3

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

async function downloadInstaller(
  target: string,
  onProgress: (progress: InstallProgress) => void,
): Promise<void> {
  const response = await fetch(WINDOWS_INSTALLER)
  if (!response.ok || !response.body) {
    throw new Error(`설치본을 받을 수 없습니다 (HTTP ${response.status})`)
  }

  const total = Number(response.headers.get('content-length') || 0)
  let received = 0

  const source = Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0])
  source.on('data', (chunk: Buffer) => {
    received += chunk.length
    onProgress({
      phase: 'downloading',
      percent: total ? (received / total) * 100 : 0,
      detail: 'Ollama 설치본을 내려받는 중입니다…',
    })
  })

  await pipeline(source, createWriteStream(target))
}

/** 몇 번 다시 시도한다. 마지막 실패는 그대로 올려 호출부가 판단하게 한다. */
async function downloadWithRetry(
  target: string,
  onProgress: (progress: InstallProgress) => void,
): Promise<void> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      await downloadInstaller(target, onProgress)
      return
    } catch (error) {
      await unlink(target).catch(() => undefined)
      if (attempt >= DOWNLOAD_ATTEMPTS) throw error
      onProgress({
        phase: 'downloading',
        percent: 0,
        detail: `내려받기에 실패해 다시 시도합니다 (${attempt}/${DOWNLOAD_ATTEMPTS})…`,
      })
      await new Promise((resolve) => setTimeout(resolve, 2000 * attempt))
    }
  }
}

/** 설치 프로그램을 무인 모드로 실행한다. 두 계열의 옵션을 순서대로 시도한다. */
async function runInstaller(target: string): Promise<void> {
  // Ollama 설치본은 Inno Setup 계열이라 /VERYSILENT를 받는다. 배포 방식이
  // 바뀌어 이 옵션을 모르면 창이 뜨는데, 그때는 사용자가 [다음]만 누르면 되고
  // 아래 대기 로직이 완료를 알아서 감지한다.
  await new Promise<void>((resolve) => {
    execFile(target, ['/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES'], () => resolve())
  })
}

/**
 * Ollama를 설치한다. Windows는 설치본을 받아 실행하고,
 * 그 외 OS(또는 자동 설치가 끝내 실패했을 때)는 공식 다운로드 페이지를 연다.
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

  if (!options.repair && (await ollamaAlive())) {
    return { phase: 'ready', percent: 100, detail: 'Ollama가 이미 실행 중입니다.' }
  }

  const target = path.join(app.getPath('temp'), 'OllamaSetup.exe')
  try {
    await downloadWithRetry(target, onProgress)

    onProgress({
      phase: 'installing',
      percent: 100,
      detail: options.repair
        ? 'Ollama를 다시 설치하는 중입니다… (몇 분 걸릴 수 있습니다)'
        : 'Ollama를 설치하는 중입니다…',
    })
    await runInstaller(target)

    onProgress({ phase: 'installing', percent: 100, detail: '설치를 마무리하는 중입니다…' })
    const alive = await waitUntilAlive()
    await unlink(target).catch(() => undefined)

    if (alive) {
      return { phase: 'ready', percent: 100, detail: 'Ollama 준비가 끝났습니다.' }
    }
    return {
      phase: 'failed',
      percent: 100,
      detail: 'Ollama가 설치됐지만 아직 응답하지 않습니다. 잠시 뒤 [다시 확인]을 눌러 주세요.',
    }
  } catch (error) {
    await unlink(target).catch(() => undefined)
    await shell.openExternal(DOWNLOAD_PAGE)
    return {
      phase: 'opened-page',
      percent: 0,
      detail:
        `자동 설치를 ${DOWNLOAD_ATTEMPTS}번 시도했지만 실패해 다운로드 페이지를 열었습니다 ` +
        `(${(error as Error).message}). 설치 후 [다시 확인]을 눌러 주세요.`,
    }
  }
}
