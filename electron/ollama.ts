/**
 * Ollama(모델 실행기) 설치 도우미 — 5주차 배포본.
 *
 * 모델을 받는 것은 백엔드가 하지만(`POST /setup/models`), **Ollama 자체가
 * 없으면 받을 곳도 없다.** 설치는 관리자 권한이 필요한 데스크톱 작업이라
 * 메인 프로세스가 맡는다: 공식 설치본을 내려받아 실행까지 걸어 준다.
 *
 * 어떤 이유로든 자동 설치가 안 되면 조용히 실패하지 않고 공식 다운로드
 * 페이지를 브라우저로 열어 준다 — 사용자가 막히지 않는 것이 우선이다.
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

export type InstallProgress = {
  phase: 'downloading' | 'installing' | 'ready' | 'opened-page' | 'failed'
  percent: number
  detail: string
}

/** Ollama가 응답하는지. 설치가 실제로 끝났는지 판단하는 유일한 기준이다. */
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

/**
 * Ollama를 설치한다. Windows는 설치본을 받아 실행하고,
 * 그 외 OS(또는 실패 시)는 공식 다운로드 페이지를 연다.
 */
export async function installOllama(
  onProgress: (progress: InstallProgress) => void,
): Promise<InstallProgress> {
  if (process.platform !== 'win32') {
    await shell.openExternal(DOWNLOAD_PAGE)
    return {
      phase: 'opened-page',
      percent: 100,
      detail: '브라우저에서 Ollama 설치 페이지를 열었습니다. 설치 후 [다시 확인]을 눌러 주세요.',
    }
  }

  if (await ollamaAlive()) {
    return { phase: 'ready', percent: 100, detail: 'Ollama가 이미 실행 중입니다.' }
  }

  const target = path.join(app.getPath('temp'), 'OllamaSetup.exe')
  try {
    await downloadInstaller(target, onProgress)

    onProgress({ phase: 'installing', percent: 100, detail: 'Ollama를 설치하는 중입니다…' })

    // 무인 설치. 사용자가 설치 마법사를 클릭해 넘길 필요가 없다.
    // (설치 프로그램이 이 옵션을 무시하면 창이 뜨는데, 그때는 사용자가
    //  직접 넘기면 되고 아래 대기 로직이 완료를 알아서 감지한다.)
    await new Promise<void>((resolve) => {
      execFile(target, ['/VERYSILENT', '/NORESTART'], () => resolve())
    })

    onProgress({ phase: 'installing', percent: 100, detail: '설치를 마무리하는 중입니다…' })
    if (await waitUntilAlive()) {
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
        `자동 설치에 실패해 다운로드 페이지를 열었습니다 (${(error as Error).message}). ` +
        '설치 후 [다시 확인]을 눌러 주세요.',
    }
  }
}
