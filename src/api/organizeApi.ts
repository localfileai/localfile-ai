export interface RenameRecommendation {
  id: string;
  currentName: string;
  recommendedName: string;
  confidence: string;
  category: string;
  fileType: 'PDF' | 'TXT' | 'MD';
}

export interface StructureRecommendation {
  id: string;
  fileName: string;
  currentFolder: string;
  targetFolder: string;
  confidence: string;
}

// 💡 백엔드가 넘겨주는 전체 파일 1개의 타입 정의
export interface CurrentFileItem {
  id: string;
  name: string;
  ext: string;
  path: string;
}

// 💡 리턴 타입에 currentFiles 배열 추가
export interface StructureResult {
  recommendations: StructureRecommendation[];
  currentFiles: CurrentFileItem[]; // 👈 화면에 8개를 띄워줄 전체 파일 배열
  totalFilesCount: number;
}

export interface ReanalyzeResponse {
  message: string;
  rename_count: number;
  move_count: number;
}

const BASE_URL = 'http://127.0.0.1:8000';

/**
 * 백엔드가 보내는 원본 항목들. 필드가 전부 optional인 이유:
 *
 * BE1의 `contracts/ai.py`와 BE2의 `contracts/api.py`가 아직 같은 것을 다르게
 * 부릅니다(`recommended_filename` vs `recommended_name` 등). 어느 쪽이 와도
 * 화면이 죽지 않게 후보 필드를 모두 열어 두고 아래에서 골라 읽습니다.
 *
 * 2주차에 계약을 하나로 합치면 이 타입들은 정확한 필드만 남기고 좁혀야 합니다.
 */
interface RawRenameItem {
  id?: string | number;
  confidence?: number | string;
  old?: string;
  currentName?: string;
  next?: string;
  recommendedName?: string;
  category?: string;
  ext?: string;
  fileType?: string;
}

interface RawMoveItem {
  id?: string | number;
  confidence?: number | string;
  fileName?: string;
  old?: string;
  name?: string;
  from_?: string;
  currentFolder?: string;
  current_path?: string;
  path?: string;
  to?: string;
  targetFolder?: string;
  target_path?: string;
  next?: string;
}

interface RawCurrentFile {
  id?: string | number;
  name?: string;
  ext?: string;
  path?: string;
}

/** `confidence`가 0.0~1.0(BE1)이든 0~100(BE2)이든 같은 문자열로 만든다. */
const toConfidenceString = (confidence: number | string | undefined): string => {
  if (typeof confidence === 'number') {
    const value = confidence > 1 ? confidence : confidence * 100;
    return `${Math.round(value)}%`;
  }
  return confidence ? String(confidence) : '0%';
};

/**
 * 1. 파일명 변경 추천 목록 조회 (GET /mock/rename)
 */
export const getRenameRecommendations = async (): Promise<RenameRecommendation[]> => {
  try {
    const response = await fetch(`${BASE_URL}/mock/rename`);
    if (!response.ok) throw new Error('파일명 추천 조회 실패');
    
    const data = await response.json();
    const items = data.items || (Array.isArray(data) ? data : []);

    return items.map((item: RawRenameItem, index: number) => ({
      id: String(item.id || index + 1),
      currentName: item.old || item.currentName || '이름 없음',
      recommendedName: item.next || item.recommendedName || '추천 이름 없음',
      confidence: toConfidenceString(item.confidence),
      category: item.category || '일반 문서',
      fileType: (item.ext === 'Markdown' ? 'MD' : item.ext || item.fileType || 'PDF') as 'PDF' | 'TXT' | 'MD',
    }));
  } catch (error) {
    console.error('Rename API 에러:', error);
    return [];
  }
};

/**
 * 2. 파일명 변경 적용 모의 (POST /mock/rename/apply)
 */
export const applyRenameRecommendations = async (selectedIds: string[]) => {
  try {
    const response = await fetch(`${BASE_URL}/mock/rename/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: selectedIds }),
    });
    return await response.json();
  } catch (error) {
    console.error('Apply Rename API 에러:', error);
  }
};

/**
 * 3. 파일 이동 추천 목록, 전체 파일 배열, 전체 개수 조회 (GET /mock/move)
 */
export const getStructureRecommendations = async (): Promise<StructureResult> => {
  try {
    const response = await fetch(`${BASE_URL}/mock/move`);
    if (!response.ok) throw new Error('폴더 구조 추천 조회 실패');
    
    const data = await response.json();
    const items = data.recommendations || data.items || (Array.isArray(data) ? data : []);

    // 💡 1. 백엔드 CURRENT_FILES_SAMPLE (8개) 매핑
    const rawFiles = data.current_files || [];
    const mappedCurrentFiles: CurrentFileItem[] = rawFiles.map((file: RawCurrentFile, index: number) => ({
      id: String(file.id || index + 1),
      name: file.name || '파일명 없음',
      ext: file.ext || 'PDF',
      path: file.path || 'Documents',
    }));

    // 💡 2. 이동 추천 항목 매핑
    const mappedRecommendations = items.map((item: RawMoveItem, index: number) => {
      return {
        id: String(item.id || index + 1),
        fileName: item.fileName || item.old || item.name || '파일명 없음',
        currentFolder: item.from_ || item.currentFolder || item.current_path || item.path || '현재 폴더',
        targetFolder: item.to || item.targetFolder || item.target_path || item.next || '추천 폴더',
        confidence: toConfidenceString(item.confidence),
      };
    });

    // 💡 3. recommendations, currentFiles, totalFilesCount 세 가지를 모두 전달
    return {
      recommendations: mappedRecommendations,
      currentFiles: mappedCurrentFiles, // 👈 백엔드가 보낸 8개 파일 배열
      totalFilesCount: mappedCurrentFiles.length || items.length,
    };
  } catch (error) {
    console.error('Move API 에러:', error);
    return { recommendations: [], currentFiles: [], totalFilesCount: 0 };
  }
};

/**
 * 4. 파일 이동 적용 모의 (POST /mock/move/apply)
 */
export const applyStructureRecommendations = async (selectedIds: string[]) => {
  try {
    const response = await fetch(`${BASE_URL}/mock/move/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: selectedIds }),
    });
    return await response.json();
  } catch (error) {
    console.error('Apply Move API 에러:', error);
  }
};

/**
 * 5. 재분석 모의 (POST /mock/reanalyze)
 */
export const reanalyzeProject = async (): Promise<ReanalyzeResponse | null> => {
  try {
    const response = await fetch(`${BASE_URL}/mock/reanalyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) throw new Error('재분석 요청 실패');
    return await response.json();
  } catch (error) {
    console.error('Reanalyze API 에러:', error);
    return null;
  }
};