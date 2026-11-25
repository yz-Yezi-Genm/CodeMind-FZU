import '../shared/styles.css';
import './student.css';
import { ApiError, ask, fetchHealth } from '../shared/api';
import type { StudentAskResponse } from '../shared/api';
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
    historical: '历史资料参考，请以当前年度官方通知为准。',
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

function renderResult(query: string, response: StudentAskResponse): void {
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
  const isMockAnswer = response.status === 'answered' && response.warnings.some(item => item.code === 'MOCK_AGENT');
  const testFixtureNotice = hasTestFixtureCitation(response.citations)
    ? '<p class="student-test-fixture-notice">当前回答引用的是联调测试资料，不代表学校正式政策结论。</p>'
    : '';

  const turn = document.createElement('article');
  turn.className = 'student-turn';
  turn.innerHTML = `
    <p class="student-question"><span class="student-sr-only">你：</span>${escapeHtml(query)}</p>
    <div class="student-answer">
      <h2>${isMockAnswer ? '模拟回答' : labels[response.status]}</h2>
      ${isMockAnswer ? '' : renderAnswerMode(response.answer_mode)}
      ${content?.trim() ? `<p>${escapeHtml(content)}</p>` : ''}
      ${warnings ? `<ul class="student-warnings">${warnings}</ul>` : ''}
      ${testFixtureNotice}
      ${citations
        ? `<section class="student-sources" aria-label="引用来源"><h3>引用来源</h3>${citations}</section>`
        : (response.status === 'answered' ? '<p class="hint">暂无引用来源。</p>' : '')}
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

function describeAskError(error: unknown): string {
  if (!(error instanceof ApiError)) return '暂时无法处理问题，请稍后重试。';
  if (error.status === 0 || error.status === 200) return error.message;

  if (error.code === 'INVALID_REQUEST' || error.status === 400 || error.status === 422) {
    return '问题格式有误，请检查后重新发送。';
  }
  if (error.code === 'RATE_LIMITED' || error.status === 429) {
    return '请求过于频繁，请稍等一会儿再发送。';
  }
  if (error.code === 'MODEL_TIMEOUT' || error.status === 504) {
    return '回答等待超时，请稍后重试。';
  }
  switch (error.code) {
    case 'MODEL_UNAVAILABLE':
      return '问答模型暂时不可用，请稍后重试。';
    case 'KNOWLEDGE_BASE_UNAVAILABLE':
      return '资料服务暂时不可用，请稍后重试。';
    case 'SERVICE_NOT_CONFIGURED':
      return '问答服务还未就绪，请稍后重试。';
    default:
      return error.status >= 500
        ? '问答服务暂时遇到问题，请稍后重试。'
        : '暂时无法提交问题，请检查后重试。';
  }
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
  form.setAttribute('aria-busy', 'true');
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
    askStatus.textContent = describeAskError(error);
  } finally {
    send.disabled = false;
    newChat.disabled = false;
    input.readOnly = false;
    form.removeAttribute('aria-busy');
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
