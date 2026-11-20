# Alpha 学生端交互与 API 联调记录

学生端页面与 API 联调由洪添军负责。2026 年 11 月 17 日在 Windows 和 Edge 上验证。学生端使用统一 Vite 工程，首页与对话界面参考 Figma 学生端原型，通过现有 `/api` 开发代理访问本地 FastAPI。

## 启动

在仓库根目录安装后端依赖，并启动 Mock Agent 入口。

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.dev:app --host 127.0.0.1 --port 8000
```

另开终端，从仓库根目录执行以下命令，再打开学生端 `http://127.0.0.1:5173/`。

```powershell
cd frontend
npm ci
npm run dev
```

页面加载时调用 `GET /api/v1/health`。四类主题入口填入可编辑的问题。问答提交使用 `POST /api/v1/ask`，JSON 仅包含 `query` 和 `conversation_id`。首轮传 `null`，成功后沿用返回的会话 ID。聊天记录保留在页面内，点击「新建对话」或刷新页面会重新开始会话。

## 实测结果

| 场景 | 操作与数据源 | 实际结果与截图 |
| --- | --- | --- |
| 首页与主题入口 | 打开学生端并点击「政策与事务办理」 | 首页显示四类主题，图标加载正常。点击后填入可编辑的奖学金问题。[首页截图](screenshots/00-student-home.png) |
| 健康检查与正常回答 | 提交主题入口填入的奖学金问题 | 健康检查显示已连接。Mock 后端返回 HTTP 200 和 `answered`，页面切换到对话并显示回答与空引用提示。[截图](screenshots/01-answered.png) |
| 新建对话 | 点击「新建对话」后提交推免问题 | 返回首页并清空当前对话。下一次请求携带 `conversation_id: null`。 |
| Agent 追问与补充 | 刷新后输入 `__mock_clarify__`，再发送「2026 学年。」 | 显示追问并保留第一轮。浏览器发出的第二个 POST 与后端响应沿用第一轮的会话 ID。[追问截图](screenshots/02-clarification.png) |
| 证据不足 | 输入 `__mock_insufficient__` | Mock 后端返回 `insufficient_evidence`，页面显示依据不足说明和警告。[截图](screenshots/03-insufficient-evidence.png) |
| 后端 422 | 通过浏览器测试拦截把发往现有后端的请求体改成空 `query`，再将实际响应交给页面 | 后端返回 `422 INVALID_REQUEST`，页面显示错误，保留输入并恢复发送按钮。正常页面会拦截空输入。[截图](screenshots/04-invalid-request.png) |
| 后端 503 | 将测试请求转发到在 8001 启动的默认入口 `backend.app.main:app` | 实际后端返回 `503 SERVICE_NOT_CONFIGURED`，页面显示服务未配置。[截图](screenshots/05-service-not-configured.png) |
| 后端停机与恢复 | 保持 Vite 运行，停止 8000 上的 FastAPI 后刷新并提交。重启后端，点击健康检查的「重试」并重新发送 | 停机时显示未连接，Vite 代理返回 HTTP 500 后保留问题。重启后健康检查恢复，重新发送返回 HTTP 200。[停机截图](screenshots/06-backend-offline.png) |
| 请求断网 | 在浏览器中拦截并中断问答请求 | 页面提示连接失败，保留输入并恢复发送。[截图](screenshots/07-network-error.png) |
| 加载、引用和空响应 | 用浏览器拦截分别返回延迟且含引用的契约测试响应，以及空 JSON 对象 | 等待期间禁止重复提交。引用默认收起，可展开查看片段和原始来源，也可再次收起。空响应进入错误提示。[引用截图](screenshots/08-citation-expanded.png) |
| 用户反馈 | 在回答下点击「有帮助」 | 页面显示选择结果。反馈状态保存在当前页面。 |
| 手机宽度与键盘提交 | 在 390 像素宽度下选择竞赛主题，按 Shift + Enter，再按 Enter | 首页无横向溢出，组合键换行，Enter 发送问答且正常显示响应。[截图](screenshots/09-mobile.png) |

构建验证使用 `cd frontend` 后执行 `npm run build`，包含 TypeScript 类型检查和两个页面入口的 Vite 构建。

当前 Mock Agent 可验证浏览器实际调用后端及三种业务状态。引用标题、原文片段、发布单位、日期和定位均来自接口字段。展开交互通过契约测试数据验证，真实回答及真实引用的验收依赖 Agent 和知识库接入。

## PR #27 视觉验收补充

学生端视觉优化完成后，使用本地 Mock Agent 服务重新启动 Vite 页面，并在 1440px 桌面视口与 390px 移动视口下核验首页布局、主题入口及输入区域：

- [桌面端截图（1440px）](screenshots/10-ui-polish-desktop.png)
- [移动端截图（390px）](screenshots/11-ui-polish-mobile-390.png)
- [构建成功输出截图](screenshots/12-build-success.png)

## 2026-11-20 联调预验收

洪添军在 Windows 和 Edge 上完成本轮学生端 API 联调和浏览器回归。学生端以 `main` 的 `f5fcabc` 为基线，测试时使用 `7-htj` 上相同的文件内容。后端在临时目录组合 [PR #32](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/32) 的 Agent 工作流（`730f88a`）和 [PR #34](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/34) 的 FastAPI 运行组装与会话存储（`548a27d`）。

浏览器通过 Vite 代理调用本地 FastAPI 的 `GET /api/v1/health` 和 `POST /api/v1/ask`。问答请求只传 `query` 和 `conversation_id`。运行组装使用 LocalBM25Retriever、AgentWorkflow、Qwen 适配器及内存会话；政策输入使用 #34 的合成测试资料，Qwen HTTP 响应由本地替身提供。手机端长文本压力场景使用浏览器拦截注入的契约响应。

| 场景 | 输入或操作 | 实测结果 |
| --- | --- | --- |
| 空白输入 | 输入空格后点击发送 | 显示输入提示，发出 0 次问答请求。 |
| 主动追问 | 新对话输入「奖学金有哪些类别？」 | 首轮请求的 `conversation_id` 为 `null`，后端返回 `needs_clarification`。测试环境采用工作流默认回调。[桌面截图](screenshots/pr32-pr34/01-desktop-clarification.png) |
| 多轮续接与连续提交 | 在同一会话补充「2026年。」，在模型替身延迟期间再次点发送并按 Enter | 输入、发送和新建对话处于等待状态。本轮只发出 1 次请求，服务端使用此前的奖学金主题返回 `answered`，页面保留两轮消息。 |
| 引用与来源 | 展开回答中的引用，点击「查看原始来源」，再收起 | 标题和摘录与 API 响应一致，展开与收起正常。浏览器在新标签打开合成来源 URL，目标页面由测试拦截提供。[桌面截图](screenshots/pr32-pr34/02-desktop-answered-citation.png) |
| 会话隔离 | 新建对话后单独输入「2026年。」 | 请求传 `null`，返回新 ID 和 `needs_clarification`，前一会话的奖学金主题未被沿用。 |
| 证据不足与引用拒绝 | 询问「2099年推免条件是什么？」；另开会话让替身改写奖学金证据 | 两轮都返回 `insufficient_evidence` 且无引用。改写场景收到 `UNSUPPORTED_GENERATION` 警告。[桌面截图](screenshots/pr32-pr34/03-desktop-insufficient.png) |
| 模型异常 | 让 Qwen 替身分别触发超时和不可用 | 实际 FastAPI 返回 `504 MODEL_TIMEOUT` 和 `503 MODEL_UNAVAILABLE`。页面显示错误并恢复发送，超时后保留原问题。[超时截图](screenshots/pr32-pr34/04-desktop-model-timeout.png) |
| 断网与重试 | 中断一次浏览器问答请求，再恢复连接并重发原问题 | 失败后保留输入，恢复后重试成功，只新增一轮问答。 |
| 手机端长文本 | 在 390px 视口查看首页，再发送长问题并展开三条测试引用中的一条 | 首页、长回答和引用卡片均无横向溢出，引用和发送控件可操作。[手机首页](screenshots/pr32-pr34/05-mobile-390-home.png) · [长回答截图](screenshots/pr32-pr34/06-mobile-390-long-answer.png) |

### 构建与后端检查

在仓库 `frontend/` 执行 `npm run build`，类型检查和两个 Vite 页面入口均构建通过。在临时组合目录执行下列现有测试，发现 77 项，其中 75 项通过、2 项跳过。跳过项涉及正式业务规则模块和真实 Qwen 联网。

```powershell
python -X utf8 -m unittest tests.test_agent_workflow tests.test_agent_workflow_api tests.test_agent_workflow_qwen tests.test_backend_runtime -q
```

### 缺陷与正式验收待办

- 已测场景未发现需要修复的学生端交互问题。测试中的「先追问学年」来自默认回调，正式奖学金场景仍需由 Agent 与业务规则负责人确认追问顺序。
- 待可用的正式后端接入审核通过的资料包、正式业务规则和真实 Qwen 后，补测竞赛认定、奖学金和推免三个场景。验收时补上真实来源跳转、多轮上下文和三种状态截图，确认模型错误仍走现有 HTTP 错误契约。
## PR #39 回答依据与引用回归

使用浏览器 DevTools 请求拦截构造契约 `AskResponse`，仅验证前端渲染；以下截图不是正式政策或真实 Qwen 联调记录。

| 拦截响应 | 核验结果 | 截图 |
| --- | --- | --- |
| `answer_mode: current_policy`，Citation 来源为 `https://example.invalid/test-policy` | 展示「当前政策依据」和测试资料提示；保留引用标题与原文，不生成「查看原始来源」外链。 | [测试夹具来源](screenshots/13-contract-test-fixture.png) |
| `answer_mode: current_policy`，Citation 来源为学校官网格式 URL | 展示「当前政策依据」及引用元数据；无测试资料提示；展开引用后显示「查看原始来源」入口。 | [正常来源](screenshots/14-contract-official-source.png) |

两组响应均使用既有 `AskResponse` / `Citation` 字段。真实运行时的三种业务状态、多轮会话及正式资料引用，仍以已配置 Qwen 和审核 `enabled` 资料包的实际联调结果为准。
