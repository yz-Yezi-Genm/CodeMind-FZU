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
  conversation_id?: string;
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
  source_verification_status: string;
  timeliness_verification_status: string;
  retrieval_status: string;
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

export interface ApiErrorDetail {
  code: string;
  message: string;
  retryable: boolean;
}

export interface ApiErrorResponse {
  request_id: string | null;
  error: ApiErrorDetail;
}
