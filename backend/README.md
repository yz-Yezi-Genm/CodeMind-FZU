# Backend API 与模型适配

本目录提供 CodeMind-FZU Alpha 阶段的 FastAPI HTTP 入口、公共 Pydantic v2 数据模型、Python Protocol 接口、Mock Agent 演示入口和 Qwen 模型适配器。已实现可注入的 `AgentWorkflow`、Markdown/TXT 文档解析和本地 BM25 检索。

## 环境与启动

从仓库根目录执行：

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r backend/requirements.txt

# 默认入口（未注入真实 Agent，/api/v1/ask 返回 503，属预期）
python -m uvicorn backend.app.main:app --reload --port 8000

# Mock Agent 演示入口（用于前后端联调）
python -m uvicorn backend.app.dev:app --reload --port 8000
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

完整的环境安装、启动、测试与常见问题见 [Alpha 阶段运行说明](../docs/assignment-03/alpha/run-guide.md)。

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

- 对话历史持久化；
- Qwen 真实网络调用需要本地配置 API Key，本次使用 MockTransport 完成适配器测试；
- 文件存储服务和完整资料入库流程；
- PostgreSQL/SQLAlchemy 在线连接与迁移；
- Chroma 和 RRF 混合检索；
- 管理端业务 API 和认证授权。

数据库设计中的资料默认 `retrieval_status=blocked`。解析、入库或建立索引均不会自动开放正式问答检索。

## 文档解析（Alpha）

`backend.document_processing.TextDocumentParser` 实现现有 `DocumentParser` 协议，返回公共 `DocumentPackage`。支持 Markdown/TXT、标题层级、片段编号、行号/字符定位和哈希；输出全部保持 `retrieval_status=blocked`。文件业务角色可用构造参数`file_role`或CLI的`--file-role`显式指定；已知业务角色时应传入，未传时保留原默认值。PDF及其他格式仅登记待处理，不伪造正文。

```bash
python -m scripts.parse_alpha_documents
python -m scripts.check_document_processing
```

三个场景样例位于 `knowledge_base/processed/alpha/`，共 23 个片段，均已通过内存索引联调。正文和附件仍待政策核验，问答检索保持关闭。使用方法见 [文档处理说明](../docs/assignment-03/alpha/document-processing.md)。

PDF/OCR、文件存储服务和持久化入库仍待接入。

## 本地知识检索（Alpha）

`backend.retrieval.LocalBM25Retriever` 实现 `KnowledgeIndexer` 和 `Retriever`。两个接口共用同一内存实例。配置 `file_root` 可检查真实资料文件及登记的 SHA-256。检索仅返回已明确开放的资料片段，并保留文档、版本和来源定位。

统一加载与只读查询入口（PR #35）：
- `load_approved_alpha_retriever()` / `build_approved_alpha_retriever()`：从 `knowledge_base/processed/alpha/approved/` 加载人工审核通过且 `retrieval_status=enabled` 的正式资料包。
- `LocalBM25Retriever.get_document_metadata(version_id: UUID)`（示例：`retriever.get_document_metadata(chunk.version_id)`）与 `get_parsed_chunk(chunk_id: UUID)`：供业务规则侧只读查询元数据与原始片段（返回深拷贝；不存在、未开放或重索引被剔除时返回 `None` 不抛异常）。
- **正式组装边界**：`build_approved_alpha_retriever()` 会丢弃 `AlphaCorpusLoadReport`；`load_approved_alpha_retriever()` 会将 `partial`（含来源未就绪导致 `indexed_count=0`）也计入 `loaded_packages`，且默认 `allow_missing=True` 缺目录时返回空索引与空报告。由于目录缺失与空目录都会返回空的 `index_results`、`warnings` 和 `total_indexed_chunks=0`，正式后端入口不能仅凭空报告判断知识库正常，应在正式组装时传入 `allow_missing=False` 或显式检查 `report.corpus_dir.is_dir()`，并核对 `index_results`（保守约定要求完整 `indexed`）、`warnings` 与 `total_indexed_chunks`，以区分“知识库目录缺失/未就绪”与“正常无命中”。

```bash
python -X utf8 -m scripts.demo_local_retrieval
python -X utf8 -m scripts.demo_local_retrieval --real
python -X utf8 -m unittest discover -s tests -p test_local_retrieval.py -v
```

默认示例用合成资料演示有命中和无命中两种情况。`--real` 校验仓库的三个真实资料包，预期问答检索均为空。接入方式和运行记录见 [检索报告](../docs/assignment-03/alpha/retrieval-report.md)。
