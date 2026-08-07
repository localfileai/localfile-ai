import { useState } from 'react';
import type { SearchResult } from '../api/searchApi';
import { CATEGORIES, sendFeedback } from '../api/feedbackApi';
import DocumentPreview from './DocumentPreview';

interface Props {
  item: SearchResult;
  /** FE1이 인식한 폴더. 실제 검색 결과에는 전체 경로가 들어 있어 대개 쓰이지 않는다. */
  selectedPath?: string;
}

/** 실제 파일 경로. 실제 검색은 전체 경로를 그대로 주므로 그것을 우선한다. */
function resolvePath(item: SearchResult, selectedPath?: string): string {
  if (item.fullPath) return item.fullPath;
  const base = (selectedPath || item.path || '').replace(/[\\/]+$/, '');
  if (!base) return item.title;
  const separator = base.includes('\\') ? '\\' : '/';
  return `${base}${separator}${item.title}`;
}

export default function FileResultCard({ item, selectedPath }: Props) {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isLabeling, setIsLabeling] = useState(false);
  const [labelNote, setLabelNote] = useState('');

  const targetPath = resolvePath(item, selectedPath);

  // 파일명을 누르면 탐색기가 열리고 그 파일이 선택돼 있다.
  // 텍스트를 다시 보여 주는 것보다 "그래서 이게 어디 있는데"에 답하는 게 먼저다.
  const handleReveal = () => {
    void window.api?.revealFile?.(targetPath);
  };

  // 잘못 찾은 파일에 올바른 갈래를 알려 준다 — 다음 분류부터 이 사람 기준이 반영된다.
  const handleLabel = async (category: string) => {
    setIsLabeling(false);
    setLabelNote('저장 중…');
    try {
      await sendFeedback(targetPath, category);
      setLabelNote('알려 주셔서 고맙습니다. 다음부터 반영됩니다.');
    } catch (error) {
      setLabelNote((error as Error).message);
    }
    window.setTimeout(() => setLabelNote(''), 4000);
  };

  return (
    <>
      <div className="group flex items-start gap-3 py-3.5">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-indigo-100 dark:border-indigo-500/30 bg-indigo-50 dark:bg-indigo-500/15 text-[10px] font-bold text-indigo-600">
          {item.type}
        </div>

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <button
              onClick={handleReveal}
              title="탐색기에서 이 파일 보기"
              className="cursor-pointer truncate text-xs font-bold text-gray-800 dark:text-gray-100 transition hover:text-indigo-600 hover:underline"
            >
              {item.title}
            </button>
            <span className="shrink-0 rounded-md border border-indigo-100 dark:border-indigo-500/30 bg-indigo-50 dark:bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-bold text-indigo-600">
              {item.matchScore}
            </span>
          </div>

          <div
            className="truncate text-[10px] font-medium text-gray-400 dark:text-gray-500"
            title={targetPath}
          >
            {item.path} · {item.date}
          </div>

          <div className="pt-0.5 text-[11px] leading-relaxed text-gray-600 dark:text-gray-300">
            {item.snippetHighlight}
          </div>

          {/* 분류 고치기 — 맞춤화의 입구 */}
          {isLabeling ? (
            <div className="flex flex-wrap gap-1 pt-1">
              {CATEGORIES.map((category) => (
                <button
                  key={category.value}
                  onClick={() => void handleLabel(category.value)}
                  className="rounded-full border border-gray-200 dark:border-gray-700 px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:text-gray-300 hover:border-indigo-300 hover:text-indigo-600"
                >
                  {category.label}
                </button>
              ))}
              <button
                onClick={() => setIsLabeling(false)}
                className="px-1.5 text-[10px] text-gray-400 dark:text-gray-500 hover:text-gray-600"
              >
                취소
              </button>
            </div>
          ) : labelNote ? (
            <div className="pt-0.5 text-[10px] font-medium text-indigo-600">{labelNote}</div>
          ) : (
            <button
              onClick={() => setIsLabeling(true)}
              className="pt-0.5 text-[10px] text-gray-400 opacity-0 transition group-hover:opacity-100 hover:text-indigo-600 dark:text-gray-500"
            >
              이 파일 갈래 알려 주기
            </button>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1 pt-1">
          <button
            onClick={() => setIsPreviewOpen(true)}
            title="첫 페이지 미리보기"
            className="cursor-pointer rounded-lg border border-transparent p-2 text-gray-400 transition hover:border-gray-200 hover:text-indigo-600 dark:text-gray-500 dark:hover:border-gray-700"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
          </button>
          <button
            onClick={handleReveal}
            title="탐색기에서 보기"
            className="cursor-pointer rounded-lg border border-transparent p-2 text-gray-400 transition hover:border-gray-200 hover:text-indigo-600 dark:text-gray-500 dark:hover:border-gray-700"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
              <path d="M3 7h6l2 2.5h10V19H3z" />
            </svg>
          </button>
        </div>
      </div>

      {isPreviewOpen && (
        <DocumentPreview
          path={targetPath}
          name={item.title}
          onClose={() => setIsPreviewOpen(false)}
          onReveal={handleReveal}
        />
      )}
    </>
  );
}
