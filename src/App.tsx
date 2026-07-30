import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import MainView from './components/MainView'
import OrganizeView from './components/OrganizedView'
import AllFilesView from './components/AllFilesView'
import {
  getRenameRecommendations,
  getStructureRecommendations,
  type CurrentFileItem,
  type RenameRecommendation,
  type StructureRecommendation,
} from './api/organizeApi'
import type { Menu } from './types'

// 1주차 통합 지점.
//   FE2: Sidebar / Header / MainView / OrganizeView / AllFilesView 레이아웃과
//        BE2 Mock API(/mock/*) 데이터 바인딩
//   FE1: OS 네이티브 폴더 선택(IPC)과 Drag & Drop 경로 인식
// 두 사람의 결과물이 만나는 곳은 selectedPath 하나입니다.
// FE1이 경로를 만들고, FE2의 Header/Sidebar가 그 경로를 화면에 보여줍니다.

const DEFAULT_FOLDER_NAME = 'Documents'

function App() {
  const [currentMenu, setCurrentMenu] = useState<Menu>('search')

  // FE2: Mock API에서 받아오는 추천 데이터
  const [renameList, setRenameList] = useState<RenameRecommendation[]>([])
  const [structureList, setStructureList] = useState<StructureRecommendation[]>([])
  const [currentFiles, setCurrentFiles] = useState<CurrentFileItem[]>([])
  const [totalFiles, setTotalFiles] = useState(0)

  // FE1: OS에서 인식한 경로
  const [selectedPath, setSelectedPath] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [dropError, setDropError] = useState('')
  // dragenter/dragleave는 자식 요소를 넘나들 때마다 발생합니다.
  // 깊이를 세지 않으면 오버레이가 깜빡이고 창을 벗어난 시점을 알 수 없습니다.
  const dragDepth = useRef(0)

  const loadOrganizeData = useCallback(async () => {
    try {
      const [renameData, structureData] = await Promise.all([
        getRenameRecommendations(),
        getStructureRecommendations(),
      ])

      setRenameList(renameData || [])
      setStructureList(structureData.recommendations || [])
      setCurrentFiles(structureData.currentFiles || [])
      setTotalFiles(structureData.totalFilesCount || 0)
    } catch (error) {
      console.error('초기 데이터 로딩 에러:', error)
    }
  }, [])

  useEffect(() => {
    loadOrganizeData()
  }, [loadOrganizeData])

  // FE1: 실제 OS 폴더 선택 창을 띄우고 경로를 받는다. 취소하면 null.
  const handleSelectFolder = async () => {
    setDropError('')
    const path = await window.api.selectFolder()
    if (path) setSelectedPath(path)
  }

  // dragenter에서도 preventDefault를 해야 Chromium이 이 요소를 유효한 드롭 대상으로 봅니다.
  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepth.current += 1
    setIsDragging(true)
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    // 이걸 빼면 브라우저 기본 동작(파일로 페이지 이동)이 실행되고 drop이 오지 않습니다.
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    if (!isDragging) setIsDragging(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    // 자식 사이를 이동하는 중에는 끄지 않습니다. 창을 완전히 벗어났을 때만 끕니다.
    if (dragDepth.current === 0) setIsDragging(false)
  }

  // FE1: 드롭된 항목에서 로컬 실제 경로를 뽑아 선택 경로로 삼는다.
  // FE2 레이아웃에는 경로 목록을 놓을 자리가 없어 첫 항목만 반영합니다.
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragDepth.current = 0
    setIsDragging(false)
    setDropError('')

    const files = Array.from(event.dataTransfer.files)
    if (files.length === 0) {
      setDropError('드롭된 항목에서 파일 정보를 읽지 못했습니다. 탐색기에서 다시 끌어다 놓아 주세요.')
      return
    }

    // 경로 추출이 실패하면 빈 문자열이 옵니다. 조용히 넘기지 않고 사용자에게 알립니다.
    const paths: string[] = []
    for (const file of files) {
      try {
        const path = window.api.getPathForFile(file)
        if (path) paths.push(path)
      } catch (error) {
        console.error('경로 추출 실패:', file.name, error)
      }
    }

    if (paths.length === 0) {
      setDropError(
        `드롭한 "${files[0].name}" 의 실제 경로를 확인할 수 없습니다. ` +
          '개발자 도구 콘솔(Ctrl+Shift+I)의 [preload] 로그를 확인해 주세요.',
      )
      return
    }

    setSelectedPath(paths[0])
    if (paths.length > 1) {
      console.log(`드롭된 항목 ${paths.length}개 중 첫 번째만 사용합니다.`, paths)
    }
  }

  const badgeCount = renameList.length + structureList.length
  const folderName =
    selectedPath.split(/[\\/]/).filter(Boolean).at(-1) || DEFAULT_FOLDER_NAME

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="relative flex h-screen bg-[#F8F9FA] text-gray-800 font-sans antialiased overflow-hidden"
    >
      <Sidebar
        currentMenu={currentMenu}
        onMenuChange={setCurrentMenu}
        badgeCount={badgeCount}
        totalFiles={totalFiles}
        folderName={folderName}
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header
          currentMenu={currentMenu}
          selectedPath={selectedPath}
          onSelectFolder={handleSelectFolder}
        />

        <main className="flex-1 overflow-y-auto flex flex-col">
          {currentMenu === 'search' && <MainView selectedPath={selectedPath} />}

          {currentMenu === 'organize' && (
            <OrganizeView
              renameList={renameList}
              setRenameList={setRenameList}
              structureList={structureList}
              setStructureList={setStructureList}
              currentFiles={currentFiles}
              setCurrentFiles={setCurrentFiles}
              totalFiles={totalFiles}
              onRefreshData={loadOrganizeData}
            />
          )}

          {currentMenu === 'files' && <AllFilesView currentFiles={currentFiles} />}
        </main>
      </div>

      {/* 드롭 실패를 조용히 넘기지 않고 알린다 */}
      {dropError && (
        <div className="absolute bottom-6 left-1/2 z-50 w-[34rem] -translate-x-1/2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 shadow-lg">
          <div className="flex items-start justify-between gap-3">
            <div className="text-[11px] leading-relaxed text-red-700">{dropError}</div>
            <button
              onClick={() => setDropError('')}
              className="shrink-0 px-1 text-xs font-bold text-red-400 hover:text-red-600"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* FE1: 드래그 중임을 알리는 오버레이 */}
      {isDragging && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center bg-indigo-500/10 backdrop-blur-[1px]">
          <div className="rounded-2xl border-2 border-dashed border-indigo-400 bg-white/90 px-8 py-6 text-center shadow-lg">
            <div className="text-sm font-bold text-indigo-600">여기에 놓으세요</div>
            <div className="mt-1 text-[11px] text-gray-500">
              폴더나 파일을 놓으면 분석 대상 경로로 인식합니다.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
