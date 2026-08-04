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

// ---------------------------------------------------------------------------
// 실제 적용 API (POST /apply) — 승인한 항목만 실제로 이동·개명한다 (4주차).
// analyzeFolder가 분석 결과를 여기 캐시해 두면, apply 함수들이 id로 찾아 쓴다.
// 폴더를 선택하지 않은 데모(mock) 상태에서는 기존 /mock/*/apply로 폴백한다.
// ---------------------------------------------------------------------------

interface AnalyzedItem {
  sourcePath: string;       // 원본 파일의 절대 경로
  sourceName: string;       // 현재 파일명 (확장자 포함)
  sourceRelFolder: string;  // root 기준 상대 폴더 ('.'이면 root 바로 아래)
  recommendedName: string;
  recommendedFolder: string;
}

let lastAnalysis: { root: string; items: Map<string, AnalyzedItem> } | null = null;

/** 항목 1건의 적용 결과 (백엔드 AppliedItem 계약과 동일). */
export interface AppliedItem {
  source_path: string;
  target_path: string;
  status: 'moved' | 'valid' | 'skipped' | 'failed';
  reason: string;
}

export interface ApplyOutcome {
  total: number;
  moved: number;
  failed: number;
  items: AppliedItem[];
  history_id: string;
  /** 요청에 넣은 순서와 items 순서가 같다 — i번째 id의 결과가 items[i]다. */
  appliedIds: string[];
}

const relativeFolder = (root: string, absoluteDir: string): string => {
  const normalize = (value: string) => value.split(/[\\/]/).filter(Boolean).join('/');
  const rootNorm = normalize(root);
  const dirNorm = normalize(absoluteDir);
  if (dirNorm === rootNorm) return '.';
  if (dirNorm.startsWith(`${rootNorm}/`)) return dirNorm.slice(rootNorm.length + 1);
  return '.'; // root 밖이면 백엔드가 unsafe_path로 거른다 — 여기서는 그대로 보낸다
};

const postApply = async (
  root: string,
  ids: string[],
  toItem: (analyzed: AnalyzedItem) => { target_folder: string; target_filename: string },
): Promise<ApplyOutcome> => {
  const selected = ids
    .map((id) => ({ id, analyzed: lastAnalysis?.items.get(id) }))
    .filter((entry): entry is { id: string; analyzed: AnalyzedItem } => !!entry.analyzed);

  const response = await fetch(`${BASE_URL}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approved: true, // 이 요청은 사용자가 체크박스로 승인한 항목만 담는다
      root,
      items: selected.map(({ analyzed }) => ({
        source_path: analyzed.sourcePath,
        ...toItem(analyzed),
      })),
    }),
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(typeof detail === 'string' ? detail : `적용 실패 (HTTP ${response.status})`);
  }
  const body = await response.json();

  // 개명 후 이동(또는 그 반대)이 이어져도 원본 경로가 낡지 않도록,
  // 실제로 옮겨진 항목은 캐시를 새 경로로 갱신한다.
  (body.items as AppliedItem[]).forEach((applied, index) => {
    const entry = selected[index];
    if (applied.status !== 'moved' || !entry) return;
    const analyzed = lastAnalysis?.items.get(entry.id);
    if (!analyzed) return;
    analyzed.sourcePath = applied.target_path;
    analyzed.sourceName = applied.target_path.split(/[\\/]/).filter(Boolean).at(-1)
      || analyzed.sourceName;
    analyzed.sourceRelFolder = relativeFolder(root, parentFolder(applied.target_path));
  });

  return { ...body, appliedIds: selected.map(({ id }) => id) };
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

  // 적용(POST /apply)에 필요한 원본 경로·추천값을 id로 찾을 수 있게 캐시한다.
  lastAnalysis = {
    root: path,
    items: new Map(data.suggestions.map((item, index) => [String(index + 1), {
      sourcePath: item.current.path,
      sourceName: item.current.name,
      sourceRelFolder: relativeFolder(path, parentFolder(item.current.path)),
      recommendedName: item.suggestion.recommended_filename,
      recommendedFolder: item.suggestion.recommended_folder,
    }])),
  };

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
 * 2. 파일명 변경 적용 (POST /apply — 4주차부터 실제 개명)
 *
 * 파일은 지금 있는 폴더에 그대로 두고 이름만 추천안으로 바꾼다.
 * 분석 캐시가 없으면(폴더 미선택 데모 상태) 기존 mock 적용으로 폴백한다.
 */
export const applyRenameRecommendations = async (
  selectedIds: string[],
): Promise<ApplyOutcome | null> => {
  if (!lastAnalysis) {
    try {
      await fetch(`${BASE_URL}/mock/rename/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: selectedIds }),
      });
    } catch (error) {
      console.error('Apply Rename API 에러:', error);
    }
    return null;
  }
  return postApply(lastAnalysis.root, selectedIds, (analyzed) => ({
    target_folder: analyzed.sourceRelFolder,
    target_filename: analyzed.recommendedName,
  }));
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
 * 4. 파일 이동 적용 (POST /apply — 4주차부터 실제 이동)
 *
 * 파일명은 그대로 두고 추천 폴더로만 옮긴다. 이름 변경과 이동을 동시에
 * 승인한 경우에도 각 적용이 독립적으로 안전하게 동작한다(충돌 시 건너뜀).
 */
export const applyStructureRecommendations = async (
  selectedIds: string[],
): Promise<ApplyOutcome | null> => {
  if (!lastAnalysis) {
    try {
      await fetch(`${BASE_URL}/mock/move/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: selectedIds }),
      });
    } catch (error) {
      console.error('Apply Move API 에러:', error);
    }
    return null;
  }
  return postApply(lastAnalysis.root, selectedIds, (analyzed) => ({
    target_folder: analyzed.recommendedFolder,
    target_filename: analyzed.sourceName,
  }));
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