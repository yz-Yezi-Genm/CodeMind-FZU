/**
 * 后台管理端的 HTML 片段构造。
 * 只用字符串拼装 + escapeHtml，不引入任何 UI 框架（与前端工程约定一致）。
 */
import { escapeHtml } from '../shared/dom';
import fzuLogo from '../shared/assets/fzu.png';
import type { AdminDocument } from '../shared/types';
import { categoryOptions, type AdminStats, type DocumentFilters, type PageResult } from './filters';
import {
  STATUS_FIELD_LABEL,
  STATUS_OPTIONS,
  type StatusField,
  statusMeta,
} from './status';

export type AdminView = 'dashboard' | 'documents';
export type DataSource = 'api' | 'demo';
export type NoticeType = 'success' | 'error' | 'info';

export interface Notice {
  type: NoticeType;
  text: string;
}

export interface ApiNotice {
  code: string;
  message: string;
}

const NAV_ITEMS: Array<{ view: AdminView | null; label: string }> = [
  { view: 'dashboard', label: '管理概览' },
  { view: 'documents', label: '资料管理' },
  { view: null, label: '资料审核' },
  { view: null, label: '用户管理' },
  { view: null, label: '数据来源' },
  { view: null, label: '运行与反馈' },
  { view: null, label: '角色与权限' },
  { view: null, label: '反馈处理' },
  { view: null, label: '操作审计' },
];

function badge(field: StatusField, value: string): string {
  const meta = statusMeta(field, value);
  return `<span class="badge badge--${meta.tone}" title="${escapeHtml(`${STATUS_FIELD_LABEL[field]}：${value}`)}">${escapeHtml(meta.label)}</span>`;
}

function dash(value: string | null | undefined): string {
  const text = (value ?? '').trim();
  return text ? escapeHtml(text) : '<span class="dash">—</span>';
}

/**
 * 来源链接只允许 http / https，避免 javascript:、data:、file: 等协议
 * 被渲染成可点击链接。非法或缺失的链接不渲染 <a>，改按纯文本展示。
 */
export function safeHttpUrl(url: string | null | undefined): string | null {
  const raw = (url ?? '').trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.href;
  } catch {
    return null;
  }
}

function renderSourceLink(url: string | null | undefined): string {
  const safe = safeHttpUrl(url);
  if (safe) {
    return `<a class="ext-link" href="${escapeHtml(safe)}" target="_blank" rel="noreferrer noopener">${escapeHtml(safe)}</a>`;
  }
  const raw = (url ?? '').trim();
  if (!raw) {
    return '<span class="dash">—</span>';
  }
  return `${escapeHtml(raw)} <span class="link-blocked">（非 HTTP/HTTPS 链接，未渲染为可点击链接）</span>`;
}

/** 页面外壳：侧栏 + 顶栏 + 内容容器。只在视图切换时整体重绘。 */
export function renderShell(options: {
  view: AdminView;
  source: DataSource;
  apiNotice: ApiNotice | null;
  mockCount: number;
}): string {
  const nav = NAV_ITEMS.map((item) => {
    if (!item.view) {
      return `<span class="nav-item nav-item--disabled" title="本轮 Alpha 冲刺未实现">${escapeHtml(item.label)}<span class="nav-tag">后续迭代</span></span>`;
    }
    const active = item.view === options.view ? ' nav-item--active' : '';
    return `<button type="button" class="nav-item${active}" data-action="switch-view" data-view="${item.view}"${item.view === options.view ? ' aria-current="page"' : ''}>${escapeHtml(item.label)}</button>`;
  }).join('');

  const sourceBadge = options.source === 'api'
    ? '<span class="source-pill source-pill--api">数据来源：后端接口</span>'
    : '<span class="source-pill source-pill--demo">数据来源：前端模拟数据</span>';

  const banner = options.source === 'demo'
    ? `<div class="banner banner--warn" role="note">
        <strong>模拟数据声明：</strong>本页 ${options.mockCount} 条资料是前端内置的演示数据，不是数据库读取结果，也不是真实核验结论。
        ${options.apiNotice
          ? `后台管理接口当前不可用（<code>${escapeHtml(options.apiNotice.code)}</code>：${escapeHtml(options.apiNotice.message)}）。`
          : ''}
        状态编排口径见 <code>docs/assignment-03/admin/数据口径与契约缺口说明.md</code>。
      </div>`
    : '';

  return `
    <div class="admin-shell">
      <aside class="sidebar">
        <div class="brand">
          <img class="brand-mark" src="${fzuLogo}" alt="福州大学校徽" width="40" height="40" />
          <span class="brand-text">
            <strong>CodeMind-FZU</strong>
            <small>福州大学 · 校园成长助手</small>
          </span>
        </div>
        <p class="sidebar-group">管理工作台</p>
        <nav class="nav" aria-label="后台管理导航">${nav}</nav>
        <div class="sidebar-foot">
          <p class="sidebar-note">仅管理员可维护公共资料与规则</p>
          <a class="sidebar-back" href="/index.html">返回学生工作台</a>
          <p class="sidebar-account">管理员 · 演示账号</p>
        </div>
      </aside>

      <div class="admin-main">
        <header class="topbar">
          <h1 class="topbar-title">管理控制台</h1>
          <div class="topbar-side">
            ${sourceBadge}
            <span class="topbar-user" aria-hidden="true">管</span>
          </div>
        </header>
        <main class="admin-content" id="admin-content">
          ${banner}
          <div id="admin-notice" class="notice-slot" aria-live="polite"></div>
          <div id="admin-view"></div>
          <footer class="admin-footer">
            <p>来源、正文、时效与检索开放分别记录：正文已提取、索引已建立都不等于政策已核验，也不等于可以进入正式问答检索。</p>
            <p>当前后台管理 API 尚未完成认证授权，仅用于本地开发与受控测试，不部署到公网。</p>
          </footer>
        </main>
      </div>

      <div id="admin-modal" class="modal-root" hidden></div>
      <div id="admin-toast" class="toast-root" aria-live="polite" aria-atomic="true"></div>
    </div>
  `;
}

/** 首页：统计卡 + 待办 + 状态分布。 */
export interface DashboardOptions {
  source: DataSource;
  /** 数据口径说明：模拟数据与后端接口不能共用同一句文案。 */
  note: string;
}

export function renderDashboard(stats: AdminStats, options: DashboardOptions): string {
  const totalHint = options.source === 'demo' ? '当前模拟数据集' : '后端接口返回';
  const pending = [
    {
      title: `来源核验待完成 ${stats.sourcePending + stats.sourcePartial} 条`,
      hint: `其中待核验 ${stats.sourcePending} 条、部分核验 ${stats.sourcePartial} 条；核验未完成前不应作为正式回答依据。`,
      filter: { label: '来源核验 = 待核验', params: 'f_source=pending' },
    },
    {
      title: `时效尚未核验 ${stats.timelinessPending} 条`,
      hint: '登记了发布日期不代表时效已确认，需要逐条核对现行 / 已废止 / 已过期。',
      filter: { label: '时效核验 = 待核验', params: 'f_timeliness=pending' },
    },
    {
      title: `正文提取异常 ${stats.extractionNeedsOcr} 条`,
      hint: '扫描件无文本层，需要 OCR 后才能进入切片与索引。',
      filter: { label: '正文提取 = 需 OCR', params: 'f_extraction=needs_ocr' },
    },
    {
      title: `仅审核可见、尚未开放检索 ${stats.retrievalReviewOnly} 条`,
      hint: '开放检索需要同时满足：首版纳入、来源已核验、正文已提取、时效已明确。',
      filter: { label: '检索开放 = 仅审核可见', params: 'f_retrieval=review_only' },
    },
  ]
    .map(
      (item) => `
      <li class="todo">
        <div class="todo-main">
          <p class="todo-title">${escapeHtml(item.title)}</p>
          <p class="todo-hint">${escapeHtml(item.hint)}</p>
        </div>
        <a class="todo-link" href="?view=documents&${item.filter.params}">${escapeHtml(item.filter.label)} →</a>
      </li>`,
    )
    .join('');

  const card = (label: string, value: number, hint: string, tone = ''): string => `
    <div class="stat-card${tone ? ` stat-card--${tone}` : ''}">
      <p class="stat-label">${escapeHtml(label)}</p>
      <p class="stat-value">${value}</p>
      <p class="stat-hint">${escapeHtml(hint)}</p>
    </div>`;

  const distribution = (['source', 'timeliness', 'extraction', 'retrieval'] as StatusField[])
    .map((field) => {
      const counts = countStatus(stats, field);
      const cells = STATUS_OPTIONS[field]
        .map((option) => {
          const value = counts[option.value] ?? 0;
          return `<span class="dist-cell"><span class="dist-label">${escapeHtml(option.label)}</span><span class="dist-value">${value}</span></span>`;
        })
        .join('');
      return `
        <div class="dist-row">
          <p class="dist-title">${escapeHtml(STATUS_FIELD_LABEL[field])}</p>
          <div class="dist-cells">${cells}</div>
        </div>`;
    })
    .join('');

  return `
    <section class="view-head">
      <h2>管理概览</h2>
      <p class="view-sub">维护可信资料与领域 Agent，让每一次回答都有依据。本轮 Alpha 冲刺只落地「资料管理」。</p>
    </section>

    <section class="stat-grid" aria-label="资料状态统计">
      ${card('资料总数', stats.total, totalHint, '')}
      ${card('来源待核验', stats.sourcePending, `另有部分核验 ${stats.sourcePartial} 条`, stats.sourcePending > 0 ? 'warn' : '')}
      ${card('已开放检索', stats.retrievalEnabled, `仅审核可见 ${stats.retrievalReviewOnly} 条`, '')}
      ${card('正文提取异常', stats.extractionNeedsOcr, '扫描件需要 OCR', stats.extractionNeedsOcr > 0 ? 'warn' : '')}
    </section>

    <section class="card">
      <header class="card-head">
        <h3>待办事项</h3>
        <p class="card-sub">点击可跳到资料列表并自动套用筛选条件。</p>
      </header>
      <ul class="todo-list">${pending}</ul>
    </section>

    <section class="card">
      <header class="card-head">
        <h3>状态分布</h3>
        <p class="card-sub">四个维度独立记录，互不替代。<span class="muted">${escapeHtml(options.note)}</span></p>
      </header>
      <div class="dist-list">${distribution}</div>
    </section>
  `;
}

function countStatus(stats: AdminStats, field: StatusField): Record<string, number> {
  switch (field) {
    case 'source':
      return stats.sourceCounts;
    case 'timeliness':
      return stats.timelinessCounts;
    case 'extraction':
      return stats.extractionCounts;
    case 'retrieval':
      return stats.retrievalCounts;
    default:
      return {};
  }
}

export interface DocumentsViewOptions {
  documents: readonly AdminDocument[];
  filters: DocumentFilters;
  query: string;
  page: PageResult<AdminDocument>;
  totalBeforeFilter: number;
  demoMode: boolean;
}

export function renderDocumentsView(options: DocumentsViewOptions): string {
  const categories = categoryOptions(options.documents);
  const categorySelect = [
    `<option value="">全部类别</option>`,
    ...categories.map(
      (name) => `<option value="${escapeHtml(name)}"${options.filters.category === name ? ' selected' : ''}>${escapeHtml(name)}</option>`,
    ),
  ].join('');

  const statusSelect = (field: StatusField, key: keyof DocumentFilters): string => {
    const current = options.filters[key];
    const items = [
      `<option value="">全部</option>`,
      ...STATUS_OPTIONS[field].map(
        (option) => `<option value="${option.value}"${current === option.value ? ' selected' : ''}>${escapeHtml(option.label)}</option>`,
      ),
    ].join('');
    return `<select class="select" data-filter="${key}" aria-label="${escapeHtml(STATUS_FIELD_LABEL[field])}筛选">${items}</select>`;
  };

  return `
    <section class="view-head">
      <h2>知识库资料列表</h2>
      <p class="view-sub">共 ${options.totalBeforeFilter} 条资料。列表展示来源、时效、正文与检索四个独立状态；「发布单位」取自数据库 <code>publisher</code> 字段，契约 <code>DocumentSummary</code> 暂未暴露（见缺口说明）。</p>
    </section>

    <section class="card card--flush">
      <div class="toolbar">
        <div class="toolbar-search">
          <input
            id="doc-search"
            class="input"
            type="search"
            placeholder="搜索资料名称、资料编号、发布单位、文号"
            value="${escapeHtml(options.query)}"
            autocomplete="off"
            aria-label="搜索资料"
          />
        </div>
        <div class="toolbar-filters">
          <select class="select" data-filter="category" aria-label="资料类别筛选">${categorySelect}</select>
          ${statusSelect('source', 'source')}
          ${statusSelect('timeliness', 'timeliness')}
          ${statusSelect('extraction', 'extraction')}
          ${statusSelect('retrieval', 'retrieval')}
          <button type="button" class="btn btn--ghost" data-action="reset-filters">清空筛选</button>
        </div>
        <div class="toolbar-actions">
          <button type="button" class="btn btn--primary" data-action="open-upload">导入资料</button>
          ${options.demoMode ? '<button type="button" class="btn btn--ghost" data-action="reset-demo">重置演示数据</button>' : ''}
        </div>
      </div>
      <p class="result-count" id="doc-count">${renderCount(options)}</p>
      <div class="table-wrap" id="doc-table">${renderTable(options.page, options.demoMode)}</div>
      <div class="pagination-slot" id="doc-pagination">${renderPagination(options.page)}</div>
    </section>
  `;
}

export function renderCount(options: {
  page: PageResult<AdminDocument>;
  totalBeforeFilter: number;
  query: string;
  filters: DocumentFilters;
}): string {
  const active = describeFilters(options.filters);
  const parts = [`共命中 ${options.page.total} 条`];
  if (options.query.trim()) {
    parts.push(`关键词「${escapeHtml(options.query.trim())}」`);
  }
  if (active.length > 0) {
    parts.push(active.map((label) => escapeHtml(label)).join(' · '));
  }
  if (options.page.total !== options.totalBeforeFilter) {
    parts.push(`数据集共 ${options.totalBeforeFilter} 条`);
  }
  return parts.join('｜');
}

export function describeFilters(filters: DocumentFilters): string[] {
  const labels: string[] = [];
  if (filters.category) labels.push(`类别 ${filters.category}`);
  if (filters.source) labels.push(`${STATUS_FIELD_LABEL.source} ${statusMeta('source', filters.source).label}`);
  if (filters.timeliness) labels.push(`${STATUS_FIELD_LABEL.timeliness} ${statusMeta('timeliness', filters.timeliness).label}`);
  if (filters.extraction) labels.push(`${STATUS_FIELD_LABEL.extraction} ${statusMeta('extraction', filters.extraction).label}`);
  if (filters.retrieval) labels.push(`${STATUS_FIELD_LABEL.retrieval} ${statusMeta('retrieval', filters.retrieval).label}`);
  return labels;
}

export function renderTable(page: PageResult<AdminDocument>, demoMode: boolean): string {
  if (page.total === 0) {
    return `
      <div class="empty" role="status">
        <p class="empty-title">没有符合条件的资料</p>
        <p class="empty-hint">当前筛选条件下没有记录。可以清空筛选，或换一个关键词再试。</p>
        <button type="button" class="btn btn--primary" data-action="reset-filters">清空筛选</button>
      </div>`;
  }

  const rows = page.items
    .map((doc) => {
      const title = escapeHtml(doc.title);
      const sub = [doc.record_code, doc.document_number].filter((part) => Boolean(part)).map((part) => escapeHtml(part as string)).join(' · ');
      const demoTag = (doc as AdminDocument & { demo_added?: boolean }).demo_added
        ? '<span class="badge badge--warn">演示新增</span>'
        : '';
      return `
        <tr>
          <td class="cell-title">
            <span class="title-line">${title}${demoTag}</span>
            <span class="title-sub">${sub || '<span class="dash">—</span>'}</span>
          </td>
          <td>${dash(doc.category_name)}</td>
          <td>${dash(doc.publisher)}</td>
          <td>${badge('source', doc.source_verification_status)}</td>
          <td>${badge('timeliness', doc.timeliness_verification_status)}</td>
          <td>${badge('extraction', doc.extraction_status)}</td>
          <td>${badge('retrieval', doc.retrieval_status)}</td>
          <td class="cell-date">${dash(doc.updated_at ? doc.updated_at.slice(0, 10) : null)}</td>
          <td class="cell-actions">
            <button type="button" class="link-btn" data-action="open-detail" data-id="${escapeHtml(doc.document_id)}">详情</button>
            <button type="button" class="link-btn" data-action="open-edit" data-id="${escapeHtml(doc.document_id)}">编辑</button>
            <button type="button" class="link-btn" data-action="open-reindex" data-id="${escapeHtml(doc.document_id)}">重建索引</button>
          </td>
        </tr>`;
    })
    .join('');

  return `
    <table class="table">
      <caption class="visually-hidden">知识库资料列表，含来源、时效、正文提取与检索开放四个状态列</caption>
      <colgroup>
        <col class="col-title" />
        <col class="col-category" />
        <col class="col-publisher" />
        <col class="col-status" />
        <col class="col-status" />
        <col class="col-status" />
        <col class="col-status" />
        <col class="col-date" />
        <col class="col-actions" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">资料名称</th>
          <th scope="col">资料类别</th>
          <th scope="col">发布单位或来源</th>
          <th scope="col">来源核验</th>
          <th scope="col">时效核验</th>
          <th scope="col">正文提取</th>
          <th scope="col">检索开放</th>
          <th scope="col">更新</th>
          <th scope="col">操作</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${demoMode ? '<p class="table-note">本表为前端模拟数据；行内「编辑」「重建索引」写入后端的能力尚未实现，点击后会在弹窗中如实说明。</p>' : ''}
  `;
}

export function renderPagination(page: PageResult<AdminDocument>): string {
  if (page.total === 0) {
    return '';
  }
  const prevDisabled = page.page <= 1 ? ' disabled' : '';
  const nextDisabled = page.page >= page.page_count ? ' disabled' : '';
  return `
    <div class="pagination">
      <span class="page-info">第 ${page.page} / ${page.page_count} 页 · 每页 ${page.page_size} 条 · 共 ${page.total} 条</span>
      <div class="page-buttons">
        <button type="button" class="btn btn--ghost" data-action="goto-page" data-page="${page.page - 1}"${prevDisabled}>上一页</button>
        <button type="button" class="btn btn--ghost" data-action="goto-page" data-page="${page.page + 1}"${nextDisabled}>下一页</button>
      </div>
    </div>`;
}

/* ============================== 弹窗 ============================== */

export function renderDetailModal(doc: AdminDocument, demoMode: boolean): string {
  const rows: Array<[string, string]> = [
    ['资料编号', dash(doc.record_code)],
    ['资料类别', dash(doc.category_name)],
    ['资料类型', dash(doc.document_type)],
    ['发布单位', dash(doc.publisher)],
    ['负责部门', dash(doc.responsible_department)],
    ['文号', dash(doc.document_number)],
    ['版本', dash(doc.version_no)],
    ['发布日期', dash(doc.published_on)],
    ['生效日期', dash(doc.effective_on)],
    ['截止日期', dash(doc.deadline_on)],
    ['适用年级', dash(doc.applicability.grade)],
    ['适用专业', dash(doc.applicability.major)],
    ['适用对象', dash(doc.applicability.target)],
    ['登记政策状态', dash(doc.policy_status)],
    ['来源核验日期', dash(doc.verified_on)],
    ['更新时间', dash(doc.updated_at ? doc.updated_at.slice(0, 10) : null)],
  ];

  const statusRows = (['source', 'timeliness', 'extraction', 'retrieval'] as StatusField[])
    .map((field) => {
      const value = pickStatus(doc, field);
      return `<div class="status-line"><span class="status-name">${escapeHtml(STATUS_FIELD_LABEL[field])}</span>${badge(field, value)}<code class="status-code">${escapeHtml(value)}</code></div>`;
    })
    .join('');

  return `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-head">
        <div>
          <h3 id="modal-title">资料详情</h3>
          <p class="modal-sub">${escapeHtml(doc.title)}</p>
        </div>
        <button type="button" class="icon-btn" data-action="close-modal" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <div class="status-block">${statusRows}</div>
        <dl class="def-list">
          ${rows.map(([label, value]) => `<div class="def-row"><dt>${escapeHtml(label)}</dt><dd>${value}</dd></div>`).join('')}
        </dl>
        <div class="def-row def-row--wide">
          <dt>来源链接</dt>
          <dd>${renderSourceLink(doc.source_url)}</dd>
        </div>
        <div class="def-row def-row--wide">
          <dt>核查说明</dt>
          <dd>${dash(doc.verification_note)}</dd>
        </div>
        <p class="modal-hint">
          来源、正文、时效与检索开放是四个独立维度：正文已提取、索引已建立都不等于政策已核验，也不等于可以进入正式问答检索。
          ${demoMode ? '<br />本条记录来自前端模拟数据。' : ''}
        </p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn--ghost" data-action="close-modal">关闭</button>
        <button type="button" class="btn btn--ghost" data-action="open-edit" data-id="${escapeHtml(doc.document_id)}">编辑元数据</button>
        <button type="button" class="btn btn--primary" data-action="open-reindex" data-id="${escapeHtml(doc.document_id)}">重建索引</button>
      </div>
    </div>`;
}

function pickStatus(doc: AdminDocument, field: StatusField): string {
  switch (field) {
    case 'source':
      return doc.source_verification_status;
    case 'timeliness':
      return doc.timeliness_verification_status;
    case 'extraction':
      return doc.extraction_status;
    case 'retrieval':
      return doc.retrieval_status;
    default:
      return '';
  }
}

export function renderEditModal(doc: AdminDocument, categories: readonly string[]): string {
  const field = (name: string, label: string, value: string | null, type = 'text', hint = ''): string => `
    <label class="form-field">
      <span class="form-label">${escapeHtml(label)}</span>
      <input class="input" type="${type}" name="${name}" value="${escapeHtml(value ?? '')}" />
      ${hint ? `<span class="form-hint">${escapeHtml(hint)}</span>` : ''}
    </label>`;

  const categorySelect = categories
    .map(
      (name) =>
        `<option value="${escapeHtml(name)}"${name === doc.category_name ? ' selected' : ''}>${escapeHtml(name)}</option>`,
    )
    .join('');

  return `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <form data-form="edit" data-id="${escapeHtml(doc.document_id)}" novalidate>
        <div class="modal-head">
          <div>
            <h3 id="modal-title">编辑资料元数据</h3>
            <p class="modal-sub">${escapeHtml(doc.record_code)}</p>
          </div>
          <button type="button" class="icon-btn" data-action="close-modal" aria-label="关闭">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <label class="form-field form-field--wide">
              <span class="form-label">资料名称 <em>必填</em></span>
              <input class="input" type="text" name="title" value="${escapeHtml(doc.title)}" required />
            </label>
            <label class="form-field">
              <span class="form-label">资料类别</span>
              <select class="select select--full" name="category_name">${categorySelect}</select>
            </label>
            ${field('publisher', '发布单位', doc.publisher)}
            ${field('document_number', '文号', doc.document_number)}
            ${field('document_type', '资料类型', doc.document_type)}
            ${field('published_on', '发布日期', doc.published_on, 'date')}
          </div>
          <p class="modal-hint modal-hint--warn">
            四个状态字段（来源核验 / 时效核验 / 正文提取 / 检索开放）不在此处直接修改：
            开放检索必须同时满足「首版纳入 + 来源已核验 + 正文已提取 + 时效已明确」并经人工确认，不能靠编辑表单绕过。
          </p>
          <p class="modal-hint" data-role="form-error" hidden></p>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn--ghost" data-action="close-modal">取消</button>
          <button type="submit" class="btn btn--primary" data-role="submit">保存修改</button>
        </div>
      </form>
    </div>`;
}

export function renderUploadModal(): string {
  return `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <form data-form="upload" novalidate>
        <div class="modal-head">
          <div>
            <h3 id="modal-title">导入资料</h3>
            <p class="modal-sub">上传后应触发解析与入库，再经人工核验才可能开放检索。</p>
          </div>
          <button type="button" class="icon-btn" data-action="close-modal" aria-label="关闭">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <label class="form-field form-field--wide">
              <span class="form-label">原始文件 <em>必填</em></span>
              <input class="input" type="file" name="file" accept=".html,.htm,.pdf,.docx,.doc,.xlsx,.xls,.md,.txt" />
              <span class="form-hint">支持 HTML / PDF / Word / Excel / Markdown / 纯文本；扫描件会在正文提取阶段标记为需 OCR。</span>
            </label>
            <label class="form-field form-field--wide">
              <span class="form-label">资料名称 <em>必填</em></span>
              <input class="input" type="text" name="title" placeholder="例如：福州大学本科生奖学金评定管理办法" />
            </label>
            <label class="form-field">
              <span class="form-label">资料类别</span>
              <input class="input" type="text" name="category_name" placeholder="例如：综评与奖学金" />
            </label>
            <label class="form-field">
              <span class="form-label">发布单位</span>
              <input class="input" type="text" name="publisher" placeholder="例如：福州大学学生工作部（处）" />
            </label>
            <label class="form-field">
              <span class="form-label">文号</span>
              <input class="input" type="text" name="document_number" placeholder="例如：福大学〔2026〕23号" />
            </label>
            <label class="form-field">
              <span class="form-label">发布日期</span>
              <input class="input" type="date" name="published_on" />
            </label>
          </div>
          <p class="modal-hint modal-hint--warn">
            POST /api/v1/admin/documents 尚未在本仓库实现。提交后会如实返回失败原因，不会伪造上传成功，也不会把文件写入任何位置。
          </p>
          <p class="modal-hint" data-role="form-error" hidden></p>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn--ghost" data-action="close-modal">取消</button>
          <button type="submit" class="btn btn--primary" data-role="submit">上传并登记</button>
        </div>
      </form>
    </div>`;
}

export function renderReindexModal(doc: AdminDocument, demoMode: boolean): string {
  return `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-head">
        <div>
          <h3 id="modal-title">重新建立索引</h3>
          <p class="modal-sub">${escapeHtml(doc.title)}</p>
        </div>
        <button type="button" class="icon-btn" data-action="close-modal" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <dl class="def-list">
          <div class="def-row"><dt>资料编号</dt><dd>${dash(doc.record_code)}</dd></div>
          <div class="def-row"><dt>当前正文提取</dt><dd>${badge('extraction', doc.extraction_status)}</dd></div>
          <div class="def-row"><dt>当前检索开放</dt><dd>${badge('retrieval', doc.retrieval_status)}</dd></div>
        </dl>
        <p class="modal-hint modal-hint--warn">
          重建索引只影响切片与向量索引，<strong>不会自动把检索开放改成 enabled</strong>；
          开放检索仍需满足核验前置条件并由负责人员确认。
          ${demoMode ? '当前为模拟数据模式：请求会真实发出，失败时不会伪造索引结果。' : ''}
        </p>
        ${doc.extraction_status === 'needs_ocr'
          ? '<p class="modal-hint modal-hint--error">该资料正文尚未成功提取（需 OCR），即使重建索引也不会有可用正文。</p>'
          : ''}
        <p class="modal-hint" data-role="form-error" hidden></p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn--ghost" data-action="close-modal">取消</button>
        <button type="button" class="btn btn--primary" data-action="confirm-reindex" data-id="${escapeHtml(doc.document_id)}">确认重建</button>
      </div>
    </div>`;
}
