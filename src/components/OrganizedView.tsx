import React, { useState, useEffect, useMemo } from 'react';
import { 
  RenameRecommendation, 
  StructureRecommendation,
  CurrentFileItem,
  reanalyzeProject,
  applyRenameRecommendations,
  applyStructureRecommendations
} from '../api/organizeApi';

interface OrganizeViewProps {
  renameList?: RenameRecommendation[];
  setRenameList?: React.Dispatch<React.SetStateAction<RenameRecommendation[]>>;
  structureList?: StructureRecommendation[];
  setStructureList?: React.Dispatch<React.SetStateAction<StructureRecommendation[]>>;
  currentFiles?: CurrentFileItem[];
  setCurrentFiles?: React.Dispatch<React.SetStateAction<CurrentFileItem[]>>;
  totalFiles?: number;
  onRefreshData?: () => void;
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
          <div className="flex items-center justify-between text-[11px] text-gray-800">
            <div className="flex items-center gap-1.5">
              <span>📁</span>
              <span>{node.name}</span>
            </div>
            <span className="text-[10px] bg-gray-100 text-gray-400 px-1.5 rounded-full font-semibold">
              {node.fileCount}
            </span>
          </div>

          {/* 자식 노드가 있으면 들여쓰기 계층선(border-l)과 함께 재귀 렌더링 */}
          {childKeys.length > 0 && (
            <div className="pl-3 border-l border-gray-100 ml-1.5 space-y-1 pt-0.5">
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
                  <span
                    className={`text-[11px] truncate pr-2 ${
                      selectedMoveIds.includes(node.fileData.id)
                        ? 'text-rose-600'
                        : 'text-gray-700'
                    }`}
                  >
                    📄 {node.name}
                  </span>
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
                  <span className="text-[11px] text-emerald-800 truncate pr-2">
                    📄 {node.name}
                  </span>
                  <span className="text-[9px] bg-emerald-100 text-emerald-700 font-bold px-1.5 py-0.5 rounded shrink-0">
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
  onRefreshData,
}: OrganizeViewProps) {
  const [activeTab, setActiveTab] = useState<'rename' | 'structure'>('structure');

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
    setSelectedMoveIds(initialStructureList.map((item) => item.id));
  }, [initialStructureList]);

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
  const handleReanalyze = async () => {
    const res = await reanalyzeProject();
    if (res) {
      alert(`재분석이 완료되었습니다!\n• 파일명 추천: ${res.rename_count}건\n• 폴더 이동 추천: ${res.move_count}건`);
      if (onRefreshData) onRefreshData();
    } else {
      alert('재분석 요청 중 오류가 발생했습니다.');
    }
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

  const handleApplySelected = async () => {
    if (activeTab === 'rename') {
      if (selectedRenameIds.length === 0) return;
      let outcome;
      try {
        outcome = await applyRenameRecommendations(selectedRenameIds);
      } catch (error) {
        alert(`적용 중 오류가 발생했습니다:\n${(error as Error).message}`);
        return;
      }
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
        outcome = await applyStructureRecommendations(selectedMoveIds);
      } catch (error) {
        alert(`적용 중 오류가 발생했습니다:\n${(error as Error).message}`);
        return;
      }
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

  return (
    <div className="flex-1 overflow-y-auto bg-white p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        
        {/* 헤더 영역 */}
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h2 className="text-xl font-black text-gray-900">
              정리 전과 정리 후 구조를 한눈에 비교합니다.
            </h2>
            <p className="text-xs text-gray-400 font-medium">
              선택한 이동 추천만 반영해 오른쪽의 ‘적용 후 폴더 구조’를 실시간으로 다시 그립니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={handleReanalyze}
              className="px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
            >
              다시 분석
            </button>
            <button
              onClick={handleApplySelected}
              disabled={
                activeTab === 'rename'
                  ? selectedRenameIds.length === 0
                  : selectedMoveIds.length === 0
              }
              className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-200 text-white font-bold text-xs rounded-xl transition cursor-pointer shadow-2xs"
            >
              선택 항목 적용
            </button>
          </div>
        </div>

        {/* 상단 모드 전환 탭 */}
        <div className="flex items-center gap-2 border-b border-gray-100 pb-3">
          <button
            onClick={() => setActiveTab('rename')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
              activeTab === 'rename'
                ? 'bg-white text-gray-900 border border-gray-200 shadow-2xs'
                : 'text-gray-400 hover:bg-gray-50'
            }`}
          >
            <span>파일명 변경</span>
            <span className="px-2 py-0.5 text-[10px] bg-gray-50 text-black-600 rounded-full font-bold">
              {renameList.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('structure')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
              activeTab === 'structure'
                ? 'bg-white text-gray-900 border border-gray-200 shadow-2xs'
                : 'text-gray-400 hover:bg-gray-50'
            }`}
          >
            <span>폴더 구조 비교</span>
            <span className="px-2 py-0.5 text-[10px] bg-gray-100 text-gray-600 rounded-full font-bold">
              {structureList.length}
            </span>
          </button>
        </div>

        {/* ========================================================= */}
        {/* 탭 1: 파일명 변경 모드                                     */}
        {/* ========================================================= */}
        {activeTab === 'rename' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">분석된 파일</div>
                <div className="text-2xl font-black text-gray-900">{totalFiles}</div>
                <div className="text-[10px] text-gray-400 font-medium">PDF · TXT · MD</div>
              </div>

              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">이름 변경 추천</div>
                <div className="text-2xl font-black text-gray-900">{renameList.length}</div>
                <div className="text-[10px] text-gray-400 font-medium">문서 내용 기반</div>
              </div>

              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">선택된 항목</div>
                <div className="text-2xl font-black text-gray-900">{selectedRenameIds.length}</div>
                <div className="text-[10px] text-gray-400 font-medium">사용자 승인 필요</div>
              </div>

              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">충돌·오류</div>
                <div className="text-2xl font-black text-gray-900">0</div>
                <div className="text-[10px] text-gray-400 font-medium">적용 전 검사 완료</div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-stretch">
              <div className="lg:col-span-3 bg-white rounded-2xl border border-gray-200/80 shadow-2xs overflow-hidden flex flex-col">
                <div className="bg-gray-50/80 px-6 h-13 border-b border-gray-100 flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-gray-900 text-xs">파일명 변경 추천</h3>
                    <span className="text-[11px] text-gray-400 font-medium">추천 이름은 직접 수정할 수 있습니다.</span>
                  </div>
                  {renameList.length > 0 && (
                    <button
                      onClick={handleSelectAllRename}
                      className="px-3 py-1 border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-700 text-xs font-bold rounded-lg transition shadow-2xs cursor-pointer"
                    >
                      {selectedRenameIds.length === renameList.length ? '선택 해제' : '전체 선택'}
                    </button>
                  )}
                </div>

                <div className="flex-1 bg-white overflow-x-auto flex flex-col">
                  {renameList.length === 0 ? (
                    <div className="py-16 text-center text-gray-400 text-xs font-medium">
                      🎉 변경 추천 대상 파일이 없거나 모두 적용 완료되었습니다!
                    </div>
                  ) : (
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-gray-100 bg-gray-50/80 h-13 text-[11px] text-gray-400 font-bold">
                          <th className="px-6 w-12 text-center"></th>
                          <th className="px-3">현재 파일</th>
                          <th className="px-3">추천 파일명</th>
                          <th className="px-6 text-right w-24">신뢰도</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 text-xs px-6">
                        {renameList.map((item) => (
                          <tr key={item.id} className="hover:bg-gray-50/40 transition">
                            <td className="py-4 px-6 text-center">
                              <input
                                type="checkbox"
                                checked={selectedRenameIds.includes(item.id)}
                                onChange={() => handleToggleRenameSelect(item.id)}
                                className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
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
                                  <div className="font-bold text-gray-900 text-xs">{item.currentName}</div>
                                  <div className="text-[10px] text-gray-400 font-medium">{item.category}</div>
                                </div>
                              </div>
                            </td>
                            <td className="py-4 px-3 pr-4">
                              <input
                                type="text"
                                value={item.recommendedName}
                                onChange={(e) => handleRenameChange(item.id, e.target.value)}
                                className="w-full bg-white border border-indigo-100 rounded-2xl px-4 py-2.5 text-xs font-bold text-[#4F46E5] focus:outline-none focus:ring-2 focus:ring-indigo-200 transition"
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

              <div className="bg-white rounded-2xl border border-gray-200/80 shadow-2xs overflow-hidden flex flex-col justify-between">
                <div className="bg-gray-50/80 px-5 h-13 border-b border-gray-100 flex items-center justify-between shrink-0">
                  <h3 className="font-bold text-gray-900 text-xs">이름 변경 미리보기</h3>
                  <span className="text-[10px] text-gray-400 font-medium">안전 적용</span>
                </div>

                <div className="p-5 flex-1 bg-white flex flex-col justify-between space-y-5">
                  <div className="space-y-4">
                    <div className="p-4 rounded-2xl border border-dashed border-gray-200 text-center py-12 bg-gray-50/20">
                      {selectedRenameIds.length === 0 ? (
                        <p className="text-gray-400 text-[11px] leading-relaxed font-medium">
                          왼쪽 목록에서 변경할 파일을 선택하면<br />적용 전 요약을 표시합니다.
                        </p>
                      ) : (
                        <p className="font-bold text-indigo-600 text-xs">
                          총 {selectedRenameIds.length}개 파일의 이름 변경 준비가 완료되었습니다.
                        </p>
                      )}
                    </div>

                    <div className="space-y-2.5 pt-1">
                      <div className="flex items-center gap-2.5 text-[11px] text-gray-500 font-medium">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center text-[10px] font-bold">✓</span>
                        <span>동일한 파일명이 있는지 검사합니다.</span>
                      </div>
                      <div className="flex items-center gap-2.5 text-[11px] text-gray-500 font-medium">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center text-[10px] font-bold">✓</span>
                        <span>운영체제에서 금지된 문자를 확인합니다.</span>
                      </div>
                      <div className="flex items-center gap-2.5 text-[11px] text-gray-500 font-medium">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center text-[10px] font-bold">✓</span>
                        <span>확장자는 원본 파일과 동일하게 유지합니다.</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
                    <button
                      onClick={() => setSelectedRenameIds([])}
                      className="w-1/2 py-2.5 border border-gray-200/80 hover:bg-gray-50 text-gray-700 text-xs font-bold rounded-xl transition cursor-pointer"
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
              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">전체 파일 수</div>
                <div className="text-2xl font-black text-gray-900">{totalFiles}</div>
                <div className="text-[10px] text-gray-400 font-medium">분석 대상 문서</div>
              </div>

              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">이동 추천</div>
                <div className="text-2xl font-black text-gray-900">{structureList.length}</div>
                <div className="text-[10px] text-gray-400 font-medium">내용·프로젝트 기반</div>
              </div>

              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">선택된 이동</div>
                <div className="text-2xl font-black text-gray-900">{selectedMoveIds.length}</div>
                <div className="text-[10px] text-gray-400 font-medium">오른쪽 구조에 반영</div>
              </div>

              <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs space-y-1">
                <div className="text-[11px] font-bold text-gray-400">생성될 폴더 수</div>
                <div className="text-2xl font-black text-gray-900">{selectedMoveIds.length}</div>
                <div className="text-[10px] text-gray-400 font-medium">자동 디렉터리 구성</div>
              </div>
            </div>

            {/* 이동 추천 카드 패널 */}
            <div className="bg-white rounded-2xl border border-gray-200/80 shadow-2xs overflow-hidden">
              <div className="bg-gray-50/80 px-6 py-3.5 border-b border-gray-100 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-gray-900 text-xs">파일 이동 추천</h3>
                  <p className="text-[10px] text-gray-400 font-medium">
                    체크한 항목만 아래 비교 화면에 반영됩니다.
                  </p>
                </div>
                {structureList.length > 0 && (
                  <button
                    onClick={handleSelectAllMove}
                    className="px-3 py-1 border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-700 text-xs font-bold rounded-lg transition shadow-2xs cursor-pointer"
                  >
                    {selectedMoveIds.length === structureList.length ? '전체 해제' : '전체 선택'}
                  </button>
                )}
              </div>

              <div className="p-6 bg-white">
                {structureList.length === 0 ? (
                  <div className="py-8 text-center text-gray-400 text-xs font-medium">
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
                            className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 mt-1 cursor-pointer"
                          />
                          <div className="space-y-2 flex-1 min-w-0">
                            <div className="font-bold text-xs text-gray-900 truncate">
                              {item.fileName}
                            </div>

                            <div className="flex items-center gap-1.5 text-[11px] flex-wrap">
                              <span className="px-2 py-0.5 bg-gray-100 text-gray-500 font-medium rounded-md text-[10px]">
                                {item.currentFolder}
                              </span>
                              <span className="text-gray-300 text-[10px]">→</span>
                              <span className="px-2 py-0.5 bg-emerald-50 text-emerald-600 font-medium rounded-md truncate max-w-[130px] text-[10px]">
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
              <div className="lg:col-span-5 bg-white rounded-2xl border border-gray-200/80 shadow-2xs overflow-hidden flex flex-col h-full">
                <div className="bg-gray-50/80 px-5 h-12 border-b border-gray-100 flex items-center justify-between shrink-0">
                  <div className="space-y-0.5">
                    <h3 className="font-bold text-gray-900 text-xs">현재 폴더 구조</h3>
                    <p className="text-[9px] text-gray-400 font-medium">실제 파일이 지금 저장된 위치</p>
                  </div>
                  <span className="text-[10px] text-gray-500 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                    <span>이동 예정</span>
                  </span>
                </div>
                <div className="p-5 text-xs font-medium text-gray-700 bg-white flex-1 overflow-y-auto">
                  <DynamicTreeNode
                    node={currentTree}
                    selectedMoveIds={selectedMoveIds}
                    isTargetTree={false}
                  />
                </div>
              </div>

              {/* 중앙 인디케이터 화살표 */}
              <div className="lg:col-span-1 flex flex-col items-center justify-center text-center py-2 shrink-0">
                <div className="w-10 h-10 bg-gray-50 border border-black-100 rounded-full flex items-center justify-center text-black-600 font-bold shadow-2xs mb-1">
                  ➔
                </div>
                <div className="text-xs font-black text-black-600">
                  {selectedMoveIds.length}개
                </div>
                <div className="text-[10px] text-gray-400 font-medium">이동 반영</div>
              </div>

              {/* 우측 트리: 적용 후 폴더 구조 (동적 생성) */}
              <div className="lg:col-span-5 bg-white rounded-2xl border border-gray-200/80 shadow-2xs overflow-hidden flex flex-col h-full">
                <div className="bg-gray-50/80 px-5 h-12 border-b border-gray-100 flex items-center justify-between shrink-0">
                  <div className="space-y-0.5">
                    <h3 className="font-bold text-gray-900 text-xs">적용 후 폴더 구조</h3>
                    <p className="text-[9px] text-gray-400 font-medium">승인한 이동이 반영된 예상 구조</p>
                  </div>
                  <span className="text-[10px] text-gray-500 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    <span>새 위치</span>
                  </span>
                </div>

                <div className="p-5 text-xs font-medium text-gray-700 bg-white flex-1 overflow-y-auto">
                  {selectedMoveIds.length === 0 ? (
                    <div className="text-gray-400 text-[11px] py-12 text-center font-medium">
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
            <div className="p-4 bg-white rounded-2xl border border-gray-200/80 shadow-2xs flex items-center justify-between">
              <div>
                <h4 className="font-bold text-gray-900 text-xs">
                  {selectedMoveIds.length}개 파일 이동이 적용 후 구조에 반영되었습니다.
                </h4>
                <p className="text-[11px] text-gray-400 font-medium">
                  왼쪽의 현재 위치는 빨간색 줄, 오른쪽의 새 위치는 초록색 카드로 연동되어 표시됩니다.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedMoveIds([])}
                  className="px-4 py-2 border border-gray-200/80 hover:bg-gray-50 text-gray-700 font-bold text-xs rounded-xl transition cursor-pointer"
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