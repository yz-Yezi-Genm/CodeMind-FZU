import '../shared/styles.css';
import './student.css';
import { ApiError, ask, fetchHealth } from '../shared/api';
import { escapeHtml, requireElement } from '../shared/dom';
import type { AskResponse, Citation } from '../shared/types';

const dot = requireElement<HTMLSpanElement>('#health-dot');
const healthText = requireElement<HTMLSpanElement>('#health-text');
const healthRetry = requireElement<HTMLButtonElement>('#health-retry');
const form = requireElement<HTMLFormElement>('#ask-form');
const input = requireElement<HTMLTextAreaElement>('#ask-input');
const send = requireElement<HTMLButtonElement>('#ask-button');
const newChat = requireElement<HTMLButtonElement>('#new-chat');
const title = requireElement<HTMLSpanElement>('#conversation-title');
const welcome = requireElement<HTMLElement>('#student-welcome');
const result = requireElement<HTMLElement>('#ask-result');
const askStatus = requireElement<HTMLParagraphElement>('#ask-status');

let conversationId: string | null = null;

async function refreshHealth(): Promise<void> {
  dot.classList.remove('ok', 'error');
  healthText.textContent = '正在检查后端连接…';
  healthRetry.hidden = true;
  try {
    await fetchHealth();
    dot.classList.add('ok');
    healthText.textContent = '后端已连接';
  } catch {
    dot.classList.add('error');
    healthText.textContent = '后端未连接';
    healthRetry.hidden = false;
  }
}

function renderCitation(citation: Citation): string {
  let sourceLink = '';
  if (!isTestFixtureCitation(citation)) {
    try {
      const url = new URL(citation.source_url);
      if (url.protocol === 'https:' || url.protocol === 'http:') {
        sourceLink = `<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">查看原始来源</a>`;
      }
    } catch {
      // The title and excerpt remain available if the source URL is invalid.
    }
  }

  const metadata = [
    citation.publisher,
    citation.published_on && `发布于 ${citation.published_on}`,
    citation.effective_on && `生效于 ${citation.effective_on}`,
    citation.locator,
    citation.original_locator,
  ].filter(Boolean).join(' · ');

  return `<details class="student-citation"><summary>${escapeHtml(citation.title)}</summary>
    ${metadata ? `<p class="hint">${escapeHtml(metadata)}</p>` : ''}
    <p>${escapeHtml(citation.excerpt)}</p>${sourceLink}</details>`;
}

function renderAnswerMode(mode: AskResponse['answer_mode']): string {
  if (!mode) return '';
  const labels: Record<NonNullable<AskResponse['answer_mode']>, string> = {
    current_policy: '当前政策依据',
    historical: '历史资料参考',
    procedure_reference: '办理流程参考',
    insufficient_data: '证据不足',
  };
  return `<p class="student-answer-mode">回答依据：${escapeHtml(labels[mode])}</p>`;
}

function isTestFixtureCitation(citation: Citation): boolean {
  try {
    return new URL(citation.source_url).hostname === 'example.invalid';
  } catch {
    return false;
  }
}

function hasTestFixtureCitation(citations: Citation[]): boolean {
  return citations.some(isTestFixtureCitation);
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
    .map(({ message }) => `<li>${escapeHtml(message)}</li>`)
    .join('');
  const citations = response.citations.map(renderCitation).join('');
  const answer = content || '目前没有足够的依据提供可靠回答。';
  const testFixtureNotice = hasTestFixtureCitation(response.citations)
    ? '<p class="student-test-fixture-notice">当前回答引用的是联调测试资料，不代表学校正式政策结论。</p>'
    : '';

  const turn = document.createElement('article');
  turn.className = 'student-turn';
  turn.innerHTML = `
    <p class="student-question"><span class="student-sr-only">你：</span>${escapeHtml(query)}</p>
    <div class="student-answer">
      <h2>${labels[response.status]}</h2>
      ${renderAnswerMode(response.answer_mode)}
      <p>${escapeHtml(answer)}</p>
      ${warnings ? `<ul class="student-warnings">${warnings}</ul>` : ''}
      ${testFixtureNotice}
      ${citations || (response.status === 'answered' ? '<p class="hint">暂无引用来源。</p>' : '')}
      ${response.status === 'answered' ? `<div class="student-feedback" role="group" aria-label="回答反馈">
        <button type="button" aria-pressed="false">有帮助</button>
        <button type="button" aria-pressed="false">需改进</button>
        <span class="hint" role="status"></span>
      </div>` : ''}
    </div>`;
  const feedbackStatus = turn.querySelector<HTMLElement>('[role="status"]');
  if (feedbackStatus) {
    const options = turn.querySelectorAll('button');
    for (const selected of options) {
      selected.addEventListener('click', () => {
        for (const button of options) {
          button.setAttribute('aria-pressed', String(button === selected));
        }
        feedbackStatus.textContent = `已在当前页面标记「${selected.textContent}」。`;
      });
    }
  }
  result.append(turn);
}

async function handleAsk(): Promise<void> {
  if (send.disabled) return;
  const query = input.value.trim();
  if (!query) {
    askStatus.textContent = '请输入问题后再发送。';
    input.focus();
    return;
  }

  send.disabled = true;
  newChat.disabled = true;
  input.readOnly = true;
  askStatus.textContent = '正在请求回答…';

  try {
    const response = await ask({ query, conversation_id: conversationId });
    renderResult(query, response);
    if (conversationId === null) title.textContent = query;
    conversationId = response.conversation_id;
    welcome.hidden = true;
    input.value = '';
    input.placeholder = '继续提问，或补充当前问题的信息';
    askStatus.textContent = response.status === 'needs_clarification' ? '请补充信息后发送。' : '';
  } catch (error) {
    const detail = error instanceof ApiError ? error.message : '处理响应时出错，请稍后重试。';
    const code = error instanceof ApiError && error.status ? `（HTTP ${error.status}，${error.code}）` : '';
    askStatus.textContent = `请求失败${code}：${detail}`;
  } finally {
    send.disabled = false;
    newChat.disabled = false;
    input.readOnly = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  void handleAsk();
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

for (const topic of document.querySelectorAll<HTMLButtonElement>('#student-topics button[data-query]')) {
  topic.addEventListener('click', () => {
    if (send.disabled) return;
    input.value = topic.dataset.query ?? '';
    input.focus();
  });
}

const initialPlaceholder = input.placeholder;
newChat.addEventListener('click', () => {
  conversationId = null;
  result.replaceChildren();
  title.textContent = '首页 / 工作台';
  welcome.hidden = false;
  input.value = '';
  input.placeholder = initialPlaceholder;
  askStatus.textContent = '';
  input.focus();
});

healthRetry.addEventListener('click', () => void refreshHealth());
void refreshHealth();
