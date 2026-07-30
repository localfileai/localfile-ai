const BASE_URL = 'http://127.0.0.1:8000';

/**
 * 백엔드 `ExtractedDocument` 1건. (BE2 `app/contracts/api.py`)
 *
 * FileResultCard가 이 타입을 import하는데 FE2 원본 `preprocessApi.ts`에는
 * 정의가 없어 컴파일이 되지 않았습니다. 백엔드 응답 필드를 그대로 옮겨 정의합니다.
 */
export interface PreviewItem {
  path: string;
  name: string;
  extension: string;
  raw_text?: string;
  normalized_text?: string;
  preview_text: string;
  error?: string;
}

export interface PreprocessPreviewResponse {
  /** 백엔드 원본 응답 */
  count?: number;
  items?: PreviewItem[];
  /**
   * 아래 3개는 백엔드에 없는 필드입니다.
   * FE는 단일 파일 미리보기만 쓰므로 이 클라이언트에서 items[0]으로 채워 줍니다.
   */
  first_page_text?: string;
  text?: string;
  content?: string;
  detail?: unknown;
  [key: string]: unknown;
}

/**
 * [POST /preprocess/extract-first-page] 폴더 안의 지원 문서를 모두 추출한다.
 *
 * 같은 엔드포인트가 파일 하나와 폴더를 모두 받습니다. 폴더를 주면
 * 바로 아래의 PDF·TXT·MD를 전부 돌려줍니다.
 *
 * 1주차에서 **실제로 동작하는 유일한 기능**이라 화면에서 바로 확인할 수 있게
 * 목록 조회를 따로 뺐습니다. (검색 결과는 아직 Mock입니다)
 */
export const listFolderDocuments = async (
  path: string,
  maxChars = 1500
): Promise<{ items: PreviewItem[]; error: string }> => {
  try {
    const response = await fetch(
      `${BASE_URL}/preprocess/extract-first-page?max_chars=${maxChars}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      }
    );

    if (!response.ok) {
      const detail = await response.text();
      console.error('폴더 추출 실패:', detail);
      return { items: [], error: `추출 실패 (HTTP ${response.status}). 경로를 확인해 주세요.` };
    }

    const data: PreprocessPreviewResponse = await response.json();
    return { items: data.items ?? [], error: '' };
  } catch (error) {
    console.error('폴더 추출 API 에러:', error);
    return { items: [], error: '백엔드에 연결할 수 없습니다. `npm run backend:dev` 가 켜져 있는지 확인하세요.' };
  }
};

/**
 * [POST /preprocess/extract-first-page] PDF/문서 첫 페이지 텍스트 추출 API
 *
 * 백엔드는 `{ count, items[] }`를 돌려줍니다. 호출부(FileResultCard)는
 * `first_page_text`를 읽으므로 여기서 첫 문서의 텍스트를 평탄화해 넣습니다.
 * 이 처리가 없으면 미리보기 모달에 JSON 원문이 그대로 노출됩니다.
 */
export const getPreprocessPreview = async (
  path: string
): Promise<PreprocessPreviewResponse | null> => {
  try {
    const response = await fetch(`${BASE_URL}/preprocess/extract-first-page`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      // 백엔드가 path 키값을 기대하는 형태
      body: JSON.stringify({ path }),
    });

    if (!response.ok) {
      // 400 등의 에러 원인을 백엔드 응답 디테일로 확인
      const errorDetail = await response.text();
      console.error('백엔드 에러 상세:', errorDetail);
      throw new Error(`전처리 API 요청 실패 (${response.status})`);
    }

    const data: PreprocessPreviewResponse = await response.json();

    const first = data.items?.[0];
    if (first) {
      // 추출 실패한 파일은 error에 이유가 담겨 오므로 그걸 보여 줍니다.
      const extracted = first.error
        ? `텍스트를 추출하지 못했습니다: ${first.error}`
        : first.preview_text || first.normalized_text || first.raw_text || '';
      return { ...data, first_page_text: extracted };
    }

    // 지원 확장자(PDF/TXT/MD)가 하나도 없으면 items가 빈 배열로 옵니다.
    return { ...data, first_page_text: '지원하는 문서를 찾지 못했습니다. (PDF · TXT · MD)' };
  } catch (error) {
    console.error('Preprocess Preview API 에러:', error);
    return null;
  }
};
