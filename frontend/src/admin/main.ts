/**
 * 后台管理端入口（林彦翔 · Alpha 冲刺）
 *
 * 本轮只落地「管理概览 + 知识库资料管理」。后台管理 API（契约第 10 节）尚未实现，
 * 因此页面先尝试真实接口，失败后降级到前端模拟数据；数据来源声明只在模拟数据模式下显示，
 * 切换成功后改为标注后端接口，不会把真实数据标成模拟数据。
 * 写操作（编辑 / 上传 / 重建索引）一律先发真实请求，失败时如实报错；
 * 只有在模拟数据模式下，编辑与上传才允许改前端内存，并在提示中明确标注未写入数据库。
 */
import '../shared/styles.css';
import './admin.css';
import {
  ApiError,
  listAdminDocuments,
  reindexAdminDocument,
  updateAdminDocumentMetadata,
  uploadAdminDocument,
} from '../shared/api';
import { escapeHtml, requireElement } from '../shared/dom';
import type { AdminDocument, AdminDocumentMetadataPatch, DocumentSummary } from '../shared/types';
import {
  DEFAULT_PAGE_SIZE,
  categoryOptions,
  EMPTY_FILTERS,
  MAX_PAGE_SIZE,
  computeStats,
  filterDocuments,
  paginate,
  type DocumentFilters,
  type PageResult,
} from './filters';
import { MOCK_DOCUMENT_COUNT, loadMockDocuments } from './mock';
import {
  renderDashboard,
  renderDetailModal,
  renderDocumentsView,
  renderEditModal,
  renderPagination,
  renderReindexModal,
  renderShell,
  renderTable,
  renderUploadModal,
  renderCount,
  type AdminView,
  type ApiNotice,
  type DataSource,
  type Notice,
} from './render';

type ModalKind = 'detail' | 'edit' | 'upload' | 'reindex';

interface AdminState {
  view: AdminView;
  source: DataSource;
  apiNotice: ApiNotice | null;
  documents: AdminDocument[];
  totalBeforeFilter: number;
  query: string;
  filters: DocumentFilters;
  page: number;
  pageSize: number;
  modal: ModalKind | null;
  modalDocId: string | null;
  notice: Notice | null;
  loading: boolean;
}

const state: AdminState = {
  view: 'dashboard',
  source: 'demo',
  apiNotice: null,
  documents: [],
  totalBeforeFilter: MOCK_DOCUMENT_COUNT,
  query: '',
  filters: { ...EMPTY_FILTERS },
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
  modal: null,
  modalDocId: null,
  notice: null,
  loading: true,
};

const app = requireElement<HTMLDivElement>('#app');

/* ============================ 工具 ============================ */

function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    // code 形如 HTTP_404 时不再重复输出状态码，避免出现「HTTP_404（HTTP 404）」
    const prefix = error.code.startsWith('HTTP_') ? '' : `${error.code} · `;
    const status = error.status > 0 ? `HTTP ${error.status}` : '网络异常';
    return `${prefix}${status}：${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

function apiErrorNotice(error: unknown): ApiNotice {
  if (error instanceof ApiError) {
    return { code: error.code, message: error.message };
  }
  return { code: 'UNKNOWN', message: error instanceof Error ? error.message : String(error) };
}

function findDocument(id: string | null): AdminDocument | null {
  if (!id) return null;
  return state.documents.find((doc) => doc.document_id === id) ?? null;
}

/** 契约 DocumentSummary → 页面行。契约未暴露的字段在接口模式下留空，不臆造取值。 */
function toAdminDocument(summary: DocumentSummary): AdminDocument {
  return {
    ...summary,
    publisher: null,
    responsible_department: null,
    document_number: null,
    source_url: null,
    published_on: null,
    effective_on: null,
    deadline_on: null,
    policy_status: null,
    applicability: { grade: null, major: null, target: null },
    verification_note: null,
    verified_on: null,
  };
}

/* ============================ 状态提示 ============================ */

let noticeTimer: number | null = null;

function showNotice(notice: Notice): void {
  state.notice = notice;
  const root = document.querySelector<HTMLDivElement>('#admin-toast');
  if (!root) return;
  root.innerHTML = `
    <div class="toast toast--${notice.type}" role="status">
      <span class="toast-text">${escapeHtml(notice.text)}</span>
      <button type="button" class="toast-close" data-action="dismiss-toast" aria-label="关闭提示">×</button>
    </div>`;
  if (noticeTimer !== null) {
    window.clearTimeout(noticeTimer);
  }
  noticeTimer = window.setTimeout(() => {
    dismissToast();
  }, notice.type === 'error' ? 12000 : 6000);
}

function dismissToast(): void {
  state.notice = null;
  const root = document.querySelector<HTMLDivElement>('#admin-toast');
  if (root) root.innerHTML = '';
  if (noticeTimer !== null) {
    window.clearTimeout(noticeTimer);
    noticeTimer = null;
  }
}

/* ============================ 查询与渲染 ============================ */

function currentPage(): PageResult<AdminDocument> {
  const filtered = filterDocuments(state.documents, state.query, state.filters);
  return paginate(filtered, state.page, state.pageSize);
}

function renderView(): void {
  const host = document.querySelector<HTMLDivElement>('#admin-view');
  if (!host) return;
  if (state.view === 'dashboard') {
    const stats = computeStats(state.documents);
    host.innerHTML = renderDashboard(stats, {
      source: state.source,
      note: state.source === 'demo'
        ? '数据口径：前端内置模拟数据，非数据库读取。'
        : '数据口径：后端接口返回。',
    });
  } else {
    host.innerHTML = renderDocumentsView({
      documents: state.documents,
      filters: state.filters,
      query: state.query,
      page: currentPage(),
      totalBeforeFilter: state.totalBeforeFilter,
      demoMode: state.source === 'demo',
    });
  }
}

/** 只重绘列表主体，避免搜索框在输入时丢焦点。 */
function refreshList(): void {
  const page = currentPage();
  if (page.page !== state.page) {
    state.page = page.page;
  }
  const countHost = document.querySelector<HTMLParagraphElement>('#doc-count');
  if (countHost) {
    countHost.textContent = renderCount({
      page,
      totalBeforeFilter: state.totalBeforeFilter,
      query: state.query,
      filters: state.filters,
    });
  }
  const tableHost = document.querySelector<HTMLDivElement>('#doc-table');
  if (tableHost) {
    tableHost.innerHTML = renderTable(page, state.source === 'demo');
  }
  const pageHost = document.querySelector<HTMLDivElement>('#doc-pagination');
  if (pageHost) {
    pageHost.innerHTML = renderPagination(page);
  }
  syncUrl();
}

function renderAll(): void {
  app.innerHTML = renderShell({
    view: state.view,
    source: state.source,
    apiNotice: state.apiNotice,
    mockCount: state.documents.length || MOCK_DOCUMENT_COUNT,
  });
  renderView();
  if (state.modal) {
    renderModal();
  }
  syncUrl();
}

/* ============================ 弹窗 ============================ */

function openModal(kind: ModalKind, documentId?: string | null): void {
  state.modal = kind;
  state.modalDocId = documentId ?? state.modalDocId;
  renderModal();
  syncUrl();
}

function closeModal(): void {
  state.modal = null;
  state.modalDocId = null;
  const root = document.querySelector<HTMLDivElement>('#admin-modal');
  if (root) {
    root.innerHTML = '';
    root.hidden = true;
  }
  syncUrl();
}

function renderModal(): void {
  const root = document.querySelector<HTMLDivElement>('#admin-modal');
  if (!root) return;
  const doc = findDocument(state.modalDocId);
  // 深链进入时数据还没加载完，此时不要清掉 modal 状态，等 bootstrap 完成后再渲染。
  const missing = (): void => {
    if (!state.loading) closeModal();
  };
  let html = '';
  switch (state.modal) {
    case 'detail':
      if (!doc) {
        missing();
        return;
      }
      html = renderDetailModal(doc, state.source === 'demo');
      break;
    case 'edit':
      if (!doc) {
        missing();
        return;
      }
      html = renderEditModal(doc, categoryOptions(state.documents));
      break;
    case 'upload':
      html = renderUploadModal();
      break;
    case 'reindex':
      if (!doc) {
        missing();
        return;
      }
      html = renderReindexModal(doc, state.source === 'demo');
      break;
    default:
      closeModal();
      return;
  }
  root.hidden = false;
  root.innerHTML = `<div class="modal-backdrop" data-action="close-modal"></div>${html}`;
  const focusTarget =
    root.querySelector<HTMLElement>('input, select, textarea, button.btn--primary, button[data-action="close-modal"]')
    ?? root.querySelector<HTMLElement>('button, input');
  focusTarget?.focus();
}

/* ============================ URL 同步（便于分享与截图） ============================ */

const URL_KEYS = {
  view: 'view',
  query: 'q',
  category: 'f_category',
  source: 'f_source',
  timeliness: 'f_timeliness',
  extraction: 'f_extraction',
  retrieval: 'f_retrieval',
  page: 'page',
  modal: 'modal',
  doc: 'doc',
} as const;

function syncUrl(): void {
  const params = new URLSearchParams();
  if (state.view !== 'dashboard') params.set(URL_KEYS.view, state.view);
  if (state.query.trim()) params.set(URL_KEYS.query, state.query.trim());
  if (state.filters.category) params.set(URL_KEYS.category, state.filters.category);
  if (state.filters.source) params.set(URL_KEYS.source, state.filters.source);
  if (state.filters.timeliness) params.set(URL_KEYS.timeliness, state.filters.timeliness);
  if (state.filters.extraction) params.set(URL_KEYS.extraction, state.filters.extraction);
  if (state.filters.retrieval) params.set(URL_KEYS.retrieval, state.filters.retrieval);
  if (state.page > 1) params.set(URL_KEYS.page, String(state.page));
  if (state.modal) params.set(URL_KEYS.modal, state.modal);
  if (state.modalDocId) params.set(URL_KEYS.doc, state.modalDocId);
  const search = params.toString();
  const next = search ? `${window.location.pathname}?${search}` : window.location.pathname;
  window.history.replaceState(null, '', next);
}

function readDeepLink(): void {
  const params = new URLSearchParams(window.location.search);
  const view = params.get(URL_KEYS.view);
  if (view === 'documents' || view === 'dashboard') {
    state.view = view;
  }
  state.query = params.get(URL_KEYS.query) ?? '';
  state.filters = {
    category: params.get(URL_KEYS.category) ?? '',
    source: (params.get(URL_KEYS.source) as DocumentFilters['source']) ?? '',
    timeliness: (params.get(URL_KEYS.timeliness) as DocumentFilters['timeliness']) ?? '',
    extraction: (params.get(URL_KEYS.extraction) as DocumentFilters['extraction']) ?? '',
    retrieval: (params.get(URL_KEYS.retrieval) as DocumentFilters['retrieval']) ?? '',
  };
  const page = Number(params.get(URL_KEYS.page));
  state.page = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1;
  const modal = params.get(URL_KEYS.modal);
  if (modal === 'detail' || modal === 'edit' || modal === 'upload' || modal === 'reindex') {
    state.modal = modal;
  }
  state.modalDocId = params.get(URL_KEYS.doc);
  syncUrl();
}

/* ============================ 数据装载 ============================ */

async function bootstrap(): Promise<void> {
  state.loading = true;
  renderAll();
  try {
    const response = await listAdminDocuments({ page: 1, page_size: MAX_PAGE_SIZE });
    state.source = 'api';
    state.apiNotice = null;
    state.documents = response.items.map(toAdminDocument);
    state.totalBeforeFilter = state.documents.length;
  } catch (error) {
    state.source = 'demo';
    state.apiNotice = apiErrorNotice(error);
    state.documents = loadMockDocuments();
    state.totalBeforeFilter = state.documents.length;
  } finally {
    state.loading = false;
    renderAll();
  }
}

/* ============================ 事件 ============================ */

function onClick(event: MouseEvent): void {
  const target = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  switch (action) {
    case 'switch-view': {
      const view = target.dataset.view;
      if (view === 'documents' || view === 'dashboard') {
        state.view = view;
        renderAll();
      }
      break;
    }
    case 'reset-filters': {
      state.query = '';
      state.filters = { ...EMPTY_FILTERS };
      state.page = 1;
      renderView();
      syncUrl();
      break;
    }
    case 'goto-page': {
      const page = Number(target.dataset.page);
      if (Number.isFinite(page)) {
        state.page = page;
        refreshList();
      }
      break;
    }
    case 'open-detail':
    case 'open-edit':
    case 'open-reindex': {
      openModal(action.replace('open-', '') as ModalKind, target.dataset.id ?? null);
      break;
    }
    case 'open-upload':
      openModal('upload', null);
      break;
    case 'close-modal':
      if (target.classList.contains('modal-backdrop') || target.hasAttribute('data-action')) {
        closeModal();
      }
      break;
    case 'confirm-reindex':
      void handleReindex(target.dataset.id ?? null);
      break;
    case 'dismiss-toast':
      dismissToast();
      break;
    case 'reset-demo': {
      state.documents = loadMockDocuments();
      state.totalBeforeFilter = state.documents.length;
      state.page = 1;
      renderView();
      showNotice({ type: 'info', text: '演示数据已重置为初始 44 条。' });
      break;
    }
    default:
      break;
  }
}

function onChange(event: Event): void {
  const target = event.target as HTMLElement | null;
  if (!(target instanceof HTMLSelectElement)) return;
  const key = target.dataset.filter as keyof DocumentFilters | undefined;
  if (!key) return;
  state.filters = { ...state.filters, [key]: target.value } as DocumentFilters;
  state.page = 1;
  refreshList();
}

function onInput(event: Event): void {
  const target = event.target as HTMLElement | null;
  if (!(target instanceof HTMLInputElement) || target.id !== 'doc-search') return;
  state.query = target.value;
  state.page = 1;
  refreshList();
}

function onSubmit(event: Event): void {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const kind = form.dataset.form;
  if (kind === 'edit') {
    event.preventDefault();
    void handleEdit(form);
  } else if (kind === 'upload') {
    event.preventDefault();
    void handleUpload(form);
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && state.modal) {
    closeModal();
  }
}

/* ============================ 写操作 ============================ */

function setFormError(form: HTMLFormElement, message: string | null): void {
  const hint = form.querySelector<HTMLParagraphElement>('[data-role="form-error"]');
  if (!hint) return;
  if (!message) {
    hint.hidden = true;
    hint.textContent = '';
    return;
  }
  hint.hidden = false;
  hint.className = 'modal-hint modal-hint--error';
  hint.textContent = message;
}

function setSubmitting(form: HTMLFormElement, submitting: boolean, label: string): void {
  const submit = form.querySelector<HTMLButtonElement>('[data-role="submit"]');
  if (!submit) return;
  submit.disabled = submitting;
  submit.textContent = submitting ? '提交中…' : label;
}

function readPatch(form: HTMLFormElement): AdminDocumentMetadataPatch {
  const data = new FormData(form);
  const text = (key: string): string => String(data.get(key) ?? '').trim();
  const patch: AdminDocumentMetadataPatch = {};
  const title = text('title');
  if (title) patch.title = title;
  const publisher = text('publisher');
  if (publisher) patch.publisher = publisher;
  const documentNumber = text('document_number');
  if (documentNumber) patch.document_number = documentNumber;
  const categoryName = text('category_name');
  if (categoryName) patch.category_name = categoryName;
  const documentType = text('document_type');
  if (documentType) patch.document_type = documentType;
  const publishedOn = text('published_on');
  if (publishedOn) patch.published_on = publishedOn;
  return patch;
}

async function handleEdit(form: HTMLFormElement): Promise<void> {
  const id = form.dataset.id ?? '';
  const doc = findDocument(id);
  if (!doc) {
    setFormError(form, '找不到该资料，请刷新后重试。');
    return;
  }
  const patch = readPatch(form);
  if (!patch.title) {
    setFormError(form, '资料名称不能为空。');
    return;
  }
  setFormError(form, null);
  setSubmitting(form, true, '保存修改');
  try {
    await updateAdminDocumentMetadata(id, patch);
    applyPatch(id, patch);
    closeModal();
    renderView();
    showNotice({ type: 'success', text: `已保存资料元数据：${patch.title ?? doc.title}` });
  } catch (error) {
    if (state.source === 'demo') {
      applyPatch(id, patch);
      closeModal();
      renderView();
      showNotice({
        type: 'info',
        text: `后端 PATCH 接口不可用（${formatError(error)}）。演示模式：修改只保存在当前页面内存，未写入数据库。`,
      });
      return;
    }
    setFormError(form, `保存失败：${formatError(error)}`);
  } finally {
    setSubmitting(form, false, '保存修改');
  }
}

function applyPatch(id: string, patch: AdminDocumentMetadataPatch): void {
  state.documents = state.documents.map((doc) => {
    if (doc.document_id !== id) return doc;
    return {
      ...doc,
      ...(patch.title !== undefined ? { title: patch.title } : {}),
      ...(patch.publisher !== undefined ? { publisher: patch.publisher } : {}),
      ...(patch.document_number !== undefined ? { document_number: patch.document_number } : {}),
      ...(patch.document_type !== undefined ? { document_type: patch.document_type } : {}),
      ...(patch.published_on !== undefined ? { published_on: patch.published_on } : {}),
      updated_at: new Date().toISOString(),
    };
  });
}

async function handleUpload(form: HTMLFormElement): Promise<void> {
  const data = new FormData(form);
  const file = data.get('file');
  const title = String(data.get('title') ?? '').trim();
  if (!(file instanceof File) || file.size === 0) {
    setFormError(form, '请选择要导入的原始文件。');
    return;
  }
  if (!title) {
    setFormError(form, '资料名称不能为空。');
    return;
  }
  setFormError(form, null);
  setSubmitting(form, true, '上传并登记');
  const metadata: Record<string, string> = { title };
  for (const key of ['category_name', 'publisher', 'document_number', 'published_on']) {
    const value = String(data.get(key) ?? '').trim();
    if (value) metadata[key] = value;
  }
  try {
    const response = await uploadAdminDocument(file, metadata);
    closeModal();
    showNotice({ type: 'success', text: `已提交（${response.status}）：${response.message}` });
  } catch (error) {
    if (state.source === 'demo') {
      addDemoDocument(metadata, file.name);
      closeModal();
      renderView();
      showNotice({
        type: 'info',
        text: `后端上传接口不可用（${formatError(error)}）。演示模式：只在当前页面内存中新增一条记录，文件未上传、未解析、未入库。`,
      });
      return;
    }
    setFormError(form, `上传失败：${formatError(error)}`);
  } finally {
    setSubmitting(form, false, '上传并登记');
  }
}

function addDemoDocument(metadata: Record<string, string>, fileName: string): void {
  const now = new Date();
  const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const created: AdminDocument & { demo_added?: boolean } = {
    document_id: `demo-${now.getTime()}`,
    version_id: `demo-version-${now.getTime()}`,
    record_code: `演示-${stamp}-${String(state.documents.length + 1).padStart(2, '0')}`,
    version_no: 'demo-1',
    title: metadata.title ?? fileName,
    document_type: metadata.category_name ? '演示新增' : '演示新增',
    category_name: metadata.category_name ?? '未分类',
    publisher: metadata.publisher ?? null,
    responsible_department: null,
    document_number: metadata.document_number ?? null,
    source_url: null,
    published_on: metadata.published_on ?? null,
    effective_on: null,
    deadline_on: null,
    policy_status: '演示新增；未登记政策状态',
    applicability: { grade: null, major: null, target: null },
    source_verification_status: 'pending',
    timeliness_verification_status: 'pending',
    extraction_status: 'pending',
    retrieval_status: 'blocked',
    verification_note: `演示模式新增：文件 ${fileName} 未上传，状态全部从 pending / blocked 起算。`,
    verified_on: null,
    updated_at: now.toISOString(),
    demo_added: true,
  };
  state.documents = [created, ...state.documents];
  state.totalBeforeFilter = state.documents.length;
  state.page = 1;
}

async function handleReindex(id: string | null): Promise<void> {
  const doc = findDocument(id);
  const root = document.querySelector<HTMLDivElement>('#admin-modal');
  const hint = root?.querySelector<HTMLParagraphElement>('[data-role="form-error"]');
  if (!doc || !root || !hint) return;
  const button = root.querySelector<HTMLButtonElement>('[data-action="confirm-reindex"]');
  if (button) {
    button.disabled = true;
    button.textContent = '请求中…';
  }
  try {
    const result = await reindexAdminDocument(doc.document_id);
    closeModal();
    showNotice({
      type: 'success',
      text: `索引重建完成：${result.status}，片段 ${result.indexed_count}/${result.chunk_count}。`,
    });
  } catch (error) {
    hint.hidden = false;
    hint.className = 'modal-hint modal-hint--error';
    hint.textContent = state.source === 'demo'
      ? `重建索引失败（${formatError(error)}）。演示模式不会伪造索引结果：chunk_count 与 indexed_count 必须来自真实索引服务。`
      : `重建索引失败：${formatError(error)}`;
    if (button) {
      button.disabled = false;
      button.textContent = '确认重建';
    }
  }
}

/* ============================ 启动 ============================ */

app.addEventListener('click', onClick);
app.addEventListener('change', onChange);
app.addEventListener('input', onInput);
app.addEventListener('submit', onSubmit);
document.addEventListener('keydown', onKeydown);

readDeepLink();
void bootstrap();
