/**
 * 后台资料状态的中文映射。
 * 枚举值一律来自 docs/assignment-03/interface-contract-v1.md 第 4.2 节，
 * 前端只负责「值 → 中文 + 视觉语气」的映射，不新增状态值。
 */
import type {
  ExtractionStatus,
  RetrievalStatus,
  SourceVerificationStatus,
  TimelinessVerificationStatus,
} from '../shared/types';

export type StatusField = 'source' | 'timeliness' | 'extraction' | 'retrieval';

/** 语气只影响颜色，状态含义一律同时用文字表达（不靠颜色单独传达）。 */
export type StatusTone = 'ok' | 'warn' | 'danger' | 'muted';

export interface StatusMeta {
  label: string;
  tone: StatusTone;
}

export const SOURCE_STATUS: Record<SourceVerificationStatus, StatusMeta> = {
  pending: { label: '待核验', tone: 'muted' },
  partial: { label: '部分核验', tone: 'warn' },
  verified: { label: '已核验', tone: 'ok' },
  failed: { label: '核验失败', tone: 'danger' },
};

export const TIMELINESS_STATUS: Record<TimelinessVerificationStatus, StatusMeta> = {
  pending: { label: '待核验', tone: 'muted' },
  current: { label: '当前有效', tone: 'ok' },
  historical: { label: '历史参考', tone: 'warn' },
  superseded: { label: '已被替代', tone: 'danger' },
  expired: { label: '已过期', tone: 'danger' },
  uncertain: { label: '时效不明', tone: 'warn' },
};

export const EXTRACTION_STATUS: Record<ExtractionStatus, StatusMeta> = {
  pending: { label: '待提取', tone: 'muted' },
  extracted: { label: '已提取', tone: 'ok' },
  needs_ocr: { label: '需 OCR', tone: 'warn' },
  failed: { label: '提取失败', tone: 'danger' },
};

export const RETRIEVAL_STATUS: Record<RetrievalStatus, StatusMeta> = {
  blocked: { label: '未开放', tone: 'muted' },
  review_only: { label: '仅审核可见', tone: 'warn' },
  enabled: { label: '已开放检索', tone: 'ok' },
};

const TABLES: Record<StatusField, Record<string, StatusMeta>> = {
  source: SOURCE_STATUS,
  timeliness: TIMELINESS_STATUS,
  extraction: EXTRACTION_STATUS,
  retrieval: RETRIEVAL_STATUS,
};

export const STATUS_FIELD_LABEL: Record<StatusField, string> = {
  source: '来源核验',
  timeliness: '时效核验',
  extraction: '正文提取',
  retrieval: '检索开放',
};

/** 筛选项顺序固定为枚举声明顺序，便于表格横向对比。 */
export const STATUS_OPTIONS: Record<StatusField, Array<{ value: string; label: string }>> = {
  source: Object.entries(SOURCE_STATUS).map(([value, meta]) => ({ value, label: meta.label })),
  timeliness: Object.entries(TIMELINESS_STATUS).map(([value, meta]) => ({ value, label: meta.label })),
  extraction: Object.entries(EXTRACTION_STATUS).map(([value, meta]) => ({ value, label: meta.label })),
  retrieval: Object.entries(RETRIEVAL_STATUS).map(([value, meta]) => ({ value, label: meta.label })),
};

/**
 * 取状态的中文与语气。契约外的取值不静默当成正常状态，
 * 而是标成「契约外取值」并按危险语气显示，避免脏数据被当成合法状态。
 */
export function statusMeta(field: StatusField, value: string): StatusMeta {
  const table = TABLES[field];
  const hit = Object.prototype.hasOwnProperty.call(table, value) ? table[value] : undefined;
  if (hit) {
    return hit;
  }
  return { label: `契约外取值：${value || '空'}`, tone: 'danger' };
}

/** 仅取中文文案，未知值同样显式标注。 */
export function statusText(field: StatusField, value: string): string {
  return statusMeta(field, value).label;
}

/** 「全部」筛选项的空值哨兵。 */
export const FILTER_ALL = '';
