/**
 * 설치·기동 과정 파일 로그.
 *
 * 왜 필요한가: 배포본의 문제는 남의 PC에서 난다. 지금까지는 사용자가 보낸
 * 스크린샷의 오류 문구 한 줄로 원인을 역추적했는데, 화면에 담기는 정보에는
 * 한계가 있다 (어느 URL이 실패했는지, 설치 파일이 몇 바이트였는지, 실행기가
 * 어떤 코드로 죽었는지는 화면에 못 싣는다). 준비 화면이 실패하면 이 파일의
 * 경로를 보여 주고, 사용자가 내용을 복사해 주면 그것이 곧 진단이 된다.
 */
import { app } from 'electron'
import { appendFileSync, renameSync, statSync } from 'node:fs'
import path from 'node:path'

export function setupLogPath(): string {
  return path.join(app.getPath('userData'), 'setup.log')
}

/** 한 줄 기록한다. 로그가 실패해도 기능을 막지 않는다. */
export function slog(...parts: unknown[]): void {
  try {
    const file = setupLogPath()
    // 무한히 크지 않게 — 512KB를 넘으면 한 세대 물려 둔다.
    try {
      if (statSync(file).size > 512 * 1024) renameSync(file, `${file}.old`)
    } catch {
      // 파일이 아직 없음 — 정상
    }
    const line = parts
      .map((part) => (typeof part === 'string' ? part : JSON.stringify(part)))
      .join(' ')
    appendFileSync(file, `[${new Date().toISOString()}] ${line}\n`)
  } catch {
    // 로그를 못 쓴다고 설치가 멈추면 안 된다
  }
}
