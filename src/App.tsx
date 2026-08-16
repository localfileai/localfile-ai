import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import MainView from './components/MainView'
import OrganizeView from './components/OrganizedView'
import AllFilesView from './components/AllFilesView'
import {
  analyzeFolder,
  type CurrentFileItem,
  type FailedFileInfo,
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

function App() {
  const [currentMenu, setCurrentMenu] = useState<Menu>('search')

  // 선택한 폴더를 분석해 받은 추천 데이터
  const [renameList, setRenameList] = useState<RenameRecommendation[]>([])
  const [structureList, setStructureList] = useState<StructureRecommendation[]>([])
  const [currentFiles, setCurrentFiles] = useState<CurrentFileItem[]>([])
  const [totalFiles, setTotalFiles] = useState(0)
  // 이번에 실제 분석한 수와 실패 목록 — 정리 화면이 "전체 N개 중 M개 분석,
  // 그중 K개는 왜 안 됐는지"를 말할 수 있어야 한다.
  const [analyzedCount, setAnalyzedCount] = useState(0)
  const [failedFiles, setFailedFiles] = useState<FailedFileInfo[]>([])

  // FE1: OS에서 인식한 경로
  const [selectedPath, setSelectedPath] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [dropError, setDropError] = useState('')
  // dragenter/dragleave는 자식 요소를 넘나들 때마다 발생합니다.
  // 깊이를 세지 않으면 오버레이가 깜빡이고 창을 벗어난 시점을 알 수 없습니다.
  const dragDepth = useRef(0)

  // 어떤 폴더를 분석해 둔 상태인지. 같은 폴더를 다시 분석하지 않기 위한 표식.
  const [analyzedPath, setAnalyzedPath] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState('')

  // 폴더를 고르면 실제 AI 추천(POST /organize)을 받는다.
  // 폴더를 고르기 전에는 아무것도 보여 주지 않는다 — 예전에는 데모용 Mock 추천을
  // 채웠는데, 실제 앱에서는 있지도 않은 파일이 추천 목록에 뜨는 셈이라 혼란스럽다.
  const loadOrganizeData = useCallback(async () => {
    if (!selectedPath) {
      setRenameList([])
      setStructureList([])
      setCurrentFiles([])
      setTotalFiles(0)
      setAnalyzedCount(0)
      setFailedFiles([])
      setAnalyzedPath('')
      setAnalyzeError('')
      return
    }

    setIsAnalyzing(true)
    setAnalyzeError('')
    try {
      const data = await analyzeFolder(selectedPath)
      setRenameList(data.renameList)
      setStructureList(data.structureList)
      setCurrentFiles(data.currentFiles)
      setTotalFiles(data.totalFilesCount)
      setAnalyzedCount(data.analyzedCount)
      setFailedFiles(data.failedFiles)
      setAnalyzedPath(selectedPath)
    } catch (error) {
      // 조용히 비워 두면 "기능이 없는 것"처럼 보인다. 이유를 화면까지 올린다.
      setAnalyzeError((error as Error).message)
    } finally {
      setIsAnalyzing(false)
    }
  }, [selectedPath])

  // 정리 추천은 **그 화면을 열었을 때만** 계산한다.
  //
  // 폴더를 고르자마자 돌리면, 검색 준비(색인)와 LLM 분석이 동시에 Ollama를 두고
  // 경쟁한다. Ollama는 요청을 하나씩 처리하므로 둘 다 몇 배로 느려지고,
  // 사용자에게는 "아무것도 안 되는" 상태로 보인다.
  useEffect(() => {
    if (!selectedPath) {
      void loadOrganizeData()
      return
    }
    const needsAnalysis = currentMenu === 'organize' || currentMenu === 'rename'
      || currentMenu === 'files'
    if (needsAnalysis && analyzedPath !== selectedPath) void loadOrganizeData()
  }, [selectedPath, currentMenu, analyzedPath, loadOrganizeData])

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
  // 폴더를 안 골랐으면 빈 문자열 — 사이드바가 "아직 고르지 않음"을 보여 준다.
  const folderName = selectedPath.split(/[\\/]/).filter(Boolean).at(-1) || ''

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="relative flex h-screen bg-[#F8F9FA] dark:bg-[#0d0d13] text-gray-800 dark:text-gray-100 font-sans antialiased overflow-hidden"
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

        {/* 화면을 껐다 켜지 않고 감추기만 한다.
            메뉴를 옮길 때마다 다시 만들면 검색 화면이 폴더를 처음부터 다시
            훑고 색인을 또 걸며, 찾아 둔 결과도 사라진다. */}
        <main className="flex-1 overflow-y-auto flex flex-col">
          <div className={currentMenu === 'search' ? 'flex flex-1 flex-col' : 'hidden'}>
            <MainView selectedPath={selectedPath} />
          </div>

          <div
            className={
              currentMenu === 'rename' || currentMenu === 'organize'
                ? 'flex flex-1 flex-col'
                : 'hidden'
            }
          >
            <OrganizeView
              mode={currentMenu === 'rename' ? 'rename' : 'structure'}
              renameList={renameList}
              setRenameList={setRenameList}
              structureList={structureList}
              setStructureList={setStructureList}
              currentFiles={currentFiles}
              setCurrentFiles={setCurrentFiles}
              totalFiles={totalFiles}
              analyzedCount={analyzedCount}
              failedFiles={failedFiles}
              onRefreshData={loadOrganizeData}
              selectedPath={selectedPath}
              isAnalyzing={isAnalyzing}
              analyzeError={analyzeError}
            />
          </div>

          <div className={currentMenu === 'files' ? 'flex flex-1 flex-col' : 'hidden'}>
            <AllFilesView currentFiles={currentFiles} />
          </div>
        </main>
      </div>

      {/* 드롭 실패를 조용히 넘기지 않고 알린다 */}
      {dropError && (
        <div className="absolute bottom-6 left-1/2 z-50 w-[34rem] -translate-x-1/2 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/15 px-4 py-3 shadow-lg">
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
          <div className="rounded-2xl border-2 border-dashed border-indigo-400 bg-white/90 dark:bg-[#16161e]/90 px-8 py-6 text-center shadow-lg">
            <div className="text-sm font-bold text-indigo-600">여기에 놓으세요</div>
            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              폴더나 파일을 놓으면 분석 대상 경로로 인식합니다.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
