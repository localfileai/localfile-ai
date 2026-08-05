export interface SearchResult {
  id: string;
  title: string;
  type: 'PDF' | 'TXT' | 'MD';
  matchScore: string;
  path: string;
  date: string;
  snippetPre: string;
  snippetHighlight: string;
  snippetPost: string;
  /**
   * 실제 파일의 전체 경로. **실제 검색(`/search`)에서만 채워집니다.**
   * Mock 검색은 존재하지 않는 예시 경로라 이 값이 없습니다.
   * 미리보기가 이 값이 있으면 그대로 쓰고, 없으면 폴더+파일명을 조립합니다.
   */
  fullPath?: string;
}

/** 검색 엔진 선택. 1주차 Mock과 실제 임베딩 검색을 화면에서 구분하기 위한 값입니다. */
export type SearchEngine = 'real' | 'mock';

export interface SearchStatus {
  ready: boolean;
  indexed_documents: number;
  embed_model: string;
  detail: string;
}

const BASE_URL = 'http://127.0.0.1:8000';

/** 백엔드 `SearchItem` (BE2 `contracts/api.py`). 계약 확정 전이라 optional로 둡니다. */
interface RawSearchItem {
  name?: string;
  ext?: string;
  path?: string;
  modified?: string;
  score?: number;
  snippet?: string;
}

/**
 * [GET /mock/search] 동적 검색 API 호출
 */
export const fetchSearchResults = async (
  q: string = '',
  types: string = '',
  date: string = 'all',
  sort: string = 'score'
): Promise<SearchResult[]> => {
  try {
    const params = new URLSearchParams({ q, types, date, sort });
    const response = await fetch(`${BASE_URL}/mock/search?${params.toString()}`);

    if (!response.ok) {
      throw new Error(`검색 API 요청 실패 (${response.status})`);
    }

    const data = await response.json();
    const items = data.items || [];

    // 백엔드가 넘겨주는 가변 데이터를 동적으로 그대로 가져옵니다.
    return items.map((item: RawSearchItem, index: number) => {
      const extUpper = (item.ext || 'PDF').toUpperCase();
      const fileType = (extUpper === 'MARKDOWN' ? 'MD' : extUpper) as 'PDF' | 'TXT' | 'MD';

      // 백엔드에서 전달된 경로/파일명 정제
      const rawPath = item.path || '';
      const rawName = item.name || '제목 없음';

      return {
        id: String(index + 1),
        title: rawName,
        type: fileType,
        matchScore: item.score ? `${item.score}%` : '0%',
        path: rawPath, // 백엔드 동적 경로 원본 유지
        date: item.modified || '',
        snippetPre: '',
        snippetHighlight: item.snippet || '',
        snippetPost: '',
      };
    });
  } catch (error) {
    console.error('Search API 에러:', error);
    return [];
  }
};

// =====================================================================
// 실제 임베딩 검색 (BE1 기능① · bge-m3 + ChromaDB)
// =====================================================================

/** BE1 계약 `app/contracts/ai.py`의 `SearchResponse` 형태입니다. */
interface ContractFileRef {
  path: string;
  name: string;
  extension: string;
  size_bytes: number;
  modified_at: string | null;
}

interface ContractSearchHit {
  file: ContractFileRef;
  /** 관련도 0.0~1.0 (계약이 범위를 강제) */
  score: number;
  matched_text: string;
}

interface ContractSearchResponse {
  query: string;
  total_hits: number;
  hits: ContractSearchHit[];
  elapsed_ms: number;
}

export interface RealSearchOutcome {
  results: SearchResult[];
  elapsedMs: number;
  /** 색인/모델이 준비되지 않았을 때 백엔드가 준 이유 (503) */
  error: string;
}

/** `GET /search/status` — 색인·모델 준비 상태 */
export const fetchSearchStatus = async (): Promise<SearchStatus | null> => {
  try {
    const response = await fetch(`${BASE_URL}/search/status`);
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    console.error('Search status 에러:', error);
    return null;
  }
};

/**
 * [GET /search] 자연어 임베딩 검색.
 *
 * Mock과 달리 실제 파일을 가리키므로 `fullPath`를 채워 줍니다.
 * 그 덕에 결과를 눌렀을 때 원문 미리보기가 실제로 동작합니다.
 */
export const fetchRealSearchResults = async (
  q: string,
  topK = 30,
  /** 지금 고른 폴더. 주면 그 폴더에서 색인한 문서만 찾는다 */
  root = '',
): Promise<RealSearchOutcome> => {
  try {
    const params = new URLSearchParams({ q, top_k: String(topK) });
    if (root) params.set('root', root);
    const response = await fetch(`${BASE_URL}/search?${params.toString()}`);

    if (!response.ok) {
      // 503은 "색인이 없다 / Ollama가 없다" 처럼 사용자가 고칠 수 있는 상태입니다.
      let detail = `검색 실패 (HTTP ${response.status})`;
      try {
        const body = await response.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        // 본문이 JSON이 아니면 기본 문구를 씁니다.
      }
      return { results: [], elapsedMs: 0, error: detail };
    }

    const data: ContractSearchResponse = await response.json();

    const results = data.hits.map((hit, index) => {
      const extUpper = (hit.file.extension || 'pdf').toUpperCase();
      const separator = hit.file.path.includes('\\') ? '\\' : '/';
      const parentPath = hit.file.path.slice(0, hit.file.path.lastIndexOf(separator));

      return {
        id: String(index + 1),
        title: hit.file.name,
        type: extUpper as 'PDF' | 'TXT' | 'MD',
        // 계약의 score는 0.0~1.0이라 100을 곱합니다.
        matchScore: `${Math.round(hit.score * 100)}%`,
        path: parentPath,
        date: hit.file.modified_at ? hit.file.modified_at.slice(0, 10) : '',
        snippetPre: '',
        snippetHighlight: hit.matched_text,
        snippetPost: '',
        fullPath: hit.file.path,
      };
    });

    return { results, elapsedMs: data.elapsed_ms, error: '' };
  } catch (error) {
    console.error('Real search API 에러:', error);
    return {
      results: [],
      elapsedMs: 0,
      error: '백엔드에 연결할 수 없습니다. `npm run backend:dev` 가 켜져 있는지 확인하세요.',
    };
  }
};