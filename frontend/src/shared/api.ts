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
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });

  if (!response.ok) {
    let detail: ApiErrorResponse | null = null;
    try {
      detail = (await response.json()) as ApiErrorResponse;
    } catch {
      detail = null;
    }
    const code = detail?.error.code ?? `HTTP_${response.status}`;
    const message = detail?.error.message ?? response.statusText;
    throw new ApiError(response.status, code, message, detail?.error.retryable ?? false);
  }

  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function ask(payload: AskRequest): Promise<AskResponse> {
  return request<AskResponse>('/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
