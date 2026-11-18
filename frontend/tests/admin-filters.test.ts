/**
 * 后台管理端纯逻辑层测试（node:test，零依赖）。
 *
 * 运行方式（Node 22.18+ / 24 可直接执行 TypeScript）：
 *   cd frontend
 *   node tests/admin-filters.test.ts
 *
 * 覆盖：分页边界、关键词搜索、状态筛选、契约外取值、空结果、模拟数据合规性。
 * 正例与反例各至少一条，对应作业「至少一个正常情况和一个异常情况」的要求。
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  DEFAULT_PAGE_SIZE,
  EMPTY_FILTERS,
  MAX_PAGE_SIZE,
  categoryOptions,
  computeStats,
  filterDocuments,
  hasActiveFilters,
  matchesQuery,
  paginate,
} from '../src/admin/filters.ts';
import { statusMeta, statusText } from '../src/admin/status.ts';
import { validateMockDocuments } from '../src/admin/validate.ts';
import type { AdminDocument } from '../src/shared/types.ts';

const here = dirname(fileURLToPath(import.meta.url));
const dataset = JSON.parse(
  readFileSync(join(here, '..', 'src', 'admin', 'data', 'documents.json'), 'utf8'),
) as { items: AdminDocument[]; _meta: { record_count: number } };

const documents = dataset.items;

function makeDoc(overrides: Partial<AdminDocument> = {}): AdminDocument {
  return {
    document_id: 'doc-1',
    version_id: 'ver-1',
    record_code: '测试-2026-001',
    version_no: 'import-1',
    title: '福州大学本科生奖学金评定管理办法',
    document_type: '规范性文件',
    category_name: '综评与奖学金',
    publisher: '福州大学',
    responsible_department: '学生工作部（处）',
    document_number: '福大学〔2026〕23号',
    source_url: 'https://stuic.fzu.edu.cn/info/1032/6937.htm',
    published_on: '2026-05-18',
    effective_on: '2026-05-18',
    deadline_on: null,
    policy_status: '当前有效',
    applicability: { grade: '全体本科生', major: null, target: '全日制在校本科生' },
    source_verification_status: 'verified',
    timeliness_verification_status: 'current',
    extraction_status: 'extracted',
    retrieval_status: 'enabled',
    verification_note: null,
    verified_on: '2026-10-21',
    updated_at: '2026-10-21T00:00:00Z',
    ...overrides,
  };
}

/* ----------------------------- 正例 ----------------------------- */

test('分页：44 条按每页 20 条切分成 3 页，最后一页 4 条', () => {
  assert.equal(documents.length, 44);
  const first = paginate(documents, 1, DEFAULT_PAGE_SIZE);
  assert.equal(first.items.length, 20);
  assert.equal(first.total, 44);
  assert.equal(first.page_count, 3);

  const last = paginate(documents, 3, DEFAULT_PAGE_SIZE);
  assert.equal(last.items.length, 4);
  assert.equal(last.page, 3);
});

test('筛选：检索开放 = enabled 命中 3 条，且每条都满足契约的开放前置条件', () => {
  const enabled = filterDocuments(documents, '', { ...EMPTY_FILTERS, retrieval: 'enabled' });
  assert.equal(enabled.length, 3);

  const allowedTimeliness = new Set(['current', 'historical', 'superseded', 'expired']);
  for (const doc of enabled) {
    assert.equal(doc.source_verification_status, 'verified', `${doc.record_code} 未通过来源核验却被放开检索`);
    assert.equal(doc.extraction_status, 'extracted', `${doc.record_code} 正文未提取却被放开检索`);
    assert.ok(
      allowedTimeliness.has(doc.timeliness_verification_status),
      `${doc.record_code} 时效为 ${doc.timeliness_verification_status}，不满足开放条件`,
    );
  }
});

test('搜索：关键词命中资料名称，且大小写与首尾空格不敏感', () => {
  const hits = filterDocuments(documents, '  奖学金 ', EMPTY_FILTERS);
  assert.ok(hits.length > 0, '“奖学金”应至少命中一条资料');
  assert.ok(hits.every((doc) => matchesQuery(doc, '奖学金')));

  const upper = filterDocuments([makeDoc({ title: 'FZU Scholarship 管理办法' })], 'fzu', EMPTY_FILTERS);
  assert.equal(upper.length, 1);
});

test('搜索：可按发布单位与文号命中', () => {
  const byPublisher = filterDocuments(documents, '计算机与大数据学院', EMPTY_FILTERS);
  assert.ok(byPublisher.length > 0);
  assert.ok(byPublisher.every((doc) => `${doc.publisher ?? ''}${doc.title}`.includes('计算机')));

  const byNumber = filterDocuments([makeDoc()], '福大学〔2026〕23号', EMPTY_FILTERS);
  assert.equal(byNumber.length, 1);
});

test('统计：各状态计数之和等于总数，类别覆盖七类', () => {
  const stats = computeStats(documents);
  assert.equal(stats.total, 44);
  assert.equal(stats.sourcePending + stats.sourcePartial + stats.sourceVerified, 44);
  assert.equal(
    stats.retrievalBlocked + stats.retrievalReviewOnly + stats.retrievalEnabled,
    44,
  );
  assert.equal(categoryOptions(documents).length, 7);
});

test('模拟数据全部落在契约枚举内', () => {
  assert.doesNotThrow(() => validateMockDocuments(documents));
  assert.equal(dataset._meta.record_count, 44);
});

/* ----------------------------- 反例 ----------------------------- */

test('分页遇到越界与非法参数时被钳制，不产生第 0 页或超界页', () => {
  assert.equal(paginate(documents, 99).page, 3, '页码超过总页数应钳到最后一页');
  assert.equal(paginate(documents, 0).page, 1, '第 0 页应钳到第 1 页');
  assert.equal(paginate(documents, -5).page, 1);
  assert.equal(paginate(documents, Number.NaN).page, 1, '非数字页码应回落到第 1 页');
  assert.equal(paginate(documents, 1, 0).page_size, DEFAULT_PAGE_SIZE, '非法每页条数应回落默认值');
  assert.equal(paginate(documents, 1, 5000).page_size, MAX_PAGE_SIZE, '每页条数应被限制在 100 以内');
});

test('空结果：契约内存在但数据集中没有的状态返回空数组（页面走空态）', () => {
  const failed = filterDocuments(documents, '', { ...EMPTY_FILTERS, source: 'failed' });
  assert.equal(failed.length, 0, '演示数据不含失败样本，应返回空而不是报错');

  const page = paginate(failed, 1);
  assert.equal(page.total, 0);
  assert.equal(page.page, 1);
  assert.equal(page.page_count, 1);

  const noKeyword = filterDocuments(documents, '区块链', EMPTY_FILTERS);
  assert.equal(noKeyword.length, 0);
});

test('契约外取值不被当成合法状态：筛出 0 条，标签标为契约外', () => {
  const bogus = filterDocuments(documents, '', {
    ...EMPTY_FILTERS,
    retrieval: 'archived' as AdminDocument['retrieval_status'],
  });
  assert.equal(bogus.length, 0, '契约外状态值不应匹配任何记录');

  const meta = statusMeta('retrieval', 'archived');
  assert.equal(meta.tone, 'danger');
  assert.match(meta.label, /契约外取值/);
  assert.equal(statusMeta('retrieval', '').label.includes('空'), true);
});

test('状态中文映射与契约枚举一一对应', () => {
  assert.equal(statusText('source', 'verified'), '已核验');
  assert.equal(statusText('timeliness', 'superseded'), '已被替代');
  assert.equal(statusText('extraction', 'needs_ocr'), '需 OCR');
  assert.equal(statusText('retrieval', 'review_only'), '仅审核可见');
});

test('非法模拟数据会在装载阶段抛错，而不是静默显示', () => {
  const broken = [makeDoc({ extraction_status: 'done' as AdminDocument['extraction_status'] })];
  assert.throws(() => validateMockDocuments(broken), /正文提取状态不在契约枚举内/);
});

test('筛选状态判断：空筛选返回 false，任意一项生效返回 true', () => {
  assert.equal(hasActiveFilters(EMPTY_FILTERS), false);
  assert.equal(hasActiveFilters({ ...EMPTY_FILTERS, source: 'pending' }), true);
  assert.equal(hasActiveFilters({ ...EMPTY_FILTERS, category: '综评与奖学金' }), true);
});
