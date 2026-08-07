import { useEffect, useState } from 'react';
import { getPreprocessPreview } from '../api/preprocessApi';

interface Props {
  path: string;
  name: string;
  onClose: () => void;
  onReveal?: () => void;
}

const BASE_URL = 'http://127.0.0.1:8000';

/**
 * 문서 미리보기 — 첫 페이지를 **보이는 그대로** 그려 준다.
 *
 * 추출한 텍스트만 보여 주면 표·그림·서식이 사라져서 "내가 찾던 그 파일인가"를
 * 판단하기 어렵다. PDF는 첫 페이지를 이미지로 렌더링하고, 렌더링할 수 없는
 * 형식(docx·hwp 등)은 텍스트로 넘어간다.
 */
export default function DocumentPreview({ path, name, onClose, onReveal }: Props) {
  const [imageUrl, setImageUrl] = useState('');
  const [text, setText] = useState('');
  const [note, setNote] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = '';

    const load = async () => {
      setIsLoading(true);
      try {
        const response = await fetch(
          `${BASE_URL}/preview/thumbnail?path=${encodeURIComponent(path)}`,
        );
        if (response.ok) {
          objectUrl = URL.createObjectURL(await response.blob());
          if (!cancelled) setImageUrl(objectUrl);
          return;
        }
        // 이미지로 그릴 수 없는 형식이면 텍스트로 대신한다
        if (!cancelled) {
          setNote(
            response.status === 415
              ? '이 형식은 화면 그대로 보여 줄 수 없어 본문 일부를 표시합니다.'
              : '',
          );
        }
        const preview = await getPreprocessPreview(path);
        if (!cancelled) {
          setText(preview?.first_page_text || preview?.text || preview?.content || '');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6"
      onClick={onClose}
    >
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-[#16161e]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3.5 dark:border-gray-700/70">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-bold text-gray-900 dark:text-gray-50">{name}</h3>
            <p className="truncate text-[11px] text-gray-400 dark:text-gray-500" title={path}>
              {path}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2 pl-3">
            {onReveal && (
              <button
                onClick={onReveal}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-[11px] font-bold text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-white/5"
              >
                탐색기에서 보기
              </button>
            )}
            <button
              onClick={onClose}
              className="cursor-pointer px-2 text-sm font-bold text-gray-400 hover:text-gray-600 dark:text-gray-500"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-50 p-5 dark:bg-white/5">
          {isLoading ? (
            <div className="py-16 text-center text-xs text-gray-400 dark:text-gray-500">
              <div className="mx-auto mb-3 h-1.5 w-40 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-500/20">
                <div className="h-full w-1/3 rounded-full bg-indigo-500 animate-[loading_1.2s_ease-in-out_infinite]" />
              </div>
              첫 페이지를 불러오는 중입니다…
            </div>
          ) : imageUrl ? (
            <img
              src={imageUrl}
              alt={`${name} 첫 페이지`}
              className="mx-auto max-w-full rounded-lg border border-gray-200 shadow-sm dark:border-gray-700"
            />
          ) : (
            <>
              {note && (
                <p className="mb-3 text-[11px] text-gray-500 dark:text-gray-400">{note}</p>
              )}
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-gray-700 dark:text-gray-200">
                {text || '미리볼 내용을 찾지 못했습니다.'}
              </pre>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
