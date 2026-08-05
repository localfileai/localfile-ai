// src/components/AllFilesView.tsx
// jsx: "react-jsx" 설정이라 React 기본 import가 필요하지 않습니다.
// tsconfig의 noUnusedLocals가 사용하지 않는 import를 오류로 잡습니다.

import type { CurrentFileItem } from '../api/organizeApi';

interface AllFilesViewProps {
  currentFiles?: CurrentFileItem[];
}

export default function AllFilesView({ currentFiles = [] }: AllFilesViewProps) {
  const fileList = Array.isArray(currentFiles) ? currentFiles : [];

  return (
    <div className="flex-1 overflow-y-auto bg-[#F8F9FA] dark:bg-[#0d0d13] p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        
        {/* 헤더 */}
        <div className="space-y-1">
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-50">현재 폴더 보유 파일 목록</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            로컬 디렉터리(Documents)에서 스캔된 전체 문서 리스트입니다. (총 {fileList.length}개)
          </p>
        </div>

        {/* 파일 카드/테이블 박스 */}
        <div className="bg-white dark:bg-[#16161e] rounded-2xl border border-gray-200/80 dark:border-gray-700 p-6 shadow-2xs space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-700/70 text-[11px] text-gray-400 dark:text-gray-500 font-bold">
                  <th className="pb-3 w-16">형식</th>
                  <th className="pb-3">파일명</th>
                  <th className="pb-3">현재 경로</th>
                  <th className="pb-3 text-right w-20">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700/70 text-xs">
                {fileList.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-12 text-center text-gray-400 dark:text-gray-500">
                      불러온 파일이 없습니다.
                    </td>
                  </tr>
                ) : (
                  fileList.map((file) => (
                    <tr key={file.id} className="hover:bg-gray-50/60 transition">
                      <td className="py-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0 ${
                            file.ext === 'PDF'
                              ? 'bg-red-50 text-red-500 border border-red-100'
                              : file.ext === 'TXT'
                              ? 'bg-blue-50 text-blue-500 border border-blue-100'
                              : 'bg-emerald-50 text-emerald-600 border border-emerald-100'
                          }`}
                        >
                          {file.ext}
                        </span>
                      </td>
                      <td className="py-3 pr-3 font-bold text-gray-800 dark:text-gray-100">{file.name}</td>
                      <td className="py-3 pr-3 text-gray-400 dark:text-gray-500 font-mono text-[11px]">
                        {file.path}
                      </td>
                      <td className="py-3 text-right">
                        <span className="px-2 py-0.5 bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300 font-bold text-[10px] rounded-md">
                          분석 완료
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}