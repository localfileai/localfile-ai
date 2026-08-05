import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
  fetchRealSearchResults,
  fetchSearchStatus,
  type SearchResult,
  type SearchStatus,
} from '../api/searchApi';
import {
  fetchIndexProgress,
  formatEta,
  startIndexing,
  type IndexProgress,
} from '../api/indexApi';
import { listFolderFiles, type FolderFile } from '../api/filesApi';
import FileResultCard from './FileResultCard';

/** 기획안이 정한 지원 문서 형식 7종 (backend contracts/ai.py의 ALLOWED_EXTENSIONS와 같다). */
const SUPPORTED_TYPES = ['PDF', 'DOCX', 'DOC', 'PPTX', 'PPT', 'HWP', 'HWPX'];

interface MainViewProps {
  /** FE1이 IPC/Drag&Drop으로 인식한 폴더 경로 */
  selectedPath?: string;
}

export default function MainView({ selectedPath }: MainViewProps) {
  // 이 폴더에 이미 색인을 걸었는지 기억한다. 화면을 오갈 때마다 다시 걸면
  // Ollama가 그 작업들로 막혀 검색이 계속 "준비 중"에 머무른다.
  const indexRequestedFor = useRef('');
  // 새로고침을 누를 때마다 올린다. 이 값이 바뀌면 목록·색인이 다시 돈다.
  const [refreshToken, setRefreshToken] = useState(0);
  // 선택한 폴더에서 실제로 추출된 문서.
  // 검색 결과(Mock)와 달리 이건 진짜 파일에서 뽑은 텍스트입니다.
  const [realDocs, setRealDocs] = useState<FolderFile[]>([]);
  const [realDocsTotal, setRealDocsTotal] = useState(0);
  const [realDocsError, setRealDocsError] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);

  // 폴더가 바뀌면 이전 폴더의 목록·검색 결과를 즉시 버린다.
  // 남겨 두면 새 폴더를 고른 뒤에도 예전 파일이 보인다.
  useEffect(() => {
    setRealDocs([]);
    setRealDocsTotal(0);
    setRealDocsError('');
    setSearchResults([]);
    setHasSearched(false);
    setSearchError('');
    setIndexProgress(null);

    if (!selectedPath) return;

    let cancelled = false;
    setIsExtracting(true);

    listFolderFiles(selectedPath)
      .then(({ items, total, error }) => {
        if (cancelled) return;
        setRealDocs(items);
        setRealDocsTotal(total);
        setRealDocsError(error);
      })
      .finally(() => {
        // finally가 없으면 실패했을 때 로딩 표시가 영원히 남는다
        if (!cancelled) setIsExtracting(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedPath, refreshToken]);

  // 1. 검색 상태(State)
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const [searchStatus, setSearchStatus] = useState<SearchStatus | null>(null);
  const [searchError, setSearchError] = useState('');
  const [elapsedMs, setElapsedMs] = useState(0);
  const [indexProgress, setIndexProgress] = useState<IndexProgress | null>(null);
  const [indexError, setIndexError] = useState('');

  const refreshSearchStatus = useCallback(async () => {
    const status = await fetchSearchStatus();
    if (status) setSearchStatus(status);
  }, []);

  useEffect(() => {
    void refreshSearchStatus();
  }, [refreshSearchStatus]);

  // 폴더를 고르면 색인을 시작한다.
  // 사용자가 "색인"이라는 개념을 알 필요는 없다 — 폴더를 고른다 = 검색 준비다.
  //
  // 이미 돌고 있으면 다시 부르지 않는다. 예전에는 그대로 요청해 409를 받았고,
  // 무해하긴 해도 콘솔에 실패로 남아 진짜 문제를 찾기 어렵게 만들었다.
  useEffect(() => {
    if (!selectedPath || indexRequestedFor.current === selectedPath) return;
    indexRequestedFor.current = selectedPath;
    let cancelled = false;

    fetchIndexProgress().then((progress) => {
      if (cancelled || progress?.running) return;
      setIndexError('');
      startIndexing(selectedPath).then((error) => {
        if (!cancelled && error) setIndexError(error);
      });
    });

    return () => {
      cancelled = true;
    };
  }, [selectedPath, refreshToken]);

  // 색인이 도는 동안 진행률을 따라간다. 끝나면 검색 상태를 다시 읽어
  // "검색할 수 없음"에서 "검색 준비됨"으로 화면이 저절로 바뀌게 한다.
  //
  // 끝난 뒤에도 계속 물어보지는 않는다. 다만 색인이 막 시작하는 순간에는 아직
  // running=false로 보일 수 있어, 몇 번은 더 확인한 뒤에 멈춘다.
  useEffect(() => {
    if (!selectedPath) return;
    let cancelled = false;
    let timer = 0;
    let idleTicks = 0;

    const tick = async () => {
      const progress = await fetchIndexProgress();
      if (cancelled) return;
      if (progress) {
        setIndexProgress(progress);
        idleTicks = progress.running ? 0 : idleTicks + 1;
        if (!progress.running) void refreshSearchStatus();
      }
      if (idleTicks < 4) timer = window.setTimeout(tick, 1500);
    };

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [selectedPath, refreshSearchStatus, refreshToken]);

  // 2. 필터 상태(State)
  const [selectedTypes, setSelectedTypes] = useState<string[]>(SUPPORTED_TYPES);
  const [selectedTargets, setSelectedTargets] = useState<string[]>(['title', 'content', 'path']);
  // 기간은 달력으로 직접 고른다. '최근 1주일/1개월' 두 가지로는
  // "지난 학기" 같은 실제 필요를 못 맞춘다.
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortOrder, setSortOrder] = useState<string>('관련도순');

  // 색인 중에는 검색을 막는다.
  // Ollama가 요청을 하나씩 처리하므로, 색인이 도는 동안 검색을 보내면 그 뒤에
  // 줄을 서서 응답이 몇 분씩 걸린다. 사용자에게는 "검색이 안 되는" 것으로 보인다.
  // 진행률이 **지금 고른 폴더**의 것인지 확인한다. 폴더를 바꾸면 백엔드에는
  // 아직 이전 폴더의 완료 상태가 남아 있어, 그대로 믿으면 새 폴더를 읽지도
  // 않고 "준비 완료"가 된다.
  const sameFolder = (a: string, b: string) =>
    a.replace(/[\\/]+$/, '').toLowerCase() === b.replace(/[\\/]+$/, '').toLowerCase();
  const progressIsCurrent = Boolean(
    indexProgress && selectedPath && sameFolder(indexProgress.path, selectedPath),
  );
  const isIndexing = Boolean(indexProgress?.running && progressIsCurrent);

  // 추출과 색인은 내부적으로 다른 단계지만 사용자에게는 하나의 기다림이다.
  // 둘 중 무엇이든 돌고 있으면 "준비 중"으로 묶어 진행 표시만 보여 준다.
  const isPreparing = isExtracting || isIndexing;
  const isBusy = isPreparing || isLoading;

  // 이번에 고른 폴더의 색인이 끝났는가.
  // 예전 색인이 남아 있으면 searchStatus.ready는 폴더를 고르자마자 true가 되어,
  // 아직 읽지도 않은 폴더를 두고 "준비 완료"라고 말하게 된다.
  const indexFinished = Boolean(progressIsCurrent && indexProgress
                                && !indexProgress.running && indexProgress.finished_at);
  const searchReady = Boolean(searchStatus?.ready) && indexFinished && !isPreparing;

  // 3. 검색 실행 함수
  const executeSearch = async (query: string) => {
    if (!query.trim() || isPreparing) return;

    setIsLoading(true);
    setSearchError('');
    try {
      // 질의를 임베딩해 색인에서 의미가 가까운 문서를 찾는다 (전부 이 PC 안에서).
      const outcome = await fetchRealSearchResults(query, 30, selectedPath);
      setSearchResults(outcome.results);
      setSearchError(outcome.error);
      setElapsedMs(outcome.elapsedMs);
      setHasSearched(true);
    } catch (error) {
      console.error('검색 중 오류 발생:', error);
      setSearchResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  // 핸들러 함수들
  const handleSearchClick = () => executeSearch(searchTerm);

  // 폴더 목록과 색인을 다시 읽는다. 폴더 안의 파일이 바뀌었을 때 쓴다.
  const handleRefresh = () => {
    indexRequestedFor.current = '';
    setSearchResults([]);
    setHasSearched(false);
    setSearchError('');
    setRefreshToken((token) => token + 1);
  };
  const handleChipClick = (keyword: string) => {
    setSearchTerm(keyword);
    executeSearch(keyword);
  };

  // [필터 토글] 파일 형식
  const handleTypeToggle = (type: string) => {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  // [필터 토글] 검색 대상
  const handleTargetToggle = (target: string) => {
    setSelectedTargets((prev) =>
      // 원본은 `[...prev, t]`였습니다. `t`는 위 filter 콜백의 인자라 이 위치에서는
      // 존재하지 않습니다. 검색 대상 칩을 누르면 터지는 버그였고 타입체크가 잡았습니다.
      prev.includes(target) ? prev.filter((t) => t !== target) : [...prev, target]
    );
  };

  // 필터링 및 정렬된 결과 실시간 계산
  const filteredResults = useMemo(() => {
    if (!searchResults || searchResults.length === 0) return [];

    // 검색 대상 필터에 쓸 질의 낱말. 한 글자는 아무 데나 걸려 의미가 없다.
    const tokens = searchTerm
      .toLowerCase()
      .split(/\s+/)
      .filter((token) => token.length > 1);

    let list = searchResults.filter((item) => {
      // 알 수 없는 확장자가 와도 결과가 통째로 사라지지 않게 한다
      const isTypeMatched =
        selectedTypes.includes(item.type) || !SUPPORTED_TYPES.includes(item.type);

      // 기간: 달력에서 고른 범위 안의 수정일만
      const isDateMatched =
        (!dateFrom || (item.date && item.date >= dateFrom)) &&
        (!dateTo || (item.date && item.date <= dateTo));

      // 검색 대상: 고른 곳 중 하나라도 질의 낱말을 품고 있어야 한다.
      // 셋 다 골랐거나 질의가 짧으면 의미 검색 결과를 그대로 둔다.
      let isTargetMatched = true;
      if (selectedTargets.length === 0) {
        isTargetMatched = false;
      } else if (selectedTargets.length < 3 && tokens.length > 0) {
        isTargetMatched = selectedTargets.some((target) => {
          const haystack =
            target === 'title' ? item.title
              : target === 'content' ? item.snippetHighlight
                : `${item.path} ${item.date}`;
          return tokens.some((token) => haystack.toLowerCase().includes(token));
        });
      }

      return isTypeMatched && isDateMatched && isTargetMatched;
    });

    if (sortOrder === '최신순') {
      list = [...list].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }

    return list;
  }, [searchResults, selectedTypes, selectedTargets, dateFrom, dateTo, sortOrder, searchTerm]);

  return (
    <div className="flex-1 overflow-y-auto bg-white dark:bg-[#16161e] p-8">
      <div className="div-search-view">
        <div className="max-w-5xl mx-auto space-y-10">
          
          {/* 상단 검색 헤더 영역 */}
          <div className="text-center space-y-3 pt-4">
            <div className="text-[10px] font-bold text-indigo-600 tracking-widest uppercase bg-indigo-50 dark:bg-indigo-500/15 px-3 py-1 rounded-full inline-block">
              <div>Semantic file search</div>
            </div>
            <div className="text-2xl font-extrabold text-gray-900 dark:text-gray-50 tracking-tight">
              <div>무슨 파일인지 설명 해보세요.</div>
            </div>
            <div className="text-xs text-gray-400 dark:text-gray-500 max-w-md mx-auto">
              <div>
                문서 내용, 파일명, 경로, 수정일을 함께 분석해 파일을 찾습니다.
              </div>
            </div>

            {/* 준비 상태 — 추출과 색인을 하나의 진행 표시로 이어 보여 준다 */}
            <div className="mx-auto max-w-md text-[11px]">
              {isPreparing ? (
                <div className="text-indigo-600">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium">
                      {isExtracting
                        ? '폴더의 문서를 살펴보는 중입니다'
                        : '문서를 읽고 있습니다'}
                      {!isExtracting && (indexProgress?.total ?? 0) > 0 &&
                        ` · ${indexProgress?.processed}/${indexProgress?.total}건`}
                    </span>
                    <span className="text-gray-400 dark:text-gray-500">
                      {isExtracting ? '' : formatEta(indexProgress?.eta_sec ?? null)}
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-500/25">
                    {isExtracting || !(indexProgress?.total ?? 0) ? (
                      // 아직 몇 건인지 모르는 단계 — 흐르는 막대로 진행 중임을 보여 준다
                      <div className="h-full w-1/3 rounded-full bg-indigo-500 animate-[loading_1.2s_ease-in-out_infinite]" />
                    ) : (
                      <div
                        className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                        style={{
                          width: `${Math.min(
                            100,
                            ((indexProgress?.processed ?? 0) / (indexProgress?.total || 1)) * 100,
                          )}%`,
                        }}
                      />
                    )}
                  </div>
                  <div className="mt-1 text-gray-400 dark:text-gray-500">
                    끝나면 바로 검색할 수 있습니다.
                  </div>
                </div>
              ) : indexError ? (
                <span className="text-red-500">{indexError}</span>
              ) : !selectedPath ? (
                // 색인이 남아 있어도 폴더를 고르기 전에는 "준비 완료"라고 하지 않는다.
                // 사용자 입장에서 아무것도 고르지 않았는데 준비됐다는 건 앞뒤가 안 맞는다.
                <span className="text-amber-600">
                  오른쪽 위 <b>[폴더 선택]</b>으로 정리할 폴더를 고르면 검색을 준비합니다.
                </span>
              ) : searchReady ? (
                <span className="text-emerald-600">
                  문서 {searchStatus?.indexed_documents.toLocaleString()}건 검색 준비 완료
                </span>
              ) : (
                <span className="text-gray-400 dark:text-gray-500">문서를 확인하는 중입니다…</span>
              )}
            </div>

            {selectedPath && !isPreparing && (
              <button
                onClick={handleRefresh}
                className="text-[11px] font-medium text-gray-400 hover:text-indigo-600 dark:text-gray-500"
              >
                ↻ 폴더 다시 읽기
              </button>
            )}

            {/* 검색어 입력 폼 */}
            <div className="max-w-2xl mx-auto pt-2">
              <div className="flex items-center shadow-sm rounded-2xl bg-white dark:bg-[#16161e] border border-gray-200/90 dark:border-gray-700 p-1.5 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100 transition">
                <img className="w-4 h-4 ml-3 opacity-40" src="component-16.svg" alt="검색" />
                <div className="w-full px-3 py-2">
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearchClick()}
                    disabled={isPreparing}
                    placeholder={
                      isPreparing
                        ? '문서를 읽는 중입니다. 끝나면 검색할 수 있습니다.'
                        : '예: 2025년에 진행한 프로젝트 자료를 찾아줘'
                    }
                    className="w-full text-xs bg-transparent focus:outline-none text-gray-800 dark:text-gray-100 placeholder-gray-300 font-medium caret-indigo-600 disabled:cursor-not-allowed"
                  />
                </div>
                <button
                  onClick={handleSearchClick}
                  disabled={isLoading || isPreparing}
                  title={isPreparing ? '문서를 읽는 중입니다. 끝나면 검색할 수 있습니다.' : ''}
                  className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 disabled:cursor-not-allowed text-white font-semibold text-xs rounded-xl transition shrink-0 cursor-pointer"
                >
                  <div>{isPreparing ? '준비 중' : isLoading ? '검색 중...' : '검색'}</div>
                </button>
              </div>
            </div>

            {/* 추천 키워드 칩 */}
            <div className="flex items-center justify-center gap-2 pt-1 text-xs">
              {/* 특정 과목·주제를 박아 두면 대부분의 사용자에게는 맞지 않는 예시가 된다.
                  누구 폴더에나 있을 법한 문서 종류로 둔다. */}
              {['과제 보고서', '강의 자료', '발표 슬라이드', '시험 정리 노트'].map((chip) => (
                <button
                  key={chip}
                  onClick={() => handleChipClick(chip)}
                  className="px-3 py-1.5 bg-white dark:bg-[#16161e] border border-gray-200/80 dark:border-gray-700 rounded-full text-[11px] text-gray-500 dark:text-gray-400 hover:border-indigo-300 hover:text-indigo-600 transition shadow-2xs font-medium cursor-pointer"
                >
                  <div>{chip}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 폴더 안의 문서 목록.
              추출·색인·검색이 도는 동안에는 감춘다 — 그때는 진행 상황만 보여야
              사용자가 "지금 뭘 기다리는지"를 헷갈리지 않는다. */}
          {selectedPath && !isBusy && (
            <div className="bg-white dark:bg-[#16161e] rounded-2xl border border-emerald-200/70 dark:border-emerald-500/30 shadow-2xs overflow-hidden">
              <div className="bg-emerald-50/60 dark:bg-emerald-500/15 px-6 h-13 border-b border-emerald-100 dark:border-emerald-500/30 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <div className="font-bold text-gray-900 dark:text-gray-50 text-xs">폴더 내 전체 문서</div>
                  <div className="text-[11px] text-emerald-700">
                    {realDocsError
                      ? '읽지 못했습니다'
                      : realDocsTotal > realDocs.length
                        ? `${realDocs.length}건 표시 (전체 ${realDocsTotal}건)`
                        : `${realDocs.length}건`}
                  </div>
                </div>
                <code
                  className="max-w-[26rem] truncate text-[10px] text-gray-400 dark:text-gray-500"
                  title={selectedPath}
                >
                  {selectedPath}
                </code>
              </div>

              <div className="p-6">
                {realDocsError ? (
                  <div className="py-4 text-[11px] leading-relaxed text-red-600">{realDocsError}</div>
                ) : realDocs.length === 0 ? (
                  <div className="py-4 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                    이 폴더 바로 아래에 읽을 수 있는 문서가 없습니다.
                    <br />
                    PDF · DOCX · DOC · PPTX · PPT · HWP · HWPX 를 지원하며, 하위 폴더는 보지 않습니다.
                  </div>
                ) : (
                  // 파일이 많아도 창 밖으로 밀려나지 않게 이 목록 안에서만 스크롤한다
                  <div className="max-h-[22rem] overflow-y-auto pr-1 divide-y divide-gray-100 dark:divide-gray-700/70">
                    {realDocs.map((doc) => (
                      <div key={doc.path} className="py-3">
                        <button
                          onClick={() => void window.api?.revealFile?.(doc.path)}
                          title="탐색기에서 이 파일 보기"
                          className="flex w-full items-start gap-3 text-left cursor-pointer"
                        >
                          <div className="mt-0.5 w-9 h-9 shrink-0 rounded-xl border border-emerald-100 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/15 text-[10px] font-bold text-emerald-600 flex items-center justify-center">
                            {doc.extension.toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-xs font-bold text-gray-800 dark:text-gray-100">{doc.name}</div>
                            <div className="mt-0.5 truncate text-[11px] text-gray-500 dark:text-gray-400">
                              {doc.folder ? `${doc.folder} · ` : ''}
                              {doc.modified_at.slice(0, 10)}
                            </div>
                          </div>
                          <div className="shrink-0 pt-1 text-[10px] font-bold text-emerald-600">
                            폴더 열기
                          </div>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 💡 1. items-stretch로 변경하여 좌우 두 박스의 전체 높이를 100% 동일하게 맞춤 */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-stretch">
            
            {/* 좌측 패널: 검색 결과 (상단 연회색 / 하단 흰색 분리) */}
            <div className="lg:col-span-3 bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 min-h-120 flex flex-col shadow-2xs overflow-hidden">
              
              {/* 💡 2. h-13 고정 및 동일 높이 정렬 적용 (검색 결과 상단바) */}
              <div className="bg-gray-50/80 dark:bg-white/5 px-6 h-13 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <div className="font-bold text-gray-900 dark:text-gray-50 text-xs">
                    <div>검색 결과</div>
                  </div>
                  <div className="text-[11px] text-gray-400 dark:text-gray-500">
                    <div>
                      {isLoading
                        ? '내용이 비슷한 문서를 찾는 중...'
                        : hasSearched
                        ? `${filteredResults.length}개의 관련 파일` +
                          (elapsedMs ? ` · ${elapsedMs}ms` : '')
                        : ''}
                    </div>
                  </div>
                </div>

                <div>
                  <div className="select-sort-select">
                    <select
                      value={sortOrder}
                      onChange={(e) => setSortOrder(e.target.value)}
                      className="text-[11px] text-gray-600 dark:text-gray-300 border border-gray-200/80 dark:border-gray-700 rounded-lg px-2.5 py-1 focus:outline-none bg-white dark:bg-[#16161e] font-medium cursor-pointer shadow-2xs"
                    >
                      <option value="관련도순">관련도순</option>
                      <option value="최신순">최신순</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* [검색 결과 하단 컨텐츠] */}
              <div className="p-6 flex-1 bg-white dark:bg-[#16161e] flex flex-col">
                {/* 실제 검색이 준비되지 않았을 때 이유를 그대로 보여 준다 */}
                {searchError && (
                  <div className="mb-4 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/15 px-4 py-3 text-[11px] leading-relaxed text-amber-800">
                    {searchError}
                  </div>
                )}
                {isLoading ? (
                  <div className="flex-1 flex flex-col items-center justify-center py-12">
                    <div className="w-56">
                      {/* 진행률을 알 수 없는 작업이라 흐르는 막대로 "돌고 있음"을 보여 준다 */}
                      <div className="h-1.5 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-500/25">
                        <div className="h-full w-1/3 rounded-full bg-indigo-500 animate-[loading_1.2s_ease-in-out_infinite]" />
                      </div>
                    </div>
                    <div className="mt-3 text-xs font-medium text-gray-600 dark:text-gray-300">
                      내용이 비슷한 문서를 찾는 중입니다
                    </div>
                    <div className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">보통 1초 안에 끝납니다.</div>
                  </div>
                ) : !hasSearched ? (
                  <div className="flex-1 flex flex-col items-center justify-center text-center my-auto py-12">
                    <div className="w-12 h-12 bg-indigo-50/80 dark:bg-indigo-500/15 rounded-2xl flex items-center justify-center mb-3 mx-auto">
                      <img className="w-5 h-5 opacity-70" src="component-17.svg" alt="결과 없음" />
                    </div>
                    <div className="font-bold text-gray-800 dark:text-gray-100 text-sm mb-1">
                      <div>아직 검색한 내용이 없어요</div>
                    </div>
                    <div className="text-[11px] text-gray-400 dark:text-gray-500">
                      위 검색창에 기억나는 내용이나 날짜를 입력해 보세요.
                    </div>
                  </div>
                ) : filteredResults.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center text-center my-auto py-12">
                    <div className="w-12 h-12 bg-gray-100 dark:bg-white/10 rounded-2xl flex items-center justify-center mb-3 mx-auto">
                      <img className="w-5 h-5 opacity-40" src="component-17.svg" alt="결과 없음" />
                    </div>
                    <div className="font-bold text-gray-800 dark:text-gray-100 text-sm mb-1">
                      <div>일치하는 검색 결과가 없어요</div>
                    </div>
                    <div className="text-[11px] text-gray-400 dark:text-gray-500">
                      필터 조건에 일치하는 문서를 찾지 못했습니다. 우측 필터를 변경해 보세요.
                    </div>
                  </div>
                ) : (
                  // 결과가 많아도 페이지 전체가 길어지지 않게 목록 안에서 스크롤한다
                  <div className="div-results max-h-[32rem] overflow-y-auto pr-1 divide-y divide-gray-100 dark:divide-gray-700/70">
                    {filteredResults.map((item) => (
                      <FileResultCard key={item.id} item={item} selectedPath={selectedPath} />
                    ))}
                  </div>
                )}
              </div>

            </div>

            {/* 우측 패널: 필터 (상단 연회색 / 하단 흰색 분리) */}
            <div className="bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-2xs overflow-hidden flex flex-col">
              
              {/* 💡 2. h-13 고정 및 동일 높이 정렬 적용 (필터 상단바) */}
              <div className="bg-gray-50/80 dark:bg-white/5 px-5 h-13 border-b border-gray-100 dark:border-gray-700/70 flex items-center justify-between shrink-0">
                <div className="font-bold text-gray-900 dark:text-gray-50 text-xs">
                  <div>필터</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">검색 범위</span>
                  <button
                    onClick={() => {
                      setSelectedTypes(SUPPORTED_TYPES);
                      setSelectedTargets(['title', 'content', 'path']);
                      setDateFrom('');
                      setDateTo('');
                    }}
                    className="text-[10px] text-indigo-600 hover:underline font-semibold cursor-pointer"
                  >
                    초기화
                  </button>
                </div>
              </div>

              {/* [필터 하단 옵션] */}
              <div className="p-5 space-y-4 bg-white dark:bg-[#16161e] flex-1 flex flex-col justify-between">
                <div className="space-y-4">
                  {/* ① 파일 형식 */}
                  <div className="space-y-2">
                    <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">
                      <div>파일 형식</div>
                    </div>
                    <div className="grid grid-cols-2 gap-x-2 gap-y-1.5">
                      {SUPPORTED_TYPES.map((type) => (
                        <label key={type} className="flex items-center gap-2 cursor-pointer text-xs text-gray-600 dark:text-gray-300 font-medium">
                          <input
                            type="checkbox"
                            checked={selectedTypes.includes(type)}
                            onChange={() => handleTypeToggle(type)}
                            className="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                          />
                          <div>{type}</div>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* ② 검색 대상 */}
                  <div className="space-y-2 pt-3 border-t border-gray-100 dark:border-gray-700/70">
                    <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">
                      <div>검색 대상</div>
                    </div>
                    {[
                      { id: 'title', label: '파일명' },
                      { id: 'content', label: '문서 내용' },
                      { id: 'path', label: '경로·수정일' },
                    ].map((target) => (
                      <label key={target.id} className="flex items-center gap-2 cursor-pointer text-xs text-gray-600 dark:text-gray-300 font-medium">
                        <input
                          type="checkbox"
                          checked={selectedTargets.includes(target.id)}
                          onChange={() => handleTargetToggle(target.id)}
                          className="w-3.5 h-3.5 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                        />
                        <div>{target.label}</div>
                      </label>
                    ))}
                  </div>

                  {/* ③ 기간 */}
                  <div className="space-y-2 pt-3 border-t border-gray-100 dark:border-gray-700/70">
                    <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500">
                      <div>기간</div>
                    </div>
                    <div className="space-y-1.5">
                      <label className="flex items-center gap-2">
                        <span className="w-8 shrink-0 text-[10px] text-gray-400 dark:text-gray-500">부터</span>
                        <input
                          type="date"
                          value={dateFrom}
                          max={dateTo || undefined}
                          onChange={(event) => setDateFrom(event.target.value)}
                          className="w-full rounded-xl border border-gray-200/80 dark:border-gray-700 bg-white dark:bg-[#16161e] p-2 text-[11px] font-medium text-gray-600 dark:text-gray-300 focus:outline-none"
                        />
                      </label>
                      <label className="flex items-center gap-2">
                        <span className="w-8 shrink-0 text-[10px] text-gray-400 dark:text-gray-500">까지</span>
                        <input
                          type="date"
                          value={dateTo}
                          min={dateFrom || undefined}
                          onChange={(event) => setDateTo(event.target.value)}
                          className="w-full rounded-xl border border-gray-200/80 dark:border-gray-700 bg-white dark:bg-[#16161e] p-2 text-[11px] font-medium text-gray-600 dark:text-gray-300 focus:outline-none"
                        />
                      </label>
                      {(dateFrom || dateTo) && (
                        <button
                          onClick={() => { setDateFrom(''); setDateTo(''); }}
                          className="text-[10px] text-indigo-600 hover:underline"
                        >
                          기간 지우기
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* 하단 안내 */}
                <div className="p-3 bg-gray-50/80 dark:bg-white/5 rounded-xl text-[10px] text-gray-400 dark:text-gray-500 leading-relaxed border border-gray-100 dark:border-gray-700/70 mt-4">
                  <div>
                    검색 결과에는 질문과 일치한 문장, 실제 파일 경로, 관련도가 함께 표시됩니다.
                  </div>
                </div>

              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}