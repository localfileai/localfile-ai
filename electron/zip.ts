/**
 * zip 해제기 — 표준 라이브러리(fs·zlib)만 쓰는 자체 구현.
 *
 * 왜 직접 쓰는가: 실행기 무설치본(1.4GB zip)을 외부 도구로 풀다가 실제 PC에서
 * 두 번 실패했다.
 *   - PowerShell Expand-Archive: 일부 파일을 못 풀어도 exit 0으로 끝나는
 *     경우가 있었고(조용한 부분 실패), 오류를 내도 콘솔 인코딩(CP949) 때문에
 *     읽을 수 없는 글자로 깨져 도착했다.
 *   - tar.exe(bsdtar): 손상된 항목에서 "ZIP decompression failed (-3)"처럼
 *     원인 파악이 안 되는 실패를 냈다.
 * 앱의 첫 실행이 걸린 경로를 남의 도구의 동작에 걸어 둘 수 없다. 여기서는
 * 항목 하나하나를 우리가 읽고, 풀린 크기를 기록된 크기와 대조해 **손상을
 * 항목 이름과 함께 정확히 보고**한다.
 *
 * 지원 범위: 저장(0)·deflate(8) 압축 방식, ZIP64. 이 둘이면 통상적인 zip은
 * 전부 풀린다. 그 밖의 방식은 방식 번호와 함께 명확히 실패한다.
 *
 * 구현 근거: PKWARE APPNOTE의 zip 포맷 — 파일 끝의 EOCD 레코드에서 중앙
 * 디렉터리를 찾고, 중앙 디렉터리가 항목별 위치·크기·방식의 단일 진실이다.
 * (로컬 헤더의 크기 필드는 스트리밍 기록 시 0일 수 있어 믿지 않는다.)
 */
import { createReadStream, createWriteStream } from 'node:fs'
import { mkdir, open, stat } from 'node:fs/promises'
import path from 'node:path'
import { createInflateRaw } from 'node:zlib'
import { pipeline } from 'node:stream/promises'

const EOCD_SIG = 0x06054b50
const EOCD64_LOCATOR_SIG = 0x07064b50
const EOCD64_SIG = 0x06064b50
const CENTRAL_SIG = 0x02014b50
const LOCAL_SIG = 0x04034b50

type Entry = {
  name: string
  method: number
  crc32: number
  compressedSize: number
  uncompressedSize: number
  localHeaderOffset: number
}

// CRC32 — 손상 검출의 핵심이다. 압축이 안 되는 데이터(무작위에 가까운 DLL 등)는
// deflate가 "저장 블록"으로 담기 때문에, 바이트가 손상돼도 구조상 멀쩡히 풀리고
// 크기도 맞는다. 기록된 CRC와 대조해야만 잡힌다 — 테스트에서 실제로 확인했다.
// (Node zlib.crc32는 20.15부터라 직접 구현한다. 표준 다항식 0xEDB88320.)
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n += 1) {
    let value = n
    for (let k = 0; k < 8; k += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
    }
    table[n] = value
  }
  return table
})()

function crc32Update(crc: number, chunk: Buffer): number {
  let value = crc
  for (let i = 0; i < chunk.length; i += 1) {
    value = CRC_TABLE[(value ^ chunk[i]) & 0xff] ^ (value >>> 8)
  }
  return value
}

/** 파일 끝에서 중앙 디렉터리의 위치·크기를 찾는다 (ZIP64 포함). */
async function locateCentralDirectory(
  zipPath: string,
): Promise<{ offset: number; size: number; count: number }> {
  const fileSize = (await stat(zipPath)).size
  // EOCD는 파일 끝 22바이트 + 주석(최대 65535) 안에 있다. ZIP64 로케이터까지
  // 여유를 두고 끝부분을 통째로 읽는다.
  const tailSize = Math.min(fileSize, 22 + 65535 + 76)
  const handle = await open(zipPath, 'r')
  let tail: Buffer
  try {
    tail = Buffer.alloc(tailSize)
    await handle.read(tail, 0, tailSize, fileSize - tailSize)
  } finally {
    await handle.close()
  }

  let eocdAt = -1
  for (let i = tailSize - 22; i >= 0; i -= 1) {
    if (tail.readUInt32LE(i) === EOCD_SIG) {
      eocdAt = i
      break
    }
  }
  if (eocdAt < 0) throw new Error('zip 형식이 아닙니다 (끝 레코드 없음)')

  let count = tail.readUInt16LE(eocdAt + 10)
  let size = tail.readUInt32LE(eocdAt + 12)
  let offset = tail.readUInt32LE(eocdAt + 16)

  // 4GB를 넘거나 항목이 아주 많으면 값이 0xFFFF(FFFF)로 표시되고
  // 진짜 값은 ZIP64 레코드에 있다.
  if (offset === 0xffffffff || size === 0xffffffff || count === 0xffff) {
    const locatorAt = eocdAt - 20
    if (locatorAt < 0 || tail.readUInt32LE(locatorAt) !== EOCD64_LOCATOR_SIG) {
      throw new Error('ZIP64 위치 레코드가 없습니다')
    }
    const eocd64Offset = Number(tail.readBigUInt64LE(locatorAt + 8))
    const record = Buffer.alloc(56)
    const handle64 = await open(zipPath, 'r')
    try {
      await handle64.read(record, 0, 56, eocd64Offset)
    } finally {
      await handle64.close()
    }
    if (record.readUInt32LE(0) !== EOCD64_SIG) {
      throw new Error('ZIP64 끝 레코드가 손상됐습니다')
    }
    count = Number(record.readBigUInt64LE(32))
    size = Number(record.readBigUInt64LE(40))
    offset = Number(record.readBigUInt64LE(48))
  }

  return { offset, size, count }
}

/** 중앙 디렉터리에서 항목 목록을 읽는다. */
async function readEntries(zipPath: string): Promise<Entry[]> {
  const { offset, size, count } = await locateCentralDirectory(zipPath)
  const directory = Buffer.alloc(size)
  const handle = await open(zipPath, 'r')
  try {
    await handle.read(directory, 0, size, offset)
  } finally {
    await handle.close()
  }

  const entries: Entry[] = []
  let cursor = 0
  while (cursor + 46 <= size && entries.length < count) {
    if (directory.readUInt32LE(cursor) !== CENTRAL_SIG) {
      throw new Error(`중앙 디렉터리가 손상됐습니다 (항목 ${entries.length})`)
    }
    const method = directory.readUInt16LE(cursor + 10)
    const crc32 = directory.readUInt32LE(cursor + 16)
    let compressedSize: number = directory.readUInt32LE(cursor + 20)
    let uncompressedSize: number = directory.readUInt32LE(cursor + 24)
    const nameLength = directory.readUInt16LE(cursor + 28)
    const extraLength = directory.readUInt16LE(cursor + 30)
    const commentLength = directory.readUInt16LE(cursor + 32)
    let localHeaderOffset: number = directory.readUInt32LE(cursor + 42)
    const name = directory
      .subarray(cursor + 46, cursor + 46 + nameLength)
      .toString('utf8')

    // 32비트로 못 담는 값은 ZIP64 확장 필드(id 0x0001)에 있다.
    // 필드는 "넘친 값만, 이 순서대로(원본크기·압축크기·오프셋)" 담긴다.
    if (compressedSize === 0xffffffff || uncompressedSize === 0xffffffff
        || localHeaderOffset === 0xffffffff) {
      let extraCursor = cursor + 46 + nameLength
      const extraEnd = extraCursor + extraLength
      while (extraCursor + 4 <= extraEnd) {
        const id = directory.readUInt16LE(extraCursor)
        const dataSize = directory.readUInt16LE(extraCursor + 2)
        if (id === 0x0001) {
          let field = extraCursor + 4
          if (uncompressedSize === 0xffffffff) {
            uncompressedSize = Number(directory.readBigUInt64LE(field)); field += 8
          }
          if (compressedSize === 0xffffffff) {
            compressedSize = Number(directory.readBigUInt64LE(field)); field += 8
          }
          if (localHeaderOffset === 0xffffffff) {
            localHeaderOffset = Number(directory.readBigUInt64LE(field)); field += 8
          }
          break
        }
        extraCursor += 4 + dataSize
      }
    }

    entries.push({ name, method, crc32, compressedSize, uncompressedSize, localHeaderOffset })
    cursor += 46 + nameLength + extraLength + commentLength
  }
  return entries
}

/** zip 경로 탈출(zip-slip)을 막는다 — 악의적 zip이 dest 밖에 파일을 쓰지 못하게. */
function resolveSafe(destDir: string, entryName: string): string {
  const normalized = entryName.replace(/\\/g, '/')
  const target = path.resolve(destDir, normalized)
  if (target !== destDir && !target.startsWith(destDir + path.sep)) {
    throw new Error(`zip 항목의 경로가 대상 폴더를 벗어납니다: ${entryName}`)
  }
  return target
}

/** 풀린 바이트 수를 세는 변환 스트림 없이, 쓰기 스트림에서 직접 센다. */
async function extractOne(
  zipPath: string,
  entry: Entry,
  destDir: string,
): Promise<void> {
  const target = resolveSafe(destDir, entry.name)

  if (entry.name.endsWith('/')) {
    await mkdir(target, { recursive: true })
    return
  }
  await mkdir(path.dirname(target), { recursive: true })

  // 데이터의 실제 시작점은 로컬 헤더 뒤다. 로컬 헤더의 이름·확장 길이는
  // 중앙 디렉터리와 다를 수 있어 반드시 로컬 헤더에서 다시 읽는다.
  const header = Buffer.alloc(30)
  const handle = await open(zipPath, 'r')
  try {
    await handle.read(header, 0, 30, entry.localHeaderOffset)
  } finally {
    await handle.close()
  }
  if (header.readUInt32LE(0) !== LOCAL_SIG) {
    throw new Error(`${entry.name}: 로컬 헤더가 손상됐습니다`)
  }
  const dataStart = entry.localHeaderOffset + 30
    + header.readUInt16LE(26) + header.readUInt16LE(28)

  // 빈 파일은 데이터가 0바이트라 스트림 범위를 만들 수 없다 — 그냥 빈 파일을 쓴다.
  if (entry.compressedSize === 0) {
    if (entry.uncompressedSize !== 0) {
      throw new Error(`${entry.name}: 크기 기록이 모순됩니다`)
    }
    await (await open(target, 'w')).close()
    return
  }

  const source = createReadStream(zipPath, {
    start: dataStart,
    end: dataStart + entry.compressedSize - 1,
  })
  const sink = createWriteStream(target)

  let written = 0
  let crc = 0xffffffff
  const count = (chunk: Buffer) => {
    written += chunk.length
    crc = crc32Update(crc, chunk)
  }

  if (entry.method === 8) {
    const inflate = createInflateRaw()
    inflate.on('data', count)
    try {
      await pipeline(source, inflate, sink)
    } catch (error) {
      throw new Error(`${entry.name}: 압축이 손상됐습니다 (${(error as Error).message})`)
    }
  } else if (entry.method === 0) {
    source.on('data', (chunk) => count(chunk as Buffer))
    await pipeline(source, sink)
  } else {
    sink.destroy()
    throw new Error(`${entry.name}: 지원하지 않는 압축 방식(${entry.method})입니다`)
  }

  // 크기와 CRC가 기록과 다르면 그 항목이 손상된 것이다. 조용히 넘어가면
  // "성공했는데 파일이 이상한" 상태가 된다 — 반드시 여기서 멈춘다.
  if (written !== entry.uncompressedSize) {
    throw new Error(
      `${entry.name}: 풀린 크기가 다릅니다 (${written} ≠ ${entry.uncompressedSize})`)
  }
  if ((crc ^ 0xffffffff) >>> 0 !== entry.crc32) {
    throw new Error(`${entry.name}: 내용이 손상됐습니다 (CRC 불일치)`)
  }
}

/**
 * zip을 destDir에 푼다. 항목 수를 돌려준다.
 *
 * onProgress는 0~100 진행률로 불린다 (압축 바이트 기준).
 */
export async function extractZip(
  zipPath: string,
  destDir: string,
  onProgress?: (percent: number) => void,
): Promise<number> {
  const resolvedDest = path.resolve(destDir)
  await mkdir(resolvedDest, { recursive: true })

  const entries = await readEntries(zipPath)
  if (entries.length === 0) throw new Error('zip이 비어 있습니다')

  const totalCompressed = entries.reduce((sum, e) => sum + e.compressedSize, 0) || 1
  let doneCompressed = 0

  for (const entry of entries) {
    await extractOne(zipPath, entry, resolvedDest)
    doneCompressed += entry.compressedSize
    onProgress?.(Math.min(100, (doneCompressed / totalCompressed) * 100))
  }
  return entries.length
}
