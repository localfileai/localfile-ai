import React, { useState, useEffect, useMemo } from 'react';
import {
  RenameRecommendation,
  StructureRecommendation,
  CurrentFileItem,
  FailedFileInfo,
  ApplyHistoryEntry,
  applyRenameRecommendations,
  applyStructureRecommendations,
  getApplyHistory,
  undoApply
} from '../api/organizeApi';

interface OrganizeViewProps {
  renameList?: RenameRecommendation[];
  setRenameList?: React.Dispatch<React.SetStateAction<RenameRecommendation[]>>;
  structureList?: StructureRecommendation[];
  setStructureList?: React.Dispatch<React.SetStateAction<StructureRecommendation[]>>;
  currentFiles?: CurrentFileItem[];
  setCurrentFiles?: React.Dispatch<React.SetStateAction<CurrentFileItem[]>>;
  totalFiles?: number;
  /** 이번에 실제 분석한 수 (추천+실패). totalFiles보다 작으면 상한에 걸린 것 */
  analyzedCount?: number;
  /** 분석하지 못한 파일과 이유 — 숨기지 않고 화면에 보여 준다 */
  failedFiles?: FailedFileInfo[];
  onRefreshData?: () => void;
  /** 남은 파일의 다음 묶음을 이어서 분석한다 (처리 상한 20개 초과 폴더용) */
  onAnalyzeMore?: () => void;
  /** 고른 폴더. 없으면 분석할 대상이 없다는 안내를 띄운다 */
  selectedPath?: string;
  /** 추천을 계산하는 중 (파일당 몇 초씩 걸린다) */
  isAnalyzing?: boolean;
  /** 계산이 실패한 이유 */
  analyzeError?: string;
  /** 이 화면이 다루는 것. 사이드바 메뉴가 정한다 */
  mode?: 'rename' | 'structure';
}

// "20260824-150233-…" 형태의 이력 시각을 사람이 읽는 형태로.
function formatAppliedAt(appliedAt: string): string {
  const parsed = new Date(appliedAt);
  if (Number.isNaN(parsed.getTime())) return appliedAt;
  return `${parsed.getMonth() + 1}/${parsed.getDate()} ${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`;
}

// 💡 백엔드 동적 트리를 위한 노드 타입
interface FileNode {
  name: string;
  isFolder: boolean;
  fileData?: StructureRecommendation;
  children: { [key: string]: FileNode };
  fileCount: number;
}

// 💡 1. 백엔드 데이터(StructureRecommendation[])를 동적 트로그 구조로 변환하는 함수
function buildTreeFromList(
  items: StructureRecommendation[],
  pathKey: 'currentFolder' | 'targetFolder'
): FileNode {
  const root: FileNode = {
    name: 'Documents',
    isFolder: true,
    children: {},
    fileCount: 0,
  };

  items.forEach((item) => {
    const fullPath = item[pathKey] || '';
    // 경로 정리 (Documents/ 제거 후 split)
    const cleanPath = fullPath.replace(/^Documents\/?/, '');
    const parts = cleanPath ? cleanPath.split('/').filter(Boolean) : [];

    let current = root;
    current.fileCount += 1;

    // 폴더 경로 탐색 및 생성
    parts.forEach((part) => {
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          isFolder: true,
          children: {},
          fileCount: 0,
        };
      }
      current = current.children[part];
      current.fileCount += 1;
    });

    // 파일 노드 추가
    current.children[item.fileName] = {
      name: item.fileName,
      isFolder: false,
      fileData: item,
      children: {},
      fileCount: 1,
    };
  });

  return root;
}

// 💡 2. 동적으로 다계층 트리를 그리는 재귀 컴포넌트
function DynamicTreeNode({ 
  node, 
  selectedMoveIds, 
  isTargetTree = false 
}: { 
  node: FileNode; 
  selectedMoveIds: string[]; 
  isTargetTree?: boolean;
}) {
  const childKeys = Object.keys(node.children);

  return (
    <div className="space-y-1">
      {/* 📁 폴더인 경우 */}
      {node.isFolder ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px] text-gray-800 dark:text-gray-100">
            <div className="flex items-center gap-1.5">
              <span>📁</span>
              <span>{node.name}</span>
            </div>
            <span className="text-[10px] bg-gray-100 dark:bg-white/10 text-gray-400 dark:text-gray-500 px-1.5 rounded-full font-semibold">
              {node.fileCount}
            </span>
          </div>

          {/* 자식 노드가 있으면 들여쓰기 계층선(border-l)과 함께 재귀 렌더링 */}
          {childKeys.length > 0 && (
            <div className="pl-3 border-l border-gray-100 dark:border-gray-700/70 ml-1.5 space-y-1 pt-0.5">
              {childKeys.map((key) => (
                <DynamicTreeNode
                  key={key}
                  node={node.children[key]}
                  selectedMoveIds={selectedMoveIds}
                  isTargetTree={isTargetTree}
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        /* 📄 파일인 경우 */
        <div className="py-0.5">
          {node.fileData && (
            <>
              {/* [현재 폴더 구조 트리일 때] */}
              {!isTargetTree && (
                <div
                  className={`flex items-center justify-between py-1.5 px-2 rounded-xl transition ${
                    selectedMoveIds.includes(node.fileData.id)
                      ? 'bg-rose-50/70 border border-rose-100/80'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <button
                    onClick={() => void window.api?.revealFile?.(node.fileData?.path ?? '')}
                    title="탐색기에서 이 파일 보기"
                    className={`text-left text-[11px] truncate pr-2 cursor-pointer hover:underline ${
                      selectedMoveIds.includes(node.fileData.id)
                        ? 'text-rose-600'
                        : 'text-gray-700 dark:text-gray-200'
                    }`}
                  >
                    📄 {node.name}
                  </button>
                  {selectedMoveIds.includes(node.fileData.id) && (
                    <span className="text-[9px] bg-rose-100 text-rose-600 font-bold px-1.5 py-0.5 rounded shrink-0">
                      이동 예정
                    </span>
                  )}
                </div>
              )}

              {/* [적용 후 폴더 구조 트리일 때] */}
              {isTargetTree && selectedMoveIds.includes(node.fileData.id) && (
                <div className="flex items-center justify-between py-1.5 px-2 rounded-xl bg-emerald-50/70 border border-emerald-100/80">
                  <button
                    onClick={() => void window.api?.revealFile?.(node.fileData?.path ?? '')}
                    title="탐색기에서 이 파일 보기"
                    className="text-left text-[11px] text-emerald-800 dark:text-emerald-300 truncate pr-2 cursor-pointer hover:underline"
                  >
                    📄 {node.name}
                  </button>
                  <span className="text-[9px] bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 font-bold px-1.5 py-0.5 rounded shrink-0">
                    새 위치
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function OrganizeView({
  renameList: initialRenameList = [],
  setRenameList: setParentRenameList,
  structureList: initialStructureList = [],
  setStructureList: setParentStructureList,
  // currentFiles는 이 컴포넌트에서 쓰지 않습니다(전체 목록은 AllFilesView 담당).
  // props 타입에는 남겨 두어 App이 그대로 넘길 수 있게 하고, 구조 분해에서만 뺐습니다.
  setCurrentFiles,
  totalFiles = 0,
  analyzedCount,
  failedFiles = [],
  onRefreshData,
  onAnalyzeMore,
  selectedPath = '',
  isAnalyzing = false,
  analyzeError = '',
  mode = 'structure',
}: OrganizeViewProps) {
  // 예전에는 한 화면 안에서 탭으로 갈랐지만, 두 기능은 하는 일이 달라
  // 사이드바에서 각각 고르게 바꿨다. 여기서는 받은 모드만 그린다.
  const activeTab = mode;

  // --- [파일명 변경 탭 상태] ---
  const [renameList, setRenameList] = useState<RenameRecommendation[]>(initialRenameList);
  const [selectedRenameIds, setSelectedRenameIds] = useState<string[]>([]);

  useEffect(() => {
    setRenameList(initialRenameList);
  }, [initialRenameList]);

  // --- [폴더 구조 비교 탭 상태] ---
  const [structureList, setStructureList] = useState<StructureRecommendation[]>(initialStructureList);
  const [selectedMoveIds, setSelectedMoveIds] = useState<string[]>([]);

  useEffect(() => {
    setStructureList(initialStructureList);
    // 기본 미선택 — 파일명 변경 탭과 같은 규칙이다. 예전에는 결과가 도착하면
    // 전부 선택돼 있어서, 검토 없이 버튼을 누르면 모든 파일이 한 번에 이동했다.
    setSelectedMoveIds([]);
  }, [initialStructureList]);

  // --- [적용 진행·검사·되돌리기 상태] ---
  // isApplying: 요청이 나가 있는 동안 버튼을 잠근다 — 더블클릭이 같은 파일에
  //             적용을 두 번 보내 "원본 없음" 실패를 만들던 문제의 방지선.
  // lastCheck : 적용 직전 dry_run 검사의 실제 결과. 예전에는 검사 없이
  //             "충돌·오류 0 · 적용 전 검사 완료"를 **고정 문구로** 보여줬다.
  // lastUndo  : 방금 적용한 작업의 이력 id — 백엔드 undo를 화면에 연결한다.
  const [isApplying, setIsApplying] = useState(false);
  const [lastCheck, setLastCheck] = useState<{ ok: number; renamed: number; failed: number } | null>(null);
  const [lastUndo, setLastUndo] = useState<{ id: string; moved: number } | null>(null);
  // "정리 내역" 패널 — 과거 적용 목록에서 골라서 되돌린다. 배너는 "방금
  // 적용"만 다루므로, 앱을 껐다 켠 뒤나 몇 번 적용한 뒤의 복구는 이쪽이다.
  const [showHistory, setShowHistory] = useState(false);
  const [historyList, setHistoryList] = useState<ApplyHistoryEntry[]>([]);
  const [historyError, setHistoryError] = useState('');

  const refreshHistory = async () => {
    try {
      setHistoryError('');
      setHistoryList(await getApplyHistory());
    } catch (error) {
      setHistoryError((error as Error).message);
    }
  };

  const handleToggleHistory = () => {
    const next = !showHistory;
    setShowHistory(next);
    if (next) void refreshHistory();
  };

  // 💡 API로 전달받은 structureList를 실시간 동적 트리로 변환
  const currentTree = useMemo(
    () => buildTreeFromList(structureList, 'currentFolder'),
    [structureList]
  );

  const activeStructureList = useMemo(
    () => structureList.filter((item) => selectedMoveIds.includes(item.id)),
    [structureList, selectedMoveIds]
  );

  const targetTree = useMemo(
    () => buildTreeFromList(activeStructureList, 'targetFolder'),
    [activeStructureList]
  );

  // --- [API 및 액션 핸들러] ---
  // 폴더를 다시 읽어 추천을 새로 만든다.
  // 예전에는 Mock API(/mock/reanalyze)를 불러 실제로는 아무것도 바뀌지 않았다.
  const handleReanalyze = () => {
    setSelectedRenameIds([]);
    setSelectedMoveIds([]);
    onRefreshData?.();
  };

  // 실제 적용(POST /apply) 결과에서 "정말 바뀐" id만 골라낸다.
  // outcome이 null이면 mock 모드(폴더 미선택)라 전부 성공으로 간주한다.
  const appliedIdsFrom = (
    outcome: Awaited<ReturnType<typeof applyRenameRecommendations>>,
    requestedIds: string[],
  ): { doneIds: string[]; summary: string } => {
    if (!outcome) {
      return { doneIds: requestedIds, summary: `${requestedIds.length}건 적용 완료` };
    }
    const doneIds = outcome.appliedIds.filter(
      (_, index) => outcome.items[index]?.status === 'moved'
    );
    const problems = outcome.items
      .filter((item) => item.status !== 'moved')
      .map((item) => {
        const name = item.source_path.split(/[\\/]/).filter(Boolean).at(-1);
        return `• ${name}: ${item.reason || item.status}`;
      });
    let summary = `${doneIds.length}건 적용 완료`;
    if (problems.length > 0) {
      summary += `\n적용되지 않음 ${problems.length}건:\n${problems.join('\n')}`;
    }
    return { doneIds, summary };
  };

  // 적용 전 dry_run 결과를 요약·표시하고, 계속할지 사용자에게 확인받는다.
  // 검사가 불가능한 상태(mock 모드)면 null이 와서 그대로 진행한다.
  const confirmAfterDryRun = (
    check: Awaited<ReturnType<typeof applyRenameRecommendations>>,
  ): boolean => {
    if (!check) return true;
    const ok = check.items.filter((item) => item.status === 'valid').length;
    const renamed = check.items.filter(
      (item) => item.status === 'valid' && item.reason.startsWith('conflict_renamed')).length;
    const problems = check.items.filter((item) => item.status !== 'valid');
    setLastCheck({ ok, renamed, failed: problems.length });

    if (problems.length === 0) return true;
    const lines = problems.slice(0, 8).map((item) => {
      const name = item.source_path.split(/[\\/]/).filter(Boolean).at(-1);
      return `• ${name}: ${item.reason || item.status}`;
    });
    if (ok === 0) {
      alert(`적용 전 검사 결과, 적용할 수 있는 항목이 없습니다:\n${lines.join('\n')}`);
      return false;
    }
    return confirm(
      `적용 전 검사 결과 ${problems.length}건은 적용할 수 없습니다:\n${lines.join('\n')}\n\n` +
      `나머지 ${ok}건만 적용할까요?`,
    );
  };

  const handleApplySelected = async () => {
    if (isApplying) return;
    setIsApplying(true);
    try {
      await runApplySelected();
      if (showHistory) void refreshHistory();  // 방금 적용이 내역에 바로 보이게
    } finally {
      setIsApplying(false);
    }
  };

  const runApplySelected = async () => {
    if (activeTab === 'rename') {
      if (selectedRenameIds.length === 0) return;
      // 사용자가 입력 칸에서 고친 이름이 있으면 그 이름으로 적용한다.
      // 화면의 최신 값을 직접 넘긴다 — 분석 시점 캐시만 믿으면 편집이 무시된다.
      const editedNames = Object.fromEntries(
        renameList
          .filter((item) => selectedRenameIds.includes(item.id))
          .map((item) => [item.id, item.recommendedName]),
      );
      let outcome;
      try {
        const check = await applyRenameRecommendations(selectedRenameIds, editedNames, true);
        if (!confirmAfterDryRun(check)) return;
        outcome = await applyRenameRecommendations(selectedRenameIds, editedNames);
      } catch (error) {
        alert(`적용 중 오류가 발생했습니다:\n${(error as Error).message}`);
        return;
      }
      if (outcome?.history_id) setLastUndo({ id: outcome.history_id, moved: outcome.moved });
      const { doneIds, summary } = appliedIdsFrom(outcome, selectedRenameIds);

      const renameMap = new Map();
      renameList.forEach((item) => {
        if (doneIds.includes(item.id)) {
          renameMap.set(item.currentName, item.recommendedName);
        }
      });

      if (setCurrentFiles) {
        setCurrentFiles((prevFiles) =>
          prevFiles.map((file) => {
            if (renameMap.has(file.name)) {
              return { ...file, name: renameMap.get(file.name) };
            }
            return file;
          })
        );
      }

      const updatedRenameList = renameList.filter((item) => !doneIds.includes(item.id));
      setRenameList(updatedRenameList);
      if (setParentRenameList) setParentRenameList(updatedRenameList);

      alert(`파일명 변경: ${summary}`);
      setSelectedRenameIds([]);
    } else {
      if (selectedMoveIds.length === 0) return;
      let outcome;
      try {
        const check = await applyStructureRecommendations(selectedMoveIds, true);
        if (!confirmAfterDryRun(check)) return;
        outcome = await applyStructureRecommendations(selectedMoveIds);
      } catch (error) {
        alert(`적용 중 오류가 발생했습니다:\n${(error as Error).message}`);
        return;
      }
      if (outcome?.history_id) setLastUndo({ id: outcome.history_id, moved: outcome.moved });
      const { doneIds, summary } = appliedIdsFrom(outcome, selectedMoveIds);

      const moveMap = new Map();
      structureList.forEach((item) => {
        if (doneIds.includes(item.id)) {
          moveMap.set(item.fileName, item.targetFolder);
        }
      });

      if (setCurrentFiles) {
        setCurrentFiles((prevFiles) =>
          prevFiles.map((file) => {
            if (moveMap.has(file.name)) {
              return {
                ...file,
                path: moveMap.get(file.name),
              };
            }
            return file;
          })
        );
      }

      const updatedStructureList = structureList.filter((item) => !doneIds.includes(item.id));
      setStructureList(updatedStructureList);
      if (setParentStructureList) setParentStructureList(updatedStructureList);

      alert(`파일 이동: ${summary}`);
      setSelectedMoveIds([]);
    }
  };

  // 방금 적용한 작업을 역순으로 되돌린다 (백엔드 /apply/undo).
  const handleUndo = async () => {
    if (!lastUndo || isApplying) return;
    setIsApplying(true);
    try {
      const result = await undoApply(lastUndo.id);
      let message = `${result.restored}건을 원래 자리로 되돌렸습니다.`;
      if (result.skipped.length > 0) {
        const lines = result.skipped.slice(0, 5).map((entry) => {
          const name = entry.path.split(/[\\/]/).filter(Boolean).at(-1);
          return `• ${name}: ${entry.reason}`;
        });
        message += `\n되돌리지 못함 ${result.skipped.length}건:\n${lines.join('\n')}`;
      }
      alert(message);
      setLastUndo(null);
      setLastCheck(null);
      if (showHistory) void refreshHistory();
      // 화면의 추천 목록은 적용 시점에 지워졌다 — 폴더를 다시 읽어야 맞는 상태가 된다.
      onRefreshData?.();
    } catch (error) {
      alert(`되돌리기 중 오류가 발생했습니다:\n${(error as Error).message}`);
    } finally {
      setIsApplying(false);
    }
  };

  // 내역 패널에서 고른 과거 적용 1회분을 되돌린다.
  const handleUndoEntry = async (entry: ApplyHistoryEntry) => {
    if (isApplying) return;
    if (!confirm(`${formatAppliedAt(entry.applied_at)}에 적용한 ${entry.moves}건을 되돌릴까요?\n` +
                 '그 뒤에 옮기거나 이름을 바꾼 파일은 건너뜁니다.')) return;
    setIsApplying(true);
    try {
      const result = await undoApply(entry.id);
      let message = `${result.restored}건을 원래 자리로 되돌렸습니다.`;
      if (result.skipped.length > 0) {
        message += `\n되돌리지 못함 ${result.skipped.length}건 (이후에 변경된 파일)`;
      }
      alert(message);
      if (lastUndo?.id === entry.id) setLastUndo(null);
      await refreshHistory();
      onRefreshData?.();
    } catch (error) {
      alert(`되돌리기 중 오류가 발생했습니다:\n${(error as Error).message}`);
    } finally {
      setIsApplying(false);
    }
  };

  const handleSelectAllRename = () => {
    if (selectedRenameIds.length === renameList.length) {
      setSelectedRenameIds([]);
    } else {
      setSelectedRenameIds(renameList.map((item) => item.id));
    }
  };

  const handleToggleRenameSelect = (id: string) => {
    setSelectedRenameIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleRenameChange = (id: string, newName: string) => {
    setRenameList((prev) =>
      prev.map((item) => (item.id === id ? { ...item, recommendedName: newName } : item))
    );
  };

  const handleSelectAllMove = () => {
    if (selectedMoveIds.length === structureList.length) {
      setSelectedMoveIds([]);
    } else {
      setSelectedMoveIds(structureList.map((item) => item.id));
    }
  };

  const handleToggleMoveSelect = (id: string) => {
    setSelectedMoveIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  // 폴더가 없거나 분석 중이면 표 대신 상태를 보여 준다.
  // 예전에는 둘 다 빈 표로 떨어져 "기능이 구현 안 된 것"처럼 보였다.
  if (!selectedPath || isAnalyzing || analyzeError) {
    return (
      <div className="flex flex-1 items-center justify-center p-10">
        <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-2xs dark:border-gray-700 dark:bg-[#16161e]">
          {!selectedPath ? (
            <>
              <div className="text-sm font-bold text-gray-800 dark:text-gray-100">
                {mode === 'rename'
                  ? '이름을 바꿀 폴더를 먼저 골라 주세요'
                  : '정리할 폴더를 먼저 골라 주세요'}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                오른쪽 위 <b>[폴더 선택]</b>을 누르면{' '}
                {mode === 'rename'
                  ? '그 폴더의 문서를 읽어 어울리는 파일명을 제안합니다.'
                  : '그 폴더 안에 갈래별 폴더를 만들어 정리할 계획을 세웁니다.'}
              </p>
            </>
          ) : isAnalyzing ? (
            <>
              <div className="mx-auto mb-4 h-1.5 w-48 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-500/25">
                <div className="h-full w-1/3 rounded-full bg-indigo-500 animate-[loading_1.2s_ease-in-out_infinite]" />
              </div>
              <div className="text-sm font-bold text-gray-800 dark:text-gray-100">
                {mode === 'rename'
                  ? '어울리는 이름을 지어 보는 중입니다'
                  : '문서를 갈래별로 나누는 중입니다'}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                {mode === 'rename'
                  ? '파일마다 내용을 읽고 무엇에 관한 문서인지 파악해 이름을 만듭니다. 그래픽카드가 없으면 파일당 10초 이상 걸릴 수 있습니다.'
                  : '파일마다 강의자료·과제·시험 준비 같은 갈래를 정하고, 어느 폴더로 보낼지 결정합니다.'}
              </p>
            </>
          ) : (
            <>
              <div className="text-sm font-bold text-red-600">분석하지 못했습니다</div>
              <p className="mt-2 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                {analyzeError}
              </p>
              <button
                onClick={onRefreshData}
                className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-[12px] font-bold text-white hover:bg-indigo-700"
              >
                다시 시도
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-white dark:bg-[#16161e] p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        
        {/* 헤더 영역 */}
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h2 className="text-xl font-black text-gray-900 dark:text-gray-50">
              {activeTab === 'rename'
                ? '내용에 맞는 파일명을 제안합니다.'
                : '선택한 폴더 안에 갈래별 폴더를 만들어 정리합니다.'}
            </h2>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">
              {activeTab === 'rename'
                ? '추천 이름은 직접 고쳐도 됩니다. 체크한 파일만 실제로 바뀝니다.'
                : `${selectedPath || '선택한 폴더'} 아래에 새 폴더가 생기고, 체크한 파일만 그리로 옮겨집니다.`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleToggleHistory}
              className="px-4 py-2 bg-white dark:bg-[#16161e] border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-200 font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
            >
              🕘 정리 내역
            </button>
            {analyzedCount != null && totalFiles > analyzedCount && (
              <button
                onClick={() => onAnalyzeMore?.()}
                disabled={isApplying}
                className="px-4 py-2 bg-white dark:bg-[#16161e] border border-indigo-200 dark:border-indigo-500/40 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 disabled:opacity-50 text-indigo-600 dark:text-indigo-300 font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
              >
                ▶ 이어서 분석 (남은 {totalFiles - analyzedCount}개)
              </button>
            )}
            <button
              onClick={handleReanalyze}
              disabled={isApplying}
              className="px-4 py-2 bg-white dark:bg-[#16161e] border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 text-gray-700 dark:text-gray-200 font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
            >
              {mode === 'rename' ? '↻ 이름 다시 짓기' : '↻ 다시 정리하기'}
            </button>
            <button
              onClick={handleApplySelected}
              disabled={
                isApplying || (
                  activeTab === 'rename'
                    ? selectedRenameIds.length === 0
                    : selectedMoveIds.length === 0
                )
              }
              className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-200 text-white font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
            >
              {isApplying ? '적용 중…' : '선택 항목 적용'}
            </button>
          </div>
        </div>

        {/* 정리 내역 — 과거 적용 목록에서 골라 되돌린다. 배너("방금 적용")가
            못 다루는 경우(앱 재시작 후, 여러 번 적용한 뒤)의 복구 경로. */}
        {showHistory && (
          <div className="mb-6 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden">
            <div className="bg-gray-50/80 dark:bg-white/5 px-5 py-3 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between">
              <h3 className="font-bold text-gray-900 dark:text-gray-50 text-xs">정리 내역</h3>
              <span className="text-[11px] text-gray-400 dark:text-gray-500 font-medium">
                파일을 실제로 옮기거나 이름을 바꾼 기록입니다. 회차 단위로 되돌릴 수 있습니다.
              </span>
            </div>
            {historyError && (
              <div className="px-5 py-3 text-[11px] text-red-500">{historyError}</div>
            )}
            {!historyError && historyList.length === 0 && (
              <div className="px-5 py-4 text-[11px] text-gray-400 dark:text-gray-500">아직 적용한 내역이 없습니다.</div>
            )}
            {historyList.map((entry) => (
              <div key={entry.id} className="px-5 py-2.5 border-b border-gray-50 dark:border-gray-700/40 last:border-b-0 flex items-center gap-3">
                <span className="text-[11px] font-semibold text-gray-700 dark:text-gray-200 w-24 shrink-0">{formatAppliedAt(entry.applied_at)}</span>
                <span className="text-[11px] text-gray-500 dark:text-gray-400 truncate flex-1">{entry.moves}건 · {entry.root}</span>
                {entry.undone ? (
                  <span className="text-[10px] font-bold text-gray-300 dark:text-gray-600 shrink-0">되돌림</span>
                ) : (
                  <button
                    onClick={() => handleUndoEntry(entry)}
                    disabled={isApplying}
                    className="px-2.5 py-1 border border-gray-200 dark:border-gray-600 text-[11px] font-bold text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition cursor-pointer shrink-0"
                  >
                    ↩ 되돌리기
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 방금 적용한 작업의 되돌리기 — 백엔드에 있던 undo가 처음으로 화면에 연결된다 */}
        {lastUndo && (
          <div className="mb-6 flex items-center gap-3 rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 px-4 py-3">
            <span className="text-[11px] text-emerald-800 dark:text-emerald-300 font-medium">
              방금 {lastUndo.moved}건을 적용했습니다. 잘못 적용했다면 바로 되돌릴 수 있습니다.
            </span>
            <button
              onClick={handleUndo}
              disabled={isApplying}
              className="px-3 py-1.5 bg-white dark:bg-transparent border border-emerald-300 dark:border-emerald-500/40 text-emerald-700 dark:text-emerald-300 font-bold text-[11px] rounded-lg hover:bg-emerald-100 dark:hover:bg-emerald-500/20 transition cursor-pointer"
            >
              ↩ 되돌리기
            </button>
            <button
              onClick={() => setLastUndo(null)}
              className="ml-auto px-1 text-xs font-bold text-emerald-400 hover:text-emerald-600 cursor-pointer"
              title="닫기"
            >
              ✕
            </button>
          </div>
        )}

        {/* ========================================================= */}
        {/* 탭 1: 파일명 변경 모드                                     */}
        {/* ========================================================= */}
        {activeTab === 'rename' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">분석된 파일</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{analyzedCount ?? totalFiles}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">
                  {analyzedCount != null && totalFiles > analyzedCount
                    ? `전체 ${totalFiles}개 중 (한 번에 최대 20개)`
                    : 'PDF · DOCX · PPT · HWP 등 7종'}
                </div>
              </div>

              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">이름 변경 추천</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{renameList.length}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">문서 내용 기반</div>
              </div>

              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">선택된 항목</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{selectedRenameIds.length}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">사용자 승인 필요</div>
              </div>

              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                {/* 실행하지 않은 검사를 "완료"로 표시하지 않는다 — 적용 버튼을
                    누르면 dry_run 검사가 먼저 돌고, 그 실제 결과가 여기 남는다. */}
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">충돌·오류</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{lastCheck ? lastCheck.failed : '—'}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">
                  {lastCheck
                    ? `검사 결과: 가능 ${lastCheck.ok}건${lastCheck.renamed ? ` · 이름 조정 ${lastCheck.renamed}건` : ''}`
                    : '적용 시 자동 검사'}
                </div>
              </div>
            </div>

            {/* 분석하지 못한 파일 — 숨기면 "8개 중 5개만 추천"의 이유를 알 수 없다 */}
            {failedFiles.length > 0 && (
              <div className="p-4 bg-amber-50 dark:bg-amber-500/10 rounded-2xl border border-amber-200/80 dark:border-amber-500/30">
                <div className="text-[11px] font-bold text-amber-700 dark:text-amber-400">
                  분석하지 못한 파일 {failedFiles.length}개
                </div>
                <ul className="mt-1.5 space-y-0.5">
                  {failedFiles.map((file) => (
                    <li key={file.path} className="text-[11px] text-amber-800/80 dark:text-amber-300/80">
                      <b className="font-semibold">{file.name}</b>
                      {' — '}
                      {file.reason.includes(':') ? file.reason.split(':').slice(1).join(':').trim() : file.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-stretch">
              <div className="lg:col-span-3 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden flex flex-col">
                <div className="bg-gray-50/80 dark:bg-white/5 px-6 h-13 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-gray-900 dark:text-gray-50 text-xs">파일명 변경 추천</h3>
                    <span className="text-[11px] text-gray-400 dark:text-gray-500 font-medium">추천 이름은 직접 수정할 수 있습니다.</span>
                  </div>
                  {renameList.length > 0 && (
                    <button
                      onClick={handleSelectAllRename}
                      className="px-3 py-1 border border-gray-200/80 dark:border-gray-700 bg-white dark:bg-[#16161e] hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-200 text-xs font-bold rounded-lg transition shadow-2xs cursor-pointer"
                    >
                      {selectedRenameIds.length === renameList.length ? '선택 해제' : '전체 선택'}
                    </button>
                  )}
                </div>

                <div className="flex-1 bg-white dark:bg-[#16161e] overflow-x-auto flex flex-col">
                  {renameList.length === 0 ? (
                    <div className="py-16 text-center text-gray-400 dark:text-gray-500 text-xs font-medium">
                      🎉 변경 추천 대상 파일이 없거나 모두 적용 완료되었습니다!
                    </div>
                  ) : (
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-gray-100 dark:border-gray-700/70 bg-gray-50/80 dark:bg-white/5 h-13 text-[11px] text-gray-400 dark:text-gray-500 font-bold">
                          <th className="px-6 w-12 text-center"></th>
                          <th className="px-3">현재 파일</th>
                          <th className="px-3">추천 파일명</th>
                          <th className="px-6 text-right w-24">신뢰도</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 dark:divide-gray-700/70 text-xs px-6">
                        {renameList.map((item) => (
                          <tr key={item.id} className="hover:bg-gray-50/40 transition">
                            <td className="py-4 px-6 text-center">
                              <input
                                type="checkbox"
                                checked={selectedRenameIds.includes(item.id)}
                                onChange={() => handleToggleRenameSelect(item.id)}
                                className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                              />
                            </td>
                            <td className="py-4 px-3 pr-4">
                              <div className="flex items-center gap-3">
                                <span
                                  className={`px-2 py-1 rounded-lg text-[10px] font-extrabold shrink-0 ${
                                    item.fileType === 'PDF'
                                      ? 'bg-gray-50 text-black-500 border border-gray-100'
                                      : item.fileType === 'TXT'
                                      ? 'bg-gray-50 text-black-500 border border-gray-100'
                                      : 'bg-gray-50 text-black-500 border border-gray-100'
                                  }`}
                                >
                                  {item.fileType}
                                </span>
                                <div className="space-y-0.5">
                                  <button
                                    onClick={() => void window.api?.revealFile?.(item.path ?? '')}
                                    title="탐색기에서 이 파일 보기"
                                    className="text-left font-bold text-gray-900 dark:text-gray-50 text-xs hover:text-indigo-600 hover:underline cursor-pointer"
                                  >
                                    {item.currentName}
                                  </button>
                                  <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">{item.category}</div>
                                </div>
                              </div>
                            </td>
                            <td className="py-4 px-3 pr-4">
                              <input
                                type="text"
                                value={item.recommendedName}
                                onChange={(e) => handleRenameChange(item.id, e.target.value)}
                                placeholder="추천 이름을 만들지 못했습니다. 직접 입력하세요."
                                className="w-full bg-white dark:bg-[#16161e] border border-indigo-100 dark:border-indigo-500/30 rounded-2xl px-4 py-2.5 text-xs font-bold text-indigo-600 dark:text-indigo-300 placeholder:font-medium placeholder:text-gray-300 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-200 transition"
                              />
                            </td>
                            <td className="py-4 px-6 text-right">
                              <span className="text-emerald-600 font-bold text-xs">
                                {item.confidence}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              <div className="bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden flex flex-col justify-between">
                <div className="bg-gray-50/80 dark:bg-white/5 px-5 h-13 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between shrink-0">
                  <h3 className="font-bold text-gray-900 dark:text-gray-50 text-xs">이름 변경 미리보기</h3>
                  <span className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">안전 적용</span>
                </div>

                <div className="p-5 flex-1 bg-white dark:bg-[#16161e] flex flex-col justify-between space-y-5">
                  <div className="space-y-4">
                    {selectedRenameIds.length === 0 ? (
                      <div className="p-4 rounded-2xl border border-dashed border-gray-200 dark:border-gray-700 text-center py-12">
                        <p className="text-gray-400 dark:text-gray-500 text-[11px] leading-relaxed font-medium">
                          왼쪽 목록에서 변경할 파일을 선택하면
                          <br />
                          바뀌기 전과 후를 여기서 보여 줍니다.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                        <p className="text-[11px] font-bold text-gray-500 dark:text-gray-400">
                          {selectedRenameIds.length}개 파일이 이렇게 바뀝니다
                        </p>
                        {renameList
                          .filter((item) => selectedRenameIds.includes(item.id))
                          .map((item) => (
                            <div
                              key={item.id}
                              className="rounded-xl border border-gray-200 dark:border-gray-700 p-3 space-y-1"
                            >
                              <div className="truncate text-[11px] text-gray-400 dark:text-gray-500 line-through">
                                {item.currentName}
                              </div>
                              <div className="flex items-start gap-1.5">
                                <span className="text-[11px] text-indigo-400">→</span>
                                <div className="min-w-0 break-all text-[11px] font-bold text-indigo-600 dark:text-indigo-300">
                                  {item.recommendedName || '(이름 없음)'}
                                </div>
                              </div>
                            </div>
                          ))}
                      </div>
                    )}

                    <div className="space-y-2.5 pt-1">
                      <div className="flex items-center gap-2.5 text-[11px] text-gray-500 dark:text-gray-400 font-medium">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 flex items-center justify-center text-[10px] font-bold">✓</span>
                        <span>동일한 파일명이 있는지 검사합니다.</span>
                      </div>
                      <div className="flex items-center gap-2.5 text-[11px] text-gray-500 dark:text-gray-400 font-medium">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 flex items-center justify-center text-[10px] font-bold">✓</span>
                        <span>운영체제에서 금지된 문자를 확인합니다.</span>
                      </div>
                      <div className="flex items-center gap-2.5 text-[11px] text-gray-500 dark:text-gray-400 font-medium">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 flex items-center justify-center text-[10px] font-bold">✓</span>
                        <span>확장자는 원본 파일과 동일하게 유지합니다.</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-gray-700/70">
                    <button
                      onClick={() => setSelectedRenameIds([])}
                      className="w-1/2 py-2.5 border border-gray-200/80 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-200 text-xs font-bold rounded-xl transition cursor-pointer"
                    >
                      선택 해제
                    </button>
                    <button
                      onClick={handleApplySelected}
                      disabled={selectedRenameIds.length === 0}
                      className="w-1/2 py-2.5 bg-indigo-200/90 hover:bg-indigo-600 disabled:bg-indigo-200 text-white text-xs font-bold rounded-xl transition cursor-pointer"
                    >
                      이름 변경
                    </button>
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* 탭 2: 폴더 구조 비교 모드                                  */}
        {/* ========================================================= */}
        {activeTab === 'structure' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">전체 파일 수</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{totalFiles}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">분석 대상 문서</div>
              </div>

              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">이동 추천</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{structureList.length}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">내용·프로젝트 기반</div>
              </div>

              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">선택된 이동</div>
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">{selectedMoveIds.length}</div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">오른쪽 구조에 반영</div>
              </div>

              <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">이동할 폴더 수</div>
                {/* 파일 수가 아니라 서로 다른 대상 폴더의 수다 — 10개 파일이 전부
                    "과제" 한 폴더로 가면 1이다. */}
                <div className="text-2xl font-black text-gray-900 dark:text-gray-50">
                  {new Set(activeStructureList.map((item) => item.targetFolder)).size}
                </div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">자동 디렉터리 구성</div>
              </div>
            </div>

            {/* 이동 추천 카드 패널 */}
            <div className="bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden">
              <div className="bg-gray-50/80 dark:bg-white/5 px-6 py-3.5 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-gray-900 dark:text-gray-50 text-xs">파일 이동 추천</h3>
                  <p className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">
                    체크한 항목만 아래 비교 화면에 반영됩니다.
                  </p>
                </div>
                {structureList.length > 0 && (
                  <button
                    onClick={handleSelectAllMove}
                    className="px-3 py-1 border border-gray-200/80 dark:border-gray-700 bg-white dark:bg-[#16161e] hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-200 text-xs font-bold rounded-lg transition shadow-2xs cursor-pointer"
                  >
                    {selectedMoveIds.length === structureList.length ? '전체 해제' : '전체 선택'}
                  </button>
                )}
              </div>

              <div className="p-6 bg-white dark:bg-[#16161e]">
                {structureList.length === 0 ? (
                  <div className="py-8 text-center text-gray-400 dark:text-gray-500 text-xs font-medium">
                    🎉 이동 추천 대상 파일이 없거나 모두 적용 완료되었습니다!
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {structureList.map((item) => {
                      const isChecked = selectedMoveIds.includes(item.id);
                      return (
                        <div
                          key={item.id}
                          onClick={() => handleToggleMoveSelect(item.id)}
                          className={`p-4 rounded-2xl border transition cursor-pointer flex items-start gap-3 relative ${
                            isChecked
                              ? 'border-indigo-400 bg-white ring-2 ring-indigo-500/20 shadow-xs'
                              : 'border-gray-200/80 bg-white hover:border-gray-300'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => {}}
                            className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 mt-1 cursor-pointer"
                          />
                          <div className="space-y-2 flex-1 min-w-0">
                            <div className="font-bold text-xs text-gray-900 dark:text-gray-50 truncate">
                              {item.fileName}
                            </div>

                            <div className="flex items-center gap-1.5 text-[11px] flex-wrap">
                              <span className="px-2 py-0.5 bg-gray-100 dark:bg-white/10 text-gray-500 dark:text-gray-400 font-medium rounded-md text-[10px]">
                                {item.currentFolder}
                              </span>
                              <span className="text-gray-300 dark:text-gray-600 text-[10px]">→</span>
                              <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-500/15 text-emerald-600 font-medium rounded-md truncate max-w-[130px] text-[10px]">
                                {item.targetFolder.replace(/^Documents\//, '')}
                              </span>
                            </div>

                            <div className="text-[10px] text-emerald-600 font-extrabold pt-0.5">
                              추천 신뢰도 {item.confidence}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* 백엔드 연동 % 동적 다계층 폴더 트리 비교 영역 */}
            <div className="grid grid-cols-1 lg:grid-cols-11 gap-4 items-stretch">
              
              {/* 좌측 트리: 현재 폴더 구조 (동적 생성) */}
              <div className="lg:col-span-5 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden flex flex-col h-full">
                <div className="bg-gray-50/80 dark:bg-white/5 px-5 h-12 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between shrink-0">
                  <div className="space-y-0.5">
                    <h3 className="font-bold text-gray-900 dark:text-gray-50 text-xs">현재 폴더 구조</h3>
                    <p className="text-[9px] text-gray-400 dark:text-gray-500 font-medium">실제 파일이 지금 저장된 위치</p>
                  </div>
                  <span className="text-[10px] text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                    <span>이동 예정</span>
                  </span>
                </div>
                <div className="p-5 text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-[#16161e] flex-1 overflow-y-auto">
                  <DynamicTreeNode
                    node={currentTree}
                    selectedMoveIds={selectedMoveIds}
                    isTargetTree={false}
                  />
                </div>
              </div>

              {/* 중앙 인디케이터 화살표 */}
              <div className="lg:col-span-1 flex flex-col items-center justify-center text-center py-2 shrink-0">
                <div className="w-10 h-10 bg-gray-50 dark:bg-white/5 border border-black-100 rounded-full flex items-center justify-center text-black-600 font-bold shadow-2xs mb-1">
                  ➔
                </div>
                <div className="text-xs font-black text-black-600">
                  {selectedMoveIds.length}개
                </div>
                <div className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">이동 반영</div>
              </div>

              {/* 우측 트리: 적용 후 폴더 구조 (동적 생성) */}
              <div className="lg:col-span-5 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden flex flex-col h-full">
                <div className="bg-gray-50/80 dark:bg-white/5 px-5 h-12 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between shrink-0">
                  <div className="space-y-0.5">
                    <h3 className="font-bold text-gray-900 dark:text-gray-50 text-xs">적용 후 폴더 구조</h3>
                    <p className="text-[9px] text-gray-400 dark:text-gray-500 font-medium">승인한 이동이 반영된 예상 구조</p>
                  </div>
                  <span className="text-[10px] text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    <span>새 위치</span>
                  </span>
                </div>

                <div className="p-5 text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-[#16161e] flex-1 overflow-y-auto">
                  {selectedMoveIds.length === 0 ? (
                    <div className="text-gray-400 dark:text-gray-500 text-[11px] py-12 text-center font-medium">
                      선택된 이동 항목이 없습니다.
                    </div>
                  ) : (
                    <DynamicTreeNode
                      node={targetTree}
                      selectedMoveIds={selectedMoveIds}
                      isTargetTree={true}
                    />
                  )}
                </div>
              </div>

            </div>

            {/* 하단 푸터 */}
            <div className="p-4 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs flex items-center justify-between">
              <div>
                <h4 className="font-bold text-gray-900 dark:text-gray-50 text-xs">
                  {selectedMoveIds.length}개 파일 이동이 적용 후 구조에 반영되었습니다.
                </h4>
                <p className="text-[11px] text-gray-400 dark:text-gray-500 font-medium">
                  왼쪽의 현재 위치는 빨간색 줄, 오른쪽의 새 위치는 초록색 카드로 연동되어 표시됩니다.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedMoveIds([])}
                  className="px-4 py-2 border border-gray-200/80 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-200 font-bold text-xs rounded-xl transition cursor-pointer"
                >
                  선택 해제
                </button>
                <button
                  onClick={handleApplySelected}
                  disabled={selectedMoveIds.length === 0}
                  className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-200 text-white font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
                >
                  폴더 구조 적용
                </button>
              </div>
            </div>

          </div>
        )}

      </div>
    </div>
  );
}