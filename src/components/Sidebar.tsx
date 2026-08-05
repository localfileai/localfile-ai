import type { Menu } from '../types';

// 💡 1. currentMenu 타입에 'files' 추가
interface SidebarProps {
  currentMenu: Menu;
  onMenuChange: (menu: Menu) => void;
  badgeCount: number;
  totalFiles: number;
  /** FE1이 인식한 폴더명. 선택 전에는 'Documents' */
  folderName?: string;
}

export default function Sidebar({
  currentMenu,
  onMenuChange,
  badgeCount,
  totalFiles,
  folderName = 'Documents',
}: SidebarProps) {
  return (
    <aside className="w-64 bg-[#F8F9FA] dark:bg-[#0d0d13] border-r border-gray-200/80 dark:border-gray-700 flex flex-col justify-between p-6 h-screen shrink-0">
      <div className="space-y-6">
        
        {/* 브랜딩 */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center shrink-0 shadow-xs">
            <img className="w-5 h-5" src="component-10.svg" alt="Logo" />
          </div>
          <div>
            <div className="font-bold text-base text-gray-900 dark:text-gray-50 leading-snug">LocalFile AI</div>
            <div className="text-[11px] text-gray-400 dark:text-gray-500 font-medium">Local document manager</div>
          </div>
        </div>

        {/* 메뉴 네비게이션 */}
        <div className="pt-2">
          <div className="text-[11px] font-bold text-gray-400 dark:text-gray-500 tracking-wider uppercase mb-3 px-1">
            Workspace
          </div>
          <nav className="space-y-1.5">
            <button
              onClick={() => onMenuChange('search')}
              className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition cursor-pointer ${
                currentMenu === 'search' ? 'bg-indigo-50/80 text-indigo-600' : 'text-gray-500 hover:bg-gray-100/60'
              }`}
            >
              <img className="w-4 h-4" src="component-11.svg" alt="파일 찾기" />
              <span>파일 찾기</span>
            </button>

            <button
              onClick={() => onMenuChange('organize')}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl font-semibold text-xs transition cursor-pointer ${
                currentMenu === 'organize' ? 'bg-indigo-50/80 text-indigo-600' : 'text-gray-500 hover:bg-gray-100/60'
              }`}
            >
              <div className="flex items-center gap-3">
                <img className="w-4 h-4 text-gray-400 dark:text-gray-500" src="component-12.svg" alt="폴더 정리" />
                <span>폴더 정리</span>
              </div>
              {badgeCount > 0 && (
                <span className="px-2 py-0.5 text-[10px] bg-indigo-100 dark:bg-indigo-500/25 text-indigo-600 font-bold rounded-full">
                  {badgeCount}
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* 💡 2. 현재 폴더 정보 카드를 '전체 보유 파일' 보기 클릭 버튼으로 변경 */}
        <button
          onClick={() => onMenuChange('files')}
          className={`w-full text-left p-4 rounded-2xl border transition cursor-pointer space-y-1.5 ${
            currentMenu === 'files'
              ? 'bg-indigo-50/80 border-indigo-300 ring-2 ring-indigo-500/20'
              : 'bg-white border-gray-200/80 hover:border-gray-300 shadow-2xs'
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold text-gray-700 dark:text-gray-200">
              <img className="w-4 h-4" src="component-13.svg" alt="현재 폴더" />
              <span>현재 폴더</span>
            </div>
            <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 dark:bg-indigo-500/15 px-1.5 py-0.5 rounded">
              전체 보기
            </span>
          </div>
          <div className="font-semibold text-gray-800 dark:text-gray-100 text-xs truncate" title={folderName}>
            {folderName || '아직 고르지 않음'}
          </div>
          <div className="text-[11px] text-gray-400 dark:text-gray-500">
            {folderName
              ? `${totalFiles}개 파일 · 이 PC에서 분석`
              : '오른쪽 위 [폴더 선택]을 눌러 주세요'}
          </div>
        </button>
      </div>

      {/* 보안 안내 */}
      <div className="flex items-start gap-2 text-[11px] text-gray-400 dark:text-gray-500 leading-tight px-1">
        <img className="w-4 h-4 shrink-0 mt-0.5" src="component-14.svg" alt="보안" />
        <div className="break-keep">문서와 임베딩 데이터는 사용자의 PC 내부에만 저장됩니다.</div>
      </div>
    </aside>
  );
}