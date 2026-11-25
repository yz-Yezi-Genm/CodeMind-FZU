import type {
  AdminDocumentMetadataPatch,
  AskRequest,
  AskResponse,
  Citation,
  DocumentListResponse,
  DocumentSummary,
  DocumentUploadResponse,
  HealthResponse,
  ReindexResponse,
} from './types';

const API_BASE = '/api/v1';
const HEALTH_TIMEOUT_MS = 5_000;
// Leave room for the backend's own model and workflow timeout responses.
const ASK_TIMEOUT_MS = 45_000;
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

// The local Alpha Mock predates Beta's requirement for a non-null answer mode.
type AlphaMockAnswer = Omit<Extract<AskResponse, { status: 'answered' }>,
  'answer_mode' | 'clarifying_question' | 'citations'> & {
  answer_mode: null;
  clarifying_question: null;
  citations: [];
};

export type StudentAskResponse = AskResponse | AlphaMockAnswer;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, retryable = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isUuid(value: unknown): boolean {
  return typeof value === 'string' && UUID.test(value);
}

async function request<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs === undefined ? undefined : new AbortController();
  const timer = controller && setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, controller ? { ...init, signal: controller.signal } : init);
    const data: unknown = await response.json().catch(() => null);
    controller?.signal.throwIfAborted();
    if (!response.ok) {
      const detail = isRecord(data) && isRecord(data.error) ? data.error : undefined;
      const code = isText(detail?.code) ? detail.code : `HTTP_${response.status}`;
      const fallback = response.status >= 500 ? '后端暂不可用，请确认服务已启动。' : '请求失败，请检查后重试。';
      throw new ApiError(response.status, code, isText(detail?.message) ? detail.message : fallback, detail?.retryable === true);
    }
    if (!isRecord(data)) {
      throw new ApiError(response.status, 'INVALID_RESPONSE', '后端返回了无效数据，请稍后重试。');
    }
    return data as T;
  } catch (error) {
    if (controller?.signal.aborted) {
      throw new ApiError(0, 'REQUEST_TIMEOUT', '请求等待超时，请稍后重试。', true);
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, 'NETWORK_ERROR', '无法连接后端，请检查网络或服务是否已启动。', true);
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const health = await request<HealthResponse>('/health', undefined, HEALTH_TIMEOUT_MS);
  if (health.status !== 'ok' || !isText(health.service) || !isText(health.version)
    || !isText(health.timestamp) || !Number.isFinite(Date.parse(health.timestamp))) {
    throw new ApiError(200, 'INVALID_RESPONSE', '无法识别后端健康检查结果。');
  }
  return health;
}

function parseCitation(value: unknown): Citation | null {
  if (!isRecord(value) || !isUuid(value.document_id) || !isUuid(value.version_id) || !isUuid(value.chunk_id)
    || !isText(value.title) || !isText(value.excerpt) || !isText(value.source_url)
    || !['pending', 'partial', 'verified', 'failed'].some(status => status === value.source_verification_status)
    || !['pending', 'current', 'historical', 'superseded', 'expired', 'uncertain'].some(status => status === value.timeliness_verification_status)
    || !['blocked', 'review_only', 'enabled'].some(status => status === value.retrieval_status)) {
    return null;
  }
  const textFields = ['publisher', 'published_on', 'effective_on', 'locator', 'original_locator'];
  if (textFields.some(key => value[key] != null && typeof value[key] !== 'string')) return null;
  return value as unknown as Citation;
}

function parseAskResponse(response: Record<string, unknown>): StudentAskResponse {
  const invalid = new ApiError(200, 'INVALID_RESPONSE', '问答接口返回了无效或空数据，请稍后重试。');
  if (!isUuid(response.conversation_id)) {
    throw new ApiError(200, 'INVALID_RESPONSE', '问答接口没有返回有效的会话编号，请稍后重试。');
  }
  if (!isUuid(response.request_id) || !isText(response.created_at) || !Number.isFinite(Date.parse(response.created_at))
    || !Array.isArray(response.citations) || !Array.isArray(response.warnings)
    || !response.warnings.every(item => isRecord(item) && isText(item.code) && isText(item.message))
    || (response.answer !== null && typeof response.answer !== 'string')
    || (response.clarifying_question !== null && typeof response.clarifying_question !== 'string')) {
    throw invalid;
  }

  const citations = response.citations.map(parseCitation);
  const isAlphaMock = response.answer_mode === null && response.clarifying_question === null
    && citations.length === 0 && response.warnings.some(item => item.code === 'MOCK_AGENT');
  const validStatus = (
    (response.status === 'answered' && isText(response.answer)
      && (isAlphaMock || ['current_policy', 'historical', 'procedure_reference', 'insufficient_data']
        .some(mode => mode === response.answer_mode)))
    || (response.status === 'needs_clarification' && response.answer === null && response.answer_mode === null
      && isText(response.clarifying_question) && citations.length === 0)
    || (response.status === 'insufficient_evidence' && response.answer_mode === 'insufficient_data'
      && (isText(response.answer) || response.warnings.length > 0) && citations.length === 0)
  );
  if (!validStatus || !citations.every(citation => citation !== null)) throw invalid;
  return { ...response, citations } as unknown as StudentAskResponse;
}

export async function ask({ query, conversation_id = null }: AskRequest): Promise<StudentAskResponse> {
  if (conversation_id !== null && !isUuid(conversation_id)) {
    throw new ApiError(0, 'INVALID_CONVERSATION', '当前会话标识无效，请点击「新建对话」后再发送。');
  }
  const response = await request<Record<string, unknown>>('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, conversation_id }),
  }, ASK_TIMEOUT_MS);
  return parseAskResponse(response);
}

/* ==========================================================================
 * 后台管理端接口（契约 10 节）。Alpha 阶段后端尚未实现，
 * 调用失败会抛 ApiError，由页面降级到模拟数据并明确提示。
 * ========================================================================== */

export interface AdminDocumentQuery {
  page: number;
  page_size: number;
}

function assertDocumentList(data: DocumentListResponse): DocumentListResponse {
  const validItems = Array.isArray(data.items)
    && data.items.every((item) => typeof item?.document_id === 'string' && typeof item?.title === 'string');
  const validEnvelope = Number.isInteger(data.total) && data.total >= 0
    && Number.isInteger(data.page) && data.page >= 1
    && Number.isInteger(data.page_size) && data.page_size >= 1;
  if (!validItems || !validEnvelope) {
    throw new ApiError(200, 'INVALID_RESPONSE', '资料列表接口返回了无效分页数据。');
  }
  return data;
}

/** GET /api/v1/admin/documents：资料分页列表。 */
export async function listAdminDocuments(query: AdminDocumentQuery): Promise<DocumentListResponse> {
  const search = new URLSearchParams({
    page: String(query.page),
    page_size: String(query.page_size),
  });
  const data = await request<DocumentListResponse>(`/admin/documents?${search.toString()}`);
  return assertDocumentList(data);
}

/** GET /api/v1/admin/documents/{document_id}：资料详情与处理状态。 */
export async function getAdminDocument(documentId: string): Promise<DocumentSummary> {
  const data = await request<DocumentSummary>(`/admin/documents/${encodeURIComponent(documentId)}`);
  if (!data.document_id || !data.title) {
    throw new ApiError(200, 'INVALID_RESPONSE', '资料详情接口返回了无效数据。');
  }
  return data;
}

/**
 * POST /api/v1/admin/documents：上传/登记资料并触发解析。
 * 契约未细化请求体格式，这里按 multipart/form-data 提交文件 + 元数据字段，
 * 待与丁晓炜（文档解析）、赵紫龙（HTTP API）对齐后调整。
 */
export async function uploadAdminDocument(
  file: File,
  metadata: Record<string, string>,
): Promise<DocumentUploadResponse> {
  const body = new FormData();
  body.append('file', file);
  for (const [key, value] of Object.entries(metadata)) {
    if (value.trim()) {
      body.append(key, value);
    }
  }
  const data = await request<DocumentUploadResponse>('/admin/documents', {
    method: 'POST',
    body,
  });
  if (!data.document_id || typeof data.status !== 'string') {
    throw new ApiError(200, 'INVALID_RESPONSE', '上传接口返回了无效数据。');
  }
  return data;
}

/**
 * PATCH /api/v1/admin/documents/{document_id}：修改允许维护的元数据。
 * 契约只给了方法名与路径，没有定义更新 DTO；这里提交白名单字段，
 * 待组长在 V1.1 补齐 DocumentMetadataUpdate 后调整。
 */
export async function updateAdminDocumentMetadata(
  documentId: string,
  patch: AdminDocumentMetadataPatch,
): Promise<DocumentSummary> {
  const data = await request<DocumentSummary>(`/admin/documents/${encodeURIComponent(documentId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!data.document_id) {
    throw new ApiError(200, 'INVALID_RESPONSE', '元数据更新接口返回了无效数据。');
  }
  return data;
}

/** POST /api/v1/admin/documents/{document_id}/reindex：重新构建索引。 */
export async function reindexAdminDocument(documentId: string): Promise<ReindexResponse> {
  const data = await request<ReindexResponse>(
    `/admin/documents/${encodeURIComponent(documentId)}/reindex`,
    { method: 'POST' },
  );
  if (!data.document_id || typeof data.status !== 'string') {
    throw new ApiError(200, 'INVALID_RESPONSE', '重建索引接口返回了无效数据。');
  }
  return data;
}
