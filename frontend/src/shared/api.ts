import type {
  ApiErrorResponse,
  AskRequest,
  AskResponse,
  HealthResponse,
} from './types';

const API_BASE = '/api/v1';

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '无法连接后端，请检查网络或服务是否已启动。', true);
  }

  if (!response.ok) {
    let detail: ApiErrorResponse | null = null;
    try {
      detail = (await response.json()) as ApiErrorResponse;
    } catch {
      detail = null;
    }
    const code = detail?.error?.code ?? `HTTP_${response.status}`;
    const message = detail?.error?.message
      ?? (response.status >= 500 ? '后端暂不可用，请确认服务已启动。' : '请求失败，请检查后重试。');
    throw new ApiError(response.status, code, message, detail?.error?.retryable ?? false);
  }

  try {
    const data: unknown = await response.json();
    if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
      return data as T;
    }
  } catch {
    // An empty or non-JSON success response also violates the API contract.
  }
  throw new ApiError(response.status, 'INVALID_RESPONSE', '后端返回了无效数据，请稍后重试。');
}

export async function fetchHealth(): Promise<HealthResponse> {
  const health = await request<HealthResponse>('/health');
  if (health.status !== 'ok' || !health.service || !health.version) {
    throw new ApiError(200, 'INVALID_RESPONSE', '无法识别后端健康检查结果。');
  }
  return health;
}

export async function ask(payload: AskRequest): Promise<AskResponse> {
  const response = await request<AskResponse>('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const validStatus =
    (response.status === 'answered' && typeof response.answer === 'string' && !!response.answer.trim())
    || (response.status === 'needs_clarification'
      && typeof response.clarifying_question === 'string' && !!response.clarifying_question.trim())
    || (response.status === 'insufficient_evidence' && response.answer_mode === 'insufficient_data');
  if (!validStatus || !response.conversation_id || !Array.isArray(response.citations)
    || !Array.isArray(response.warnings)) {
    throw new ApiError(200, 'INVALID_RESPONSE', '问答接口返回了无效或空数据，请稍后重试。');
  }
  return response;
}
