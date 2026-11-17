/**
 * 后台管理端的模拟数据。
 *
 * 来源：第二次团队作业已合并的 44 条资料登记
 *   docs/assignment-02/database-design/sql/02_review_seed_44.sql
 *   docs/assignment-02/database-design/knowledge-base/入库预览_44条.json
 * 四个状态字段是 Alpha 演示编排，不是数据库读取结果，也不是真实核验结论。
 * 口径与逐条规则见 docs/assignment-03/admin/数据口径与契约缺口说明.md。
 */
import type { AdminDocument } from '../shared/types';
import raw from './data/documents.json';
import { validateMockDocuments } from './validate';

export interface MockMeta {
  dataset: string;
  record_count: number;
  notice: string;
  status_contract: string;
  source_file: string;
  generated_at: string;
}

export const MOCK_META = raw._meta as MockMeta;

const MOCK_DOCUMENTS = raw.items as unknown as AdminDocument[];

validateMockDocuments(MOCK_DOCUMENTS);

/** 返回模拟资料的副本，页面内的演示修改不会污染模块级常量。 */
export function loadMockDocuments(): AdminDocument[] {
  return MOCK_DOCUMENTS.map((doc) => ({
    ...doc,
    applicability: { ...doc.applicability },
  }));
}

export const MOCK_DOCUMENT_COUNT = MOCK_DOCUMENTS.length;
