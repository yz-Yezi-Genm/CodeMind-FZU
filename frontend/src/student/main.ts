import '../shared/styles.css';
import { ApiError, ask, fetchHealth } from '../shared/api';
import { escapeHtml, requireElement } from '../shared/dom';
import type { AskResponse } from '../shared/types';

const app = requireElement<HTMLDivElement>('#app');

app.innerHTML = `
  <main class="page">
    <header class="page-header">
      <h1>CodeMind-FZU 学生端 <span class="badge">Alpha 工程骨架</span></h1>
      <a class="entry-link" href="/admin/index.html">进入后台管理端 →</a>
    </header>

    <div class="status-bar">
      <span id="health-dot" class="status-dot" aria-hidden="true"></span>
      <span id="health-text">正在检查后端连接…</span>
    </div>

    <section class="card">
      <h2>问答接口联调</h2>
      <p class="hint">
        当前连接后端 Mock Agent，仅用于验证前后端链路，不代表真实政策回答。
      </p>
      <form id="ask-form" class="ask-form">
        <input id="ask-input" type="text" maxlength="4000"
          placeholder="例如：大二申请院级奖学金需要什么条件？" autocomplete="off" />
        <button id="ask-button" type="submit">发送</button>
      </form>
      <div id="ask-result" class="result"></div>
    </section>
  </main>
`;

const dot = requireElement<HTMLSpanElement>('#health-dot');
const healthText = requireElement<HTMLSpanElement>('#health-text');
const form = requireElement<HTMLFormElement>('#ask-form');
const input = requireElement<HTMLInputElement>('#ask-input');
const button = requireElement<HTMLButtonElement>('#ask-button');
const result = requireElement<HTMLDivElement>('#ask-result');

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

function renderResult(response: AskResponse): void {
  const statusLabel =
    response.status === 'answered'
      ? '已回答'
      : response.status === 'needs_clarification'
        ? '需要补充信息'
        : '证据不足';

  const warnings = response.warnings
    .map((warning) => `<li>${escapeHtml(warning.code)}：${escapeHtml(warning.message)}</li>`)
    .join('');

  result.innerHTML = `
    <p>状态：<strong>${escapeHtml(statusLabel)}</strong>
      <span class="badge ${response.status === 'answered' ? '' : 'warn'}">${escapeHtml(response.status)}</span>
    </p>
    ${response.answer ? `<p>${escapeHtml(response.answer)}</p>` : ''}
    ${response.clarifying_question ? `<p>追问：${escapeHtml(response.clarifying_question)}</p>` : ''}
    ${warnings ? `<ul class="placeholder-list">${warnings}</ul>` : ''}
    <details>
      <summary class="hint">查看原始响应</summary>
      <pre>${escapeHtml(JSON.stringify(response, null, 2))}</pre>
    </details>
  `;
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  void handleAsk();
});

async function handleAsk(): Promise<void> {
  const query = input.value.trim();
  if (!query) {
    result.innerHTML = '<p class="hint">请输入问题后再发送。</p>';
    return;
  }

  button.disabled = true;
  result.innerHTML = '<p class="hint">请求中…</p>';

  try {
    renderResult(await ask({ query }));
  } catch (error) {
    if (error instanceof ApiError) {
      result.innerHTML = `<p class="hint">请求失败（HTTP ${error.status}，${escapeHtml(error.code)}）：${escapeHtml(error.message)}</p>`;
    } else {
      result.innerHTML = `<p class="hint">请求失败：${escapeHtml(String(error))}</p>`;
    }
  } finally {
    button.disabled = false;
  }
}

void refreshHealth();
