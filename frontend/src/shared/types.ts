/**
 * 与 backend/contracts/models.py 对齐的前端类型定义。
 * 公共字段与状态值以 docs/assignment-03/interface-contract-v1.md 为准，不要在前端另立一套。
 */

export type AnswerStatus =
  | 'answered'
  | 'needs_clarification'
  | 'insufficient_evidence';

export type AnswerMode =
  | 'current_policy'
  | 'historical'
  | 'procedure_reference'
  | 'insufficient_data';

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
}

export interface AskRequest {
  query: string;
  conversation_id?: string | null;
}

export interface WarningItem {
  code: string;
  message: string;
}

export interface Citation {
  document_id: string;
  version_id: string;
  chunk_id: string;
  title: string;
  publisher?: string | null;
  source_url: string;
  published_on?: string | null;
  effective_on?: string | null;
  locator?: string | null;
  original_locator?: string | null;
  excerpt: string;
  source_verification_status: 'pending' | 'partial' | 'verified' | 'failed';
  timeliness_verification_status:
    | 'pending' | 'current' | 'historical' | 'superseded' | 'expired' | 'uncertain';
  retrieval_status: 'blocked' | 'review_only' | 'enabled';
}

export interface AskResponse {
  request_id: string;
  conversation_id: string;
  status: AnswerStatus;
  answer: string | null;
  answer_mode: AnswerMode | null;
  clarifying_question: string | null;
  citations: Citation[];
  warnings: WarningItem[];
  created_at: string;
}

/* ==========================================================================
 * 后台管理端（林彦翔）
 * 字段与状态值以 docs/assignment-03/interface-contract-v1.md 第 4.2、10 节
 * 与 backend/contracts/models.py 为准，不新增、不改名。
 * ========================================================================== */

export type SourceVerificationStatus = 'pending' | 'partial' | 'verified' | 'failed';

export type TimelinessVerificationStatus =
  | 'pending'
  | 'current'
  | 'historical'
  | 'superseded'
  | 'expired'
  | 'uncertain';

export type ExtractionStatus = 'pending' | 'extracted' | 'needs_ocr' | 'failed';

export type RetrievalStatus = 'blocked' | 'review_only' | 'enabled';

export type IndexingStatus = 'pending' | 'indexed' | 'failed';

/** 契约 DocumentSummary：后台资料列表行的最小字段集合。 */
export interface DocumentSummary {
  document_id: string;
  title: string;
  document_type: string;
  category_name: string;
  record_code: string;
  version_no: string;
  source_verification_status: SourceVerificationStatus;
  timeliness_verification_status: TimelinessVerificationStatus;
  extraction_status: ExtractionStatus;
  retrieval_status: RetrievalStatus;
  updated_at: string | null;
}

/** 契约 DocumentListResponse：分页信封，page 从 1 开始。 */
export interface DocumentListResponse {
  items: DocumentSummary[];
  total: number;
  page: number;
  page_size: number;
}

/** 契约 DocumentUploadResponse：上传先返回 processing，完成后 indexed / failed。 */
export interface DocumentUploadResponse {
  document_id: string;
  version_id: string;
  status: string;
  message: string;
}

/** 契约 IndexResult。 */
export interface IndexResult {
  document_id: string;
  version_id: string;
  status: IndexingStatus;
  chunk_count: number;
  indexed_count: number;
  warnings: WarningItem[];
}

/** 契约 ReindexResponse。 */
export interface ReindexResponse {
  document_id: string;
  version_id: string;
  status: IndexingStatus;
  chunk_count: number;
  indexed_count: number;
  message: string;
}

/**
 * 契约缺口补充字段（见 docs/assignment-03/admin/数据口径与契约缺口说明.md）。
 * 数据库 document_versions 有这些列，但 DocumentSummary 未暴露，而任务书要求
 * 列表展示「发布单位或来源」。等组长在 V1.1 补齐 `publisher` / `source_url` 后，
 * 应删除本接口，直接使用契约字段。
 */
export interface DocumentDetailExtras {
  /** 数据库主键；契约 DocumentSummary 未暴露，详情/重建索引入口按需使用。 */
  version_id: string;
  publisher: string | null;
  responsible_department: string | null;
  document_number: string | null;
  source_url: string | null;
  published_on: string | null;
  effective_on: string | null;
  deadline_on: string | null;
  policy_status: string | null;
  applicability: {
    grade: string | null;
    major: string | null;
    target: string | null;
  };
  verification_note: string | null;
  verified_on: string | null;
}

/** 后台列表行 = 契约字段 + 缺口补充字段。 */
export type AdminDocument = DocumentSummary & DocumentDetailExtras;

/** PATCH /admin/documents/{id} 允许维护的元数据白名单（请求体待契约细化）。 */
export interface AdminDocumentMetadataPatch {
  title?: string;
  document_type?: string;
  category_name?: string;
  publisher?: string;
  document_number?: string;
  published_on?: string;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  retryable: boolean;
}

export interface ApiErrorResponse {
  request_id: string | null;
  error: ApiErrorDetail;
}
