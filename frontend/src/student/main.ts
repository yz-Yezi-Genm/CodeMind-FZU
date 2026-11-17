import '../shared/styles.css';
import { ApiError, ask, fetchHealth } from '../shared/api';
import { escapeHtml, requireElement } from '../shared/dom';
import type { AskResponse, Citation } from '../shared/types';

const app = requireElement<HTMLDivElement>('#app');

app.innerHTML = `
  <main class="page">
    <header class="page-header">
      <h1>CodeMind-FZU 学生端 <span class="badge">Alpha 工程骨架</span></h1>
      <a class="entry-link" href="/admin/">进入后台管理端 →</a>
    </header>

    <div class="status-bar" role="status">
      <span id="health-dot" class="status-dot" aria-hidden="true"></span>
      <span id="health-text">正在检查后端连接…</span>
    </div>

    <section class="card">
      <h2>问答接口联调</h2>
      <p class="hint">
        使用 Mock Agent 时，回答仅用于验证前后端链路。
      </p>
      <form id="ask-form" class="ask-form">
        <input id="ask-input" type="text" maxlength="4000" aria-label="输入问题"
          placeholder="例如：大二申请院级奖学金需要什么条件？" autocomplete="off" />
        <button id="ask-button" type="submit">发送</button>
      </form>
      <p id="ask-status" class="hint" role="status">输入问题后开始对话。</p>
      <div id="ask-result" class="result ask-result" role="log" aria-label="问答记录"></div>
    </section>
  </main>
`;

const dot = requireElement<HTMLSpanElement>('#health-dot');
const healthText = requireElement<HTMLSpanElement>('#health-text');
const form = requireElement<HTMLFormElement>('#ask-form');
const input = requireElement<HTMLInputElement>('#ask-input');
const button = requireElement<HTMLButtonElement>('#ask-button');
const result = requireElement<HTMLDivElement>('#ask-result');
const askStatus = requireElement<HTMLParagraphElement>('#ask-status');
let conversationId: string | null = null;

async function refreshHealth(): Promise<void> {
  dot.classList.remove('ok', 'error');
  try {
    const health = await fetchHealth();
    dot.classList.add('ok');
    healthText.textContent = `后端已连接：${health.service} v${health.version}`;
  } catch (error) {
    dot.classList.add('error');
    healthText.textContent = `后端未连接：${error instanceof Error ? error.message : String(error)}`;
  }
}

function renderCitation(citation: Citation): string {
  let sourceLink = '';
  try {
    const url = new URL(citation.source_url);
    if (url.protocol === 'https:' || url.protocol === 'http:') {
      sourceLink = `<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">查看原始来源</a>`;
    }
  } catch {
    // Keep the citation contents visible when the URL is unavailable.
  }
  return `<details><summary>${escapeHtml(citation.title)}</summary>
    <p>${escapeHtml(citation.excerpt)}</p>${sourceLink}</details>`;
}

function renderResult(query: string, response: AskResponse): void {
  const labels: Record<AskResponse['status'], string> = {
    answered: '已回答',
    needs_clarification: '需要补充信息',
    insufficient_evidence: '证据不足',
  };
  const content = response.status === 'needs_clarification'
    ? response.clarifying_question
    : response.answer;

  const warnings = response.warnings
    .map((warning) => `<li>${escapeHtml(warning.message)}</li>`)
    .join('');
  const citations = response.status === 'answered'
    ? (response.citations.map(renderCitation).join('') || '<p class="hint">暂无引用来源。</p>')
    : '';

  const turn = document.createElement('article');
  turn.innerHTML = `<hr>
    <p><strong>你</strong> ${escapeHtml(query)}</p>
    <p><strong>${labels[response.status]}</strong></p>
    ${content ? `<p>${escapeHtml(content)}</p>` : ''}
    ${warnings ? `<ul class="placeholder-list">${warnings}</ul>` : ''}
    ${citations}
    ${response.status === 'answered' ? `<div aria-label="回答反馈">
      <button type="button" aria-pressed="false">有帮助</button>
      <button type="button" aria-pressed="false">需改进</button>
      <span class="hint" role="status"></span>
    </div>` : ''}`;
  const feedbackButtons = turn.querySelectorAll('button');
  for (const selected of feedbackButtons) {
    selected.addEventListener('click', () => {
      for (const candidate of feedbackButtons) {
        candidate.setAttribute('aria-pressed', String(candidate === selected));
      }
      turn.querySelector<HTMLElement>('[role="status"]')!.textContent =
        `已在当前页面标记「${selected.textContent}」。`;
    });
  }
  result.append(turn);
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  void handleAsk();
});

async function handleAsk(): Promise<void> {
  if (button.disabled) return;
  const query = input.value.trim();
  if (!query) {
    askStatus.textContent = '请输入问题后再发送。';
    return;
  }

  button.disabled = true;
  input.readOnly = true;
  askStatus.textContent = '正在请求回答…';

  try {
    const response = await ask({ query, conversation_id: conversationId });
    renderResult(query, response);
    conversationId = response.conversation_id;
    input.value = '';
    askStatus.textContent = response.status === 'needs_clarification' ? '请补充信息后发送。' : '';
  } catch (error) {
    const detail = error instanceof ApiError ? error.message : '处理响应时出错，请稍后重试。';
    const code = error instanceof ApiError && error.status ? `（HTTP ${error.status}，${error.code}）` : '';
    askStatus.textContent = `请求失败${code}：${detail}`;
  } finally {
    button.disabled = false;
    input.readOnly = false;
    input.focus();
  }
}

void refreshHealth();
