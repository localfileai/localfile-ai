import type { Menu } from '../types';

interface HeaderProps {
  currentMenu: Menu;
  /** FE1이 IPC/Drag&Drop으로 인식한 경로. 없으면 빈 문자열 */
  selectedPath?: string;
  /** FE1의 OS 네이티브 폴더 선택 창 호출 */
  onSelectFolder?: () => void;
}

const TITLES: Record<Menu, { title: string; description: string }> = {
  search: { title: '파일 찾기', description: '파일명 대신 내용과 날짜로 찾아보세요.' },
  rename: {
    title: '파일·폴더명 변경',
    description: '문서 내용에 맞는 이름을 제안합니다.',
  },
  organize: { title: '폴더 정리', description: '현재 구조와 변경 후 구조를 비교하세요.' },
  files: { title: '전체 보유 파일', description: '분석이 끝난 파일 목록입니다.' },
};

export default function Header({ currentMenu, selectedPath, onSelectFolder }: HeaderProps) {
  const { title, description } = TITLES[currentMenu];

  return (
    <div className="h-16 bg-white dark:bg-[#16161e] border-b border-gray-200/80 dark:border-gray-700 px-8 flex items-center justify-between shrink-0">
      <div className="min-w-0">
        <h2 className="text-base font-bold text-gray-900 dark:text-gray-50">{title}</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500">{description}</p>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {/* FE1이 인식한 실제 경로 */}
        {selectedPath && (
          <code
            title={selectedPath}
            className="max-w-[22rem] truncate rounded-lg bg-gray-50 dark:bg-white/5 px-2.5 py-1 text-[11px] text-gray-500 dark:text-gray-400 border border-gray-200/80 dark:border-gray-700"
          >
            {selectedPath}
          </code>
        )}

        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-50 dark:bg-emerald-500/15 text-emerald-600 border border-emerald-200/60">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
          <span>Local Ai</span>
        </div>

        <button
          onClick={onSelectFolder}
          className="flex items-center gap-2 px-3.5 py-1.5 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-white/5 rounded-xl text-xs font-medium text-gray-700 dark:text-gray-200 transition shadow-2xs cursor-pointer"
        >
          <img className="w-4 h-4" src="component-15.svg" alt="폴더 선택" />
          <span>폴더 선택</span>
        </button>
      </div>
    </div>
  );
}
