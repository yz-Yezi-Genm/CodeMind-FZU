/**
 * 模拟数据的契约枚举校验。
 * 单独成文件，避免把 JSON 导入带进不需要它的地方（Node 直接跑 TypeScript
 * 测试时，JSON 导入需要 import attributes，Vite 与 Node 的写法并不完全一致）。
 */
import type { AdminDocument } from '../shared/types';

const SOURCE_VALUES = new Set(['pending', 'partial', 'verified', 'failed']);
const TIMELINESS_VALUES = new Set([
  'pending',
  'current',
  'historical',
  'superseded',
  'expired',
  'uncertain',
]);
const EXTRACTION_VALUES = new Set(['pending', 'extracted', 'needs_ocr', 'failed']);
const RETRIEVAL_VALUES = new Set(['blocked', 'review_only', 'enabled']);

/**
 * 契约升级或枚举改动时这里会立刻报错，避免页面悄悄显示契约外的状态。
 */
export function validateMockDocuments(items: readonly AdminDocument[]): void {
  items.forEach((item, index) => {
    const where = `模拟数据第 ${index + 1} 条（${item.record_code || item.document_id}）`;
    if (!SOURCE_VALUES.has(item.source_verification_status)) {
      throw new Error(`${where} 的来源核验状态不在契约枚举内：${item.source_verification_status}`);
    }
    if (!TIMELINESS_VALUES.has(item.timeliness_verification_status)) {
      throw new Error(`${where} 的时效核验状态不在契约枚举内：${item.timeliness_verification_status}`);
    }
    if (!EXTRACTION_VALUES.has(item.extraction_status)) {
      throw new Error(`${where} 的正文提取状态不在契约枚举内：${item.extraction_status}`);
    }
    if (!RETRIEVAL_VALUES.has(item.retrieval_status)) {
      throw new Error(`${where} 的检索开放状态不在契约枚举内：${item.retrieval_status}`);
    }
  });
}
