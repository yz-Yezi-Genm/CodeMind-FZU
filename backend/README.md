# Backend API 与模型适配

本目录提供 CodeMind-FZU Alpha 阶段的 FastAPI HTTP 入口、公共 Pydantic v2 数据模型、Python Protocol 接口、Mock Agent 演示入口和 Qwen 模型适配器。数据库、向量检索、真实 Agent 工作流及管理端业务仍由对应模块提供。

## 环境与启动

从仓库根目录执行：

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```

访问：
- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- OpenAPI 页面：`http://127.0.0.1:8000/docs`
- 问答入口：`POST http://127.0.0.1:8000/api/v1/ask`

`backend.app.main:app` 是默认入口，未注入真实 Agent 时，问答接口返回统一格式的 `503 SERVICE_NOT_CONFIGURED`，不会伪造回答。

本地 Mock 演示使用独立入口，不改变默认入口：

```bash
python -m uvicorn backend.app.dev:app --reload --port 8000
```

默认 API 为 `/api/v1`：

- `GET /api/v1/health`
- `POST /api/v1/ask`
- 请求字段严格使用 `query` 和可选的 `conversation_id`
- `answered`、`needs_clarification`、`insufficient_evidence` 三种状态由公共契约统一约束

默认入口和 Mock 入口共用同一套路由、校验、错误 envelope、CORS 与 Agent 适配逻辑。

## CORS

CORS 使用显式来源列表，不允许 `*`。内置本地开发默认值覆盖：

- `http://localhost:5173`、`http://127.0.0.1:5173`
- `http://localhost:3000`、`http://127.0.0.1:3000`
- `http://localhost:5500`、`http://127.0.0.1:5500`

前端实际端口确定后，通过环境变量覆盖，不需要修改代码：

```bash
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

来源格式非法或配置为 `*` 时，应用会在启动阶段拒绝配置。
允许的方法为 `GET`、`POST`、`PATCH`、`OPTIONS`，其中 `PATCH` 预留给后续后台元数据修改接口。

## 环境变量与 Qwen

复制模板并仅在本地填写密钥：

```bash
cp backend/.env.example backend/.env
python -m uvicorn backend.app.dev:app --env-file backend/.env --port 8000
```

可用变量：

- `CORS_ALLOW_ORIGINS`
- `QWEN_API_KEY`：仅从本地环境读取，禁止提交
- `QWEN_BASE_URL`：默认 OpenAI-compatible DashScope 地址
- `QWEN_MODEL`：默认 `qwen-plus`
- `QWEN_TIMEOUT_SECONDS`
- `QWEN_MAX_RETRIES`：0–3

`backend.services.qwen_client.QwenLLMClient` 实现公共 `LLMClient.generate()` 协议，不修改公共 `LLMGenerateRequest` / `LLMResult`。适配器处理超时、有限重试、限流和上游异常，并将错误转换为可安全返回的服务错误。

`httpx` 已包含在正式依赖 `backend/requirements.txt` 中，因为
`backend.services` 在导入时会加载 Qwen 适配器；只安装运行依赖即可启动 API。

## 测试

```bash
.venv\\Scripts\\python.exe -m unittest discover -s tests -v
```

测试包含：

- 契约模型校验；
- 默认入口 503 防护与 Mock 演示入口；
- AgentRequest/AgentResult 包装；
- `conversation_id` 和 `request_id` 传递；
- CORS 允许/拒绝与非法通配符配置；
- Agent 服务异常和错误返回脱敏；
- Agent 抛出普通 `RuntimeError` 时仍经过 CORS/request ID 中间件；
- Qwen 成功、超时、限流、重试、不可用及缺失密钥。

运行依赖还使用以下方式做了干净环境验证：新建临时虚拟环境，仅安装
`backend/requirements.txt`，确认 `httpx` 可导入并以 Uvicorn 启动健康检查。

## 公共契约

- `contracts/models.py`：请求、响应、引用、检索片段、资料入库包、索引结果及模型调用数据结构。
- `contracts/protocols.py`：Agent、Retriever、DocumentParser、KnowledgeIndexer、LLMClient 和 DocumentAdminService 的模块边界。
- 完整说明见 [Alpha 接口规范 V1.0](../docs/assignment-03/interface-contract-v1.md)。

各成员应直接复用公共模型，不要在自己的模块中复制定义同名 DTO。公共字段、状态值或函数签名需要修改时，先向罗宇泽提出并等待统一更新。

## 当前边界

- Agent 工作流和对话历史持久化；
- Qwen 真实网络调用需要本地配置 API Key，本次使用 MockTransport 完成适配器测试；
- 文档解析、文件存储和资料入库；
- PostgreSQL/SQLAlchemy 在线连接与迁移；
- Chroma、BM25、RRF 实际检索；
- 管理端业务 API 和认证授权。

数据库设计中的资料默认 `retrieval_status=blocked`。解析、入库或建立索引均不会自动开放正式问答检索。
