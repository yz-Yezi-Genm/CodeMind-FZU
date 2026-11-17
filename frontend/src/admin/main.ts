import '../shared/styles.css';
import { fetchHealth } from '../shared/api';
import { requireElement } from '../shared/dom';

const app = requireElement<HTMLDivElement>('#app');

app.innerHTML = `
  <main class="page">
    <header class="page-header">
      <h1>CodeMind-FZU 后台管理端 <span class="badge">Alpha 工程骨架</span></h1>
      <a class="entry-link" href="/index.html">← 返回学生端</a>
    </header>

    <div class="status-bar">
      <span id="health-dot" class="status-dot" aria-hidden="true"></span>
      <span id="health-text">正在检查后端连接…</span>
    </div>

    <section class="card">
      <h2>工程骨架说明</h2>
      <p class="hint">
        本页仅用于验证后台管理端的工程入口与后端连通性，具体业务页面由林彦翔等同学后续开发。
      </p>
      <ul class="placeholder-list">
        <li>资料审核与发布</li>
        <li>知识库资料管理</li>
        <li>用户与权限管理</li>
        <li>运行记录与统计看板</li>
      </ul>
    </section>
  </main>
`;

const dot = requireElement<HTMLSpanElement>('#health-dot');
const healthText = requireElement<HTMLSpanElement>('#health-text');

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

void refreshHealth();
