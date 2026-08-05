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
import { createWriteStream } from 'node:fs'
import { unlink } from 'node:fs/promises'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const DOWNLOAD_PAGE = 'https://ollama.com/download'
const WINDOWS_INSTALLER = 'https://ollama.com/download/OllamaSetup.exe'

export type InstallProgress = {
  phase: 'downloading' | 'launching' | 'opened-page' | 'failed'
  percent: number
  detail: string
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

  const target = path.join(app.getPath('temp'), 'OllamaSetup.exe')
  try {
    await downloadInstaller(target, onProgress)
    onProgress({ phase: 'launching', percent: 100, detail: '설치 프로그램을 실행합니다…' })

    // 설치 마법사를 띄운다(UAC 동의는 사용자가 한다). 설치가 끝나면
    // 사용자가 [다시 확인]을 눌러 상태를 새로 읽는다.
    const error = await shell.openPath(target)
    if (error) throw new Error(error)

    return {
      phase: 'launching',
      percent: 100,
      detail: 'Ollama 설치 프로그램이 열렸습니다. 설치를 마친 뒤 [다시 확인]을 눌러 주세요.',
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
