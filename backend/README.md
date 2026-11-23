# Backend API、Agent 与检索

> **Beta 阶段说明（2026-11-23）**：本机单进程运行即可验收，不依赖云服务器与 PostgreSQL；
> 会话使用内存实现 `InMemoryConversationStore`。Windows 本机运行、干净环境验证与四大场景的记录见
> [`docs/assignment-03/beta/windows-runtime-test.md`](../docs/assignment-03/beta/windows-runtime-test.md)。

本目录提供 CodeMind-FZU Alpha 阶段的 FastAPI HTTP 入口、公共 Pydantic v2 契约、真实运行组装、服务端会话历史、Mock Agent、Qwen 适配器、AgentWorkflow、Markdown/TXT 文档解析和本地 BM25 检索。

## 一、运行入口

| 入口 | 用途 | 说明 |
|---|---|---|
| `backend.app.alpha:app` | **真实 Alpha 运行** | 启动时加载已审核资料、初始化 Qwen、装配 AgentWorkflow 与会话历史 |
| `backend.app.dev:app` | Mock 联调 | 固定模拟回答，不需要 Qwen 密钥 |
| `backend.app.main:app` | 默认骨架 | 未注入 Agent，`/api/v1/ask` 返回 503 |

真实入口通过 FastAPI lifespan 调用审核加载入口，默认只扫描 `knowledge_base/processed/alpha/approved/`，并要求 `retrieval_status=enabled` 与 manifest/`temporal_notes` 的人工审核标记为严格 `true`。`blocked`、`review_only`、未审核和测试侧车 JSON 不会进入正式索引。

目录缺失、没有已审核资料包、部分索引或出现 warnings 时，服务仍可启动，但问答返回 `503 KNOWLEDGE_BASE_UNAVAILABLE`，**不会改用原始测试资料**。

## 二、环境要求

| 项目 | 要求 | 本次干净环境验证 |
|---|---|---|
| Python | **3.10 及以上**（推荐 3.10 / 3.11） | Python 3.10.11 |
| 运行依赖 | `backend/requirements.txt` | fastapi 0.162.5、pydantic 2.14.4、uvicorn 0.54.0、httpx 0.28.1 |
| 完整验证依赖 | `scripts/requirements-alpha-verification.txt`（pytest 等） | 已验证安装 |
| 系统 | Windows / macOS / Linux | Windows 11 |

> 干净环境验证中发现并修复了两个 Python 3.10 / Windows 兼容问题：
> 1. `asyncio.wait_for` 在 3.10 抛 `asyncio.TimeoutError`，原代码只捕获内建 `TimeoutError`，已兼容两种类型；
> 2. 会话清理测试使用 `1e-9` 秒阈值，Windows `monotonic()` 分辨率约 15ms 导致误判，测试已改为可观测时间片（不影响运行时逻辑）。

## 三、安装依赖

从仓库根目录执行：

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r backend/requirements.txt
```

跑完整测试/验证脚本时再安装：

```bash
python -m pip install -r scripts/requirements-alpha-verification.txt
```

国内网络可加镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple`。

## 四、启动

### 4.1 真实 Alpha 入口

```bash
python -m uvicorn backend.app.alpha:app --reload --port 8000 --env-file backend/.env
```

需要：

- 本地 `backend/.env` 中配置 `QWEN_API_KEY`；
- `ALPHA_PACKAGE_DIR` 指向已审核资料目录（默认 `knowledge_base/processed/alpha/approved`）；
- 该目录中至少有一份审核通过、`retrieval_status=enabled` 的资料包。

缺少密钥或资料时服务仍会启动，但 `/api/v1/ask` 返回 503 与明确错误码，不伪造回答。

### 4.2 Mock Agent（前后端联调，无需密钥）

```bash
python -m uvicorn backend.app.dev:app --reload --port 8000
```

### 4.3 默认骨架

```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```

`/api/v1/ask` 返回 `503 SERVICE_NOT_CONFIGURED`，属预期行为。

### 4.4 离线验证（不调用真实模型）

```bash
python -m scripts.check_retrieval_agent
python -m scripts.check_document_processing
python -m examples.agent_workflow_demo
```

## 五、环境变量与 Qwen

```bash
cp backend/.env.example backend/.env
python -m uvicorn backend.app.alpha:app --port 8000 --env-file backend/.env
```

变量说明见 [`backend/.env.example`](.env.example)：

| 变量 | 是否必填 | 默认 | 说明 |
|---|---|---|---|
| `CORS_ALLOW_ORIGINS` | 可选 | 覆盖 5173/3000/5500 | 逗号分隔，禁止 `*` |
| `QWEN_API_KEY` | 真实调用必填 | 空 | 仅本地保存，禁止提交 |
| `QWEN_BASE_URL` | 可选 | DashScope compatible | 必须是 http(s) |
| `QWEN_MODEL` | 可选 | `qwen-flash` | 需账号有权限 |
| `QWEN_TIMEOUT_SECONDS` | 可选 | `28` | 必须 > 0 |
| `QWEN_MAX_RETRIES` | 可选 | `0` | 0–3 |
| `ALPHA_PACKAGE_DIR` | 可选 | `knowledge_base/processed/alpha/approved` | 已审核资料目录 |
| `CONVERSATION_MAX_MESSAGES` | 可选 | `12` | 2–50，奇数向下取整为完整轮次 |
| `CONVERSATION_HISTORY_CHAR_LIMIT` | 可选 | `6000` | 200–50000 |
| `CONVERSATION_MAX_COUNT` | 可选 | `1000` | 内存会话上限 |
| `CONVERSATION_IDLE_SECONDS` | 可选 | `3600` | 空闲回收时间 |
| `CONVERSATION_CLEANUP_INTERVAL_SECONDS` | 可选 | `300` | 清理间隔 |

`QwenLLMClient.generate()` 遵循公共 `LLMClient` 协议；超时、限流、上游异常会转换为可安全返回的服务错误。未配置密钥时真实入口返回配置错误，不会伪造回答。

## 六、知识库与审核资料加载

1. 读取 `ALPHA_PACKAGE_DIR` 下的 `DocumentPackage` JSON；
2. 只接受 `retrieval_status=enabled` 且人工审核标记严格为 `true` 的资料；
3. 用 `LocalBM25Retriever` 建内存索引，同一实例同时用于索引与检索；
4. 任一份资料索引失败、出现 warnings 或目录为空时，正式问答整体不可用（503），不会部分开放；
5. 三个 Alpha 样例资料仍为 `blocked`，因此样例不会进入正式问答。

相关实现：`backend/retrieval/alpha_corpus.py`；诊断脚本：`scripts/run_alpha_agent.py`。

## 七、接口与 CORS

默认 API 前缀 `/api/v1`：

- `GET /api/v1/health`
- `POST /api/v1/ask`（`query`，可选 `conversation_id`）
- 状态值：`answered`、`needs_clarification`、`insufficient_evidence`
- 服务端按 `conversation_id` 保存有界会话历史（仅内存）

CORS 使用显式来源列表，不允许 `*`；默认覆盖 5173/3000/5500，非法来源或 `*` 会在启动阶段被拒绝。

## 八、测试

```bash
python -m unittest discover -s tests -v
```

本次干净环境（Windows 11 + Python 3.10.11，代码基线 `origin/main`）结果：**275 项执行，通过 247、跳过 28、失败 0**。

28 项跳过的构成：25 项等待 `scripts.verify_alpha_upstream_integration` 单独执行的上游集成用例（该脚本已单独执行并通过 25 项）、2 项真实 Qwen 验收（需 `RUN_LIVE_QWEN_TESTS=1` 与审核语料）、1 项 Windows 符号链接权限限制。详见
[`docs/assignment-03/beta/windows-runtime-test.md`](../docs/assignment-03/beta/windows-runtime-test.md)。

专项检查：

```bash
python -m scripts.check_document_processing
python -m scripts.check_retrieval_agent
```

## 九、文档解析（Alpha）

`backend.document_processing.TextDocumentParser` 实现 `DocumentParser` 协议，返回公共 `DocumentPackage`。支持 Markdown/TXT、标题层级、片段编号、行号/字符定位和哈希；输出保持 `retrieval_status=blocked`。PDF/OCR 仅登记待处理，不伪造正文。

```bash
python -m scripts.parse_alpha_documents
python -m scripts.check_document_processing
```

## 十、本地知识检索（Alpha）

`backend.retrieval.LocalBM25Retriever` 实现 `KnowledgeIndexer` 与 `Retriever`，两个接口共用同一内存实例。配置 `file_root` 可检查真实资料文件及登记 SHA-256；检索只返回已开放片段。

```bash
python -X utf8 -m scripts.demo_local_retrieval
python -X utf8 -m scripts.demo_local_retrieval --real
```

## 十一、公共契约

- `contracts/models.py`：请求、响应、引用、检索片段、资料入库包、索引结果及模型调用数据结构。
- `contracts/protocols.py`：Agent、Retriever、DocumentParser、KnowledgeIndexer、LLMClient、DocumentAdminService 的模块边界。
- 说明见 [Alpha 接口规范 V1.0](../docs/assignment-03/interface-contract-v1.md)。

公共字段、状态值或函数签名需要修改时，先向罗宇泽提出并等待统一更新。

## 十二、当前边界

- 真实 Qwen 调用需要本地密钥与已审核资料，本轮未使用真实密钥做正向验收；
- `knowledge_base/processed/alpha/approved/` 目前没有正式审核包时，真实问答返回 503；
- 文件存储服务与持久化资料入库；
- PostgreSQL/SQLAlchemy 在线连接与迁移；
- Chroma/RRF 混合检索（当前为本地 BM25）；
- 管理端业务 API 与认证授权（前端管理页调用后台接口会得到 404）。

## 十三、运行指南与验证记录

- 完整环境、前后端启动、联调与常见问题：[Beta Windows 本机运行指南](../docs/assignment-03/beta/windows-runtime-test.md)（Alpha 历史记录见 [Alpha 阶段运行说明](../docs/assignment-03/alpha/run-guide.md)）
- 本轮干净环境验证证据：[evidence](../docs/assignment-03/beta/evidence/)
