# Alpha 学生端交互与 API 联调记录

负责人为洪添军。2026 年 11 月 17 日在 Windows 和 Edge 上验证。学生端使用统一 Vite 工程的联调页，通过现有 `/api` 开发代理访问本地 FastAPI。

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

页面加载时调用 `GET /api/v1/health`。问答提交使用 `POST /api/v1/ask`，JSON 仅包含 `query` 和 `conversation_id`。首轮传 `null`，成功后沿用返回的会话 ID。聊天记录保留在页面内，刷新页面开始新会话。

## 实测结果

| 场景 | 操作与数据源 | 实际结果与截图 |
| --- | --- | --- |
| 健康检查与正常回答 | 打开页面，输入「申请奖学金需要什么条件？」 | 健康检查显示已连接。Mock 后端返回 HTTP 200 和 `answered`，页面显示回答与空引用提示。[截图](screenshots/01-answered.png) |
| Agent 追问与补充 | 刷新后输入 `__mock_clarify__`，再发送「2026 学年。」 | 显示追问并保留第一轮。浏览器发出的第二个 POST 与后端响应沿用第一轮的会话 ID。[追问截图](screenshots/02-clarification.png) |
| 证据不足 | 输入 `__mock_insufficient__` | Mock 后端返回 `insufficient_evidence`，页面显示依据不足说明和警告。[截图](screenshots/03-insufficient-evidence.png) |
| 后端 422 | 通过浏览器测试拦截把发往现有后端的请求体改成空 `query`，再将实际响应交给页面 | 后端返回 `422 INVALID_REQUEST`，页面显示错误，保留输入并恢复发送按钮。正常页面会拦截空输入。[截图](screenshots/04-invalid-request.png) |
| 后端 503 | 将测试请求转发到在 8001 启动的默认入口 `backend.app.main:app` | 实际后端返回 `503 SERVICE_NOT_CONFIGURED`，页面显示服务未配置。[截图](screenshots/05-service-not-configured.png) |
| 后端停机 | 保持 Vite 运行，停止 8000 上的 FastAPI 后刷新并提交 | 健康检查显示未连接。Vite 代理返回 HTTP 500 后，页面提示服务不可用并保留问题。[截图](screenshots/06-backend-offline.png) |
| 请求断网 | 在浏览器中拦截并中断问答请求 | 页面提示连接失败，保留输入并恢复发送。[截图](screenshots/07-network-error.png) |
| 加载、引用和空响应 | 用浏览器拦截分别返回延迟且含引用的契约测试响应，以及空 JSON 对象 | 等待期间禁止重复提交。引用默认收起，可展开查看片段和原始来源，也可再次收起。空响应进入错误提示。[引用截图](screenshots/08-citation-expanded.png) |
| 用户反馈 | 在回答下点击「有帮助」 | 页面显示选择结果。反馈状态保存在当前页面。 |

构建验证使用 `cd frontend` 后执行 `npm run build`，包含 TypeScript 类型检查和两个页面入口的 Vite 构建。

当前 Mock Agent 可验证浏览器实际调用后端及三种业务状态，引用展开使用标注过的测试数据。正式学生端页面整合需与吴欣键联调，真实回答与引用验证依赖 Agent 和知识库接入。
