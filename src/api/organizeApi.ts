export interface RenameRecommendation {
  id: string;
  currentName: string;
  recommendedName: string;
  confidence: string;
  category: string;
  // 실제 지원 확장자는 기획안 7종(PDF·DOCX·DOC·PPTX·PPT·HWPX·HWP)이라 문자열로 둔다.
  fileType: string;
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

// ---------------------------------------------------------------------------
// 실제 추천 API (POST /organize) — 계약: backend/app/contracts/ai.py
// 사용자가 폴더를 선택하면 이 경로를 쓰고, 선택 전에는 아래 Mock 경로를 쓴다.
// 계약 단일화 계획: docs/contracts-unification.md
// ---------------------------------------------------------------------------

interface OrganizeFileRef {
  path: string;
  name: string;
  extension: string;
}

interface OrganizeSuggestion {
  category: string;
  recommended_folder: string;
  recommended_filename: string;
  confidence: number; // 0.0~1.0 — 화면 표시는 %로 변환
  reason: string;
}

interface OrganizeResponseBody {
  total_files: number;
  success_count: number;
  suggestions: { current: OrganizeFileRef; suggestion: OrganizeSuggestion }[];
  failed: { path: string; reason: string }[];
}

export interface OrganizeData {
  renameList: RenameRecommendation[];
  structureList: StructureRecommendation[];
  currentFiles: CurrentFileItem[];
  totalFilesCount: number;
}

const parentFolder = (path: string): string => {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.slice(0, -1).join('/') || path;
};

/**
 * 선택한 폴더를 실제 AI로 분석해 추천을 받는다.
 * CPU 환경에서는 파일당 수십 초가 걸릴 수 있다(저사양이면 백엔드가 slim 모드로 자동 강등).
 */
export const analyzeFolder = async (path: string): Promise<OrganizeData> => {
  const response = await fetch(`${BASE_URL}/organize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!response.ok) {
    // 503(모델 없음)·400(잘못된 경로)의 이유를 그대로 화면까지 올린다.
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(detail || `분석 실패 (HTTP ${response.status})`);
  }

  const data: OrganizeResponseBody = await response.json();

  const renameList: RenameRecommendation[] = data.suggestions.map((item, index) => ({
    id: String(index + 1),
    currentName: item.current.name,
    recommendedName: item.suggestion.recommended_filename,
    confidence: toConfidenceString(item.suggestion.confidence),
    category: item.suggestion.category,
    fileType: item.current.extension.toUpperCase(),
  }));

  const structureList: StructureRecommendation[] = data.suggestions.map((item, index) => ({
    id: String(index + 1),
    fileName: item.current.name,
    currentFolder: parentFolder(item.current.path),
    targetFolder: item.suggestion.recommended_folder,
    confidence: toConfidenceString(item.suggestion.confidence),
  }));

  // 파일 목록에는 추천 실패분(스캔 PDF 등)도 포함해 보여 준다.
  const currentFiles: CurrentFileItem[] = [
    ...data.suggestions.map((item, index) => ({
      id: String(index + 1),
      name: item.current.name,
      ext: item.current.extension.toUpperCase(),
      path: parentFolder(item.current.path),
    })),
    ...data.failed.map((item, index) => ({
      id: `failed-${index + 1}`,
      name: item.path.split(/[\\/]/).filter(Boolean).at(-1) || item.path,
      ext: (item.path.split('.').at(-1) || '').toUpperCase(),
      path: parentFolder(item.path),
    })),
  ];

  return { renameList, structureList, currentFiles, totalFilesCount: data.total_files };
};

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