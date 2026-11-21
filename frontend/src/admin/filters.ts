/**
 * 后台资料列表的纯逻辑层：搜索、筛选、分页、统计。
 * 这里不碰 DOM，便于用 node:test 直接跑（见 frontend/tests/admin-filters.test.ts）。
 *
 * 说明：Alpha 阶段后台管理 API 未实现，页面在模拟数据上做客户端筛选与分页；
 * 等 GET /api/v1/admin/documents 接入后，分页交给服务端，本文件的筛选函数仍可用于
 * 服务端未支持的组合筛选，或作为前后端一致性对照。
 */
import type {
  AdminDocument,
  ExtractionStatus,
  RetrievalStatus,
  SourceVerificationStatus,
  TimelinessVerificationStatus,
} from '../shared/types';

/** 空字符串表示「全部」，其余取值必须是契约枚举值。 */
export interface DocumentFilters {
  category: string;
  source: SourceVerificationStatus | '';
  timeliness: TimelinessVerificationStatus | '';
  extraction: ExtractionStatus | '';
  retrieval: RetrievalStatus | '';
}

export const EMPTY_FILTERS: DocumentFilters = {
  category: '',
  source: '',
  timeliness: '',
  extraction: '',
  retrieval: '',
};

/** 契约建议分页：默认 20，最大 100。 */
export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  page_count: number;
}

export interface AdminStats {
  total: number;
  sourceCounts: Record<string, number>;
  timelinessCounts: Record<string, number>;
  extractionCounts: Record<string, number>;
  retrievalCounts: Record<string, number>;
  categoryCount: Record<string, number>;
  sourcePending: number;
  sourcePartial: number;
  sourceVerified: number;
  timelinessPending: number;
  extractionNeedsOcr: number;
  retrievalReviewOnly: number;
  retrievalEnabled: number;
  retrievalBlocked: number;
}

function normalize(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

/** 搜索命中范围：资料名称、资料编号、发布单位、文号、类别（契约未定义搜索端点，属前端本地筛选）。 */
export function matchesQuery(doc: AdminDocument, rawQuery: string): boolean {
  const query = normalize(rawQuery);
  if (!query) {
    return true;
  }
  const haystack = [
    doc.title,
    doc.record_code,
    doc.publisher,
    doc.document_number,
    doc.category_name,
  ]
    .map((field) => normalize(field))
    .join('\n');
  return haystack.includes(query);
}

export function matchesFilters(doc: AdminDocument, filters: DocumentFilters): boolean {
  if (filters.category && doc.category_name !== filters.category) {
    return false;
  }
  if (filters.source && doc.source_verification_status !== filters.source) {
    return false;
  }
  if (filters.timeliness && doc.timeliness_verification_status !== filters.timeliness) {
    return false;
  }
  if (filters.extraction && doc.extraction_status !== filters.extraction) {
    return false;
  }
  if (filters.retrieval && doc.retrieval_status !== filters.retrieval) {
    return false;
  }
  return true;
}

export function filterDocuments(
  documents: readonly AdminDocument[],
  query: string,
  filters: DocumentFilters,
): AdminDocument[] {
  return documents.filter((doc) => matchesQuery(doc, query) && matchesFilters(doc, filters));
}

export function hasActiveFilters(filters: DocumentFilters): boolean {
  return Boolean(
    filters.category || filters.source || filters.timeliness || filters.extraction || filters.retrieval,
  );
}

function safePageSize(pageSize: number): number {
  if (!Number.isFinite(pageSize) || pageSize < 1) {
    return DEFAULT_PAGE_SIZE;
  }
  return Math.min(Math.floor(pageSize), MAX_PAGE_SIZE);
}

/**
 * 分页。页码越界时钳制到有效范围并回写 `page`，
 * 空结果固定返回第 1 页、`page_count = 1`，避免出现「第 0 页」或「共 0 页」。
 */
export function paginate<T>(items: readonly T[], page: number, pageSize: number = DEFAULT_PAGE_SIZE): PageResult<T> {
  const size = safePageSize(pageSize);
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / size));
  const requested = Number.isFinite(page) ? Math.floor(page) : 1;
  const current = Math.min(Math.max(requested, 1), pageCount);
  const start = (current - 1) * size;
  return {
    items: items.slice(start, start + size),
    total,
    page: current,
    page_size: size,
    page_count: pageCount,
  };
}

export function countBy<T>(items: readonly T[], pick: (item: T) => string): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = pick(item);
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
}

export function computeStats(documents: readonly AdminDocument[]): AdminStats {
  const sourceCounts = countBy(documents, (doc) => doc.source_verification_status);
  const timelinessCounts = countBy(documents, (doc) => doc.timeliness_verification_status);
  const extractionCounts = countBy(documents, (doc) => doc.extraction_status);
  const retrievalCounts = countBy(documents, (doc) => doc.retrieval_status);
  return {
    total: documents.length,
    sourceCounts,
    timelinessCounts,
    extractionCounts,
    retrievalCounts,
    categoryCount: countBy(documents, (doc) => doc.category_name),
    sourcePending: sourceCounts.pending ?? 0,
    sourcePartial: sourceCounts.partial ?? 0,
    sourceVerified: sourceCounts.verified ?? 0,
    timelinessPending: timelinessCounts.pending ?? 0,
    extractionNeedsOcr: extractionCounts.needs_ocr ?? 0,
    retrievalReviewOnly: retrievalCounts.review_only ?? 0,
    retrievalEnabled: retrievalCounts.enabled ?? 0,
    retrievalBlocked: retrievalCounts.blocked ?? 0,
  };
}

/** 类别下拉的选项：按现有资料里出现过的类别去重排序。 */
export function categoryOptions(documents: readonly AdminDocument[]): string[] {
  return [...new Set(documents.map((doc) => doc.category_name))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
}
