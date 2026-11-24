import './design-motion';
import './demo-entry.css';
import { requireElement } from '../shared/dom';

const gate = requireElement<HTMLElement>('#demo-entry');
const workspace = requireElement<HTMLElement>('#demo-workspace');
const startup = requireElement<HTMLElement>('#student-startup');
const form = requireElement<HTMLFormElement>('#demo-form');
const account = requireElement<HTMLInputElement>('#demo-account');
const password = requireElement<HTMLInputElement>('#demo-password');
const showPassword = requireElement<HTMLButtonElement>('#show-password');
const submit = requireElement<HTMLButtonElement>('#demo-submit');
const submitLabel = requireElement<HTMLElement>('#demo-submit-label');
const feedback = requireElement<HTMLElement>('#demo-feedback');
const sessionKey = 'codemind-fzu:demo-entry';

function showLogin(): void {
  startup.hidden = true;
  gate.hidden = false;
}

async function enterWorkspace(): Promise<void> {
  submit.disabled = true;
  account.readOnly = password.readOnly = true;
  submitLabel.textContent = '正在进入…';

  try {
    await import('./main');
  } catch {
    submit.disabled = false;
    account.readOnly = password.readOnly = false;
    submitLabel.textContent = '登录';
    feedback.textContent = '工作台加载失败，请刷新页面后重试。';
    showLogin();
    return;
  }

  account.value = password.value = '';
  password.type = 'password';
  gate.hidden = true;
  startup.hidden = true;
  workspace.hidden = false;
  document.title = 'CodeMind-FZU · 学生端';
  requireElement<HTMLTextAreaElement>('#ask-input').focus();
  try {
    sessionStorage.setItem(sessionKey, '1');
  } catch {
    // Storage is optional, and the current page has already opened.
  }

  const url = new URL(location.href);
  if (url.searchParams.has('preview')) {
    url.searchParams.delete('preview');
    history.replaceState(history.state, '', url);
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (submit.disabled) return;

  if (!account.value.trim()) {
    showError(account, '请输入用户名。');
    return;
  }
  if (!password.value) {
    showError(password, '请输入密码。');
    return;
  }
  if (!/^[0-9０-９]+$/u.test(password.value)) {
    showError(password, '演示密码请使用数字。');
    return;
  }

  feedback.textContent = '';
  void enterWorkspace();
});

function showError(field: HTMLInputElement, message: string): void {
  field.setAttribute('aria-invalid', 'true');
  feedback.textContent = message;
  field.focus();
}

for (const field of [account, password]) {
  field.addEventListener('input', () => {
    field.removeAttribute('aria-invalid');
    feedback.textContent = '';
    syncProgress();
  });
}

function syncProgress(): void {
  form.closest('.demo-sign-in')?.classList.toggle('has-account', Boolean(account.value.trim()));
  form.closest('.demo-sign-in')?.classList.toggle('has-password', /^[0-9０-９]+$/u.test(password.value));
}

window.addEventListener('pageshow', syncProgress);

showPassword.addEventListener('click', () => {
  const reveal = password.type === 'password';
  password.type = reveal ? 'text' : 'password';
  showPassword.classList.toggle('is-visible', reveal);
  showPassword.setAttribute('aria-label', reveal ? '隐藏密码' : '显示密码');
});

submit.disabled = false;

function startStudentEntry(): void {
  try {
    if (!new URLSearchParams(location.search).has('preview') && sessionStorage.getItem(sessionKey) === '1') {
      void enterWorkspace();
      return;
    }
  } catch {
    // Visitors can still enter from the form when storage is blocked.
  }
  showLogin();
}

startStudentEntry();
