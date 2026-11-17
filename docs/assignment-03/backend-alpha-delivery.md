# Alpha 后端 API 与模型适配交付记录

**负责人**：赵紫龙  
**日期**：2026-11-17  
**分支**：`feat/zhaozilong-alpha-backend`  
**接口基线**：[Alpha 接口规范 V1.0](interface-contract-v1.md)

## 1. 本周完成范围

| 要求 | 实现 |
| --- | --- |
| 前后端 CORS | 使用显式来源列表，禁止 `*`，允许 `PATCH`，支持 `CORS_ALLOW_ORIGINS` 覆盖 |
| 现有 API 稳定 | 保持 `/api/v1/health` 和 `/api/v1/ask`，复用公共 Pydantic 模型 |
| 接入 AgentService | 保留 `create_app(agent_service=...)` 注入；调用 `AgentService.run()` 并包装为 `AskResponse` |
| 保留 Mock 入口 | `backend.app.dev:app` 继续注入 `MockAgentService` |
| 异常与环境配置 | 统一错误 envelope、脱敏内部异常、请求 ID 响应头、环境配置校验 |
| Qwen 适配 | 新增 `QwenLLMClient.generate()`，实现 `LLMClient` 协议 |

## 2. HTTP 行为

### 默认入口

```bash
python -m uvicorn backend.app.main:app --port 8000
```

- `GET /api/v1/health` 返回服务可响应状态。
- 未注入 Agent 时，`POST /api/v1/ask` 返回 `503 SERVICE_NOT_CONFIGURED`。
- 不伪造政策回答。

### Mock 入口

```bash
python -m uvicorn backend.app.dev:app --port 8000
```

- 保持既有 MockAgentService 演示能力。
- 支持正常回答、追问和证据不足三种统一状态。

### 统一错误

所有已实现接口使用以下 envelope：

```json
{
  "request_id": "UUID",
  "error": {
    "code": "ERROR_CODE",
    "message": "可安全展示的说明",
    "retryable": false
  }
}
```

内部协作者类型错误只写入本地日志，不向浏览器返回类名、堆栈或详细异常文本。

## 3. CORS 配置

默认来源限定为常见本地开发端口：

- Vite：`localhost:5173`、`127.0.0.1:5173`
- Node 开发服务：`localhost:3000`、`127.0.0.1:3000`
- Live Server：`localhost:5500`、`127.0.0.1:5500`

前端最终端口由吴欣键、洪添军确认后，以 `CORS_ALLOW_ORIGINS` 覆盖。配置禁止 `*`，启动时校验 URL 来源格式。

## 4. Qwen 适配

实现位置：`backend/services/qwen_client.py`

- 使用 OpenAI-compatible `chat/completions` 请求格式；
- 复用公共 `LLMGenerateRequest` 与 `LLMResult`；
- API Key 仅从 `QWEN_API_KEY` 读取，且从对象 repr 中隐藏；
- 网络异常与 HTTP 状态共用一个重试计数，最多执行 `QWEN_MAX_RETRIES + 1` 次请求；
- 对 401/403、408、429、5xx 和非法响应进行安全错误映射；
- 本次未执行真实付费模型调用，使用 `httpx.MockTransport` 验证请求与响应契约。

## 5. 测试记录

执行命令：

```bash
.venv\\Scripts\\python.exe -m unittest discover -s tests -v
```

最近一次结果：

```text
Ran 29 tests in 0.957s
OK
```

覆盖内容包括：

1. 公共模型与状态约束；
2. 默认入口未配置 Agent 的 503；
3. Mock 正常回答、追问和证据不足；
4. AgentRequest/AgentResult 包装及 ID 传递；
5. CORS 允许、拒绝和通配符配置拒绝；
6. Agent 异常与内部类型错误脱敏；
7. Qwen 成功、超时、429、5xx、重试和缺失密钥。

另使用真实 Uvicorn 进程启动 `backend.app.dev:app`，在
`http://127.0.0.1:8765` 完成冒烟验证：

- `GET /api/v1/health` 返回 `200`，`status=ok`；
- `POST /api/v1/ask` 返回 `200`、`status=answered` 和 Mock 演示回答；
- 来自 `http://localhost:5173` 的 CORS 预检支持
  `GET, POST, PATCH, OPTIONS`；
- 响应包含 `X-Request-ID`。

依赖验证：新建临时虚拟环境，仅安装 `backend/requirements.txt`；确认
`httpx 0.28.1`、`fastapi 0.163.1` 可导入，并成功启动
`backend.app.dev:app`、访问 `/api/v1/health`。

## 6. 未改变项

- 未修改 `backend/contracts/models.py` 和 `backend/contracts/protocols.py`；
- 未改变 `/api/v1` 路径、`query` / `conversation_id` 字段或三种状态值；
- 未接入数据库、检索器、真实 Agent 或管理端业务；
- 未提交 API Key 或真实 `.env`。
