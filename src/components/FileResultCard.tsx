import { useState } from 'react';
import type { SearchResult } from '../api/searchApi';
import { getPreprocessPreview, type PreviewItem } from '../api/preprocessApi';

interface Props {
  item: SearchResult;
  /** FE1이 인식한 폴더. 있으면 이 폴더 안에서 파일을 찾습니다. */
  selectedPath?: string;
}

/**
 * 백엔드에 보낼 파일 경로를 만든다.
 *
 * 원본 코드는 `item.path`(= 폴더 경로)에 확장자를 붙여 보내고 있었습니다.
 *   "Documents/연구/TSN"  ->  "Documents/연구/TSN.pdf"
 * 파일명(`item.title`)이 빠져 있고 폴더에 확장자를 붙인 값이라 항상 실패합니다.
 *
 * 파일명을 붙이고, 폴더가 선택돼 있으면 그 폴더를 기준으로 삼습니다.
 */
function buildTargetPath(item: SearchResult, selectedPath?: string): string {
  // 실제 검색(`/search`)은 파일의 전체 경로를 그대로 줍니다. 조립할 필요가 없습니다.
  if (item.fullPath) return item.fullPath;

  const fileName = item.title;
  const base = (selectedPath || item.path || '').replace(/[\\/]+$/, '');
  if (!base) return fileName;

  // 선택 경로는 Windows면 역슬래시, Mock 경로는 슬래시를 씁니다.
  const separator = base.includes('\\') ? '\\' : '/';
  return `${base}${separator}${fileName}`;
}

export default function FileResultCard({ item, selectedPath }: Props) {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewResult, setPreviewResult] = useState<PreviewItem | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleOpenPreview = async () => {
    setIsPreviewOpen(true);

    if (!previewResult) {
      setIsLoading(true);

      const targetPath = buildTargetPath(item, selectedPath);
      console.log('백엔드로 전송하는 파일 경로:', targetPath);

      const res = await getPreprocessPreview(targetPath);

      if (res) {
        setPreviewResult({
          path: targetPath,
          name: item.title,
          extension: item.type,
          preview_text: res.first_page_text || res.text || res.content || '',
        });
      } else {
        // 왜 실패했는지 알려 줍니다.
        const hint = item.fullPath
          ? `색인된 파일을 찾지 못했습니다. 데이터셋이 삭제됐거나 이동했을 수 있습니다.`
          : selectedPath
          ? `선택한 폴더에 "${item.title}" 이 없습니다.`
          : '폴더를 먼저 선택하거나, 검색 엔진을 "실제 검색"으로 바꾸세요. 지금은 Mock의 예시 경로로 찾고 있습니다.';

        setPreviewResult({
          path: targetPath,
          name: item.title,
          extension: item.type,
          preview_text:
            `${hint}\n\n시도한 경로:\n${targetPath}\n\n` +
            '1주차 검색 결과는 하드코딩된 Mock이라 이 파일명이 실제로 존재하지 않을 수 있습니다.\n' +
            '실제 추출은 아래 "선택한 폴더의 실제 문서" 목록에서 확인하세요.',
        });
      }
      setIsLoading(false);
    }
  };

  return (
    <>
      <div className="component-6 py-4 hover:bg-gray-50/60 rounded-xl px-2 transition flex items-start justify-between gap-4">
        <div className="flex items-start gap-3.5">
          {/* 확장자 배지 */}
          <div
            className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold text-[10px] shrink-0 ${
              item.type === 'PDF'
                ? 'bg-red-50 text-red-500 border border-red-100'
                : item.type === 'TXT'
                ? 'bg-blue-50 text-blue-500 border border-blue-100'
                : 'bg-emerald-50 text-emerald-600 border border-emerald-100'
            }`}
          >
            <div>{item.type}</div>
          </div>

          {/* 메타데이터 */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span
                onClick={handleOpenPreview}
                className="font-bold text-xs text-gray-800 hover:text-indigo-600 cursor-pointer transition"
              >
                {item.title}
              </span>
              <span className="px-1.5 py-0.5 text-[10px] font-bold text-indigo-600 bg-indigo-50 rounded-md border border-indigo-100">
                {item.matchScore}
              </span>
            </div>

            <div className="text-[10px] text-gray-400 font-medium">
              {item.path} · {item.date}
            </div>

            <div className="text-[11px] text-gray-600 pt-0.5 leading-relaxed">
              <span dangerouslySetInnerHTML={{ __html: item.snippetHighlight }} />
            </div>
          </div>
        </div>

        {/* 열기 버튼 */}
        <div className="flex items-center gap-1.5 shrink-0 pt-1">
          <button
            onClick={handleOpenPreview}
            title="문서 미리보기 추출"
            className="p-2 text-gray-400 hover:text-indigo-600 hover:bg-white rounded-lg border border-transparent hover:border-gray-200 transition shadow-2xs cursor-pointer"
          >
            <img className="w-4 h-4" src="component-17.svg" alt="열기" />
          </button>
        </div>
      </div>

      {/* 미리보기 모달 */}
      {isPreviewOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl max-w-xl w-full p-6 space-y-4 shadow-xl border border-gray-100">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div>
                <h3 className="font-bold text-sm text-gray-900">{item.title}</h3>
                <p className="text-[11px] text-gray-400">문서 원문 미리보기</p>
              </div>
              <button
                onClick={() => setIsPreviewOpen(false)}
                className="text-gray-400 hover:text-gray-600 font-bold text-sm px-2 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto bg-gray-50 p-4 rounded-xl text-xs text-gray-700 leading-relaxed font-mono whitespace-pre-wrap border border-gray-200/60">
              {isLoading ? (
                <div className="py-8 text-center text-gray-400">
                  문서 텍스트를 추출하는 중입니다...
                </div>
              ) : (
                previewResult?.preview_text || '추출된 미리보기 텍스트가 없습니다.'
              )}
            </div>

            <div className="flex items-center justify-between pt-2">
              <span className="text-[10px] text-gray-400">
                경로: {previewResult?.path || item.path}
              </span>
              <button
                onClick={() => setIsPreviewOpen(false)}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold text-xs rounded-xl transition cursor-pointer"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}