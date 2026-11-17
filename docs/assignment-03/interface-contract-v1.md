# CodeMind-FZU Alpha 接口规范 V1.0

> 项目：CodeMind-FZU（AgentX 团队）  
> 文档状态：**开发基线 / 待团队负责人确认**  
> 版本：V1.0  
> 规范负责人：罗宇泽（组长）  
> 架构分析协助：林世颖  
> 适用范围：Alpha 冲刺期间的学生端、后端、Agent、知识库、模型服务及后台管理端

本文是模块开发前的共同接口约定。它规定模块之间交换什么数据、调用什么方法、出现异常时如何表达；不规定各成员必须采用相同的内部算法或目录实现。

**重要边界：** 当前仓库已经有系统设计、数据库设计、ORM 模型源稿和知识库资料，但尚无完整运行中的 Web/Agent 应用。本规范和代码骨架是开发契约，不代表问答、数据库部署、检索或后台管理已经实现。

---

## 1. 设计原则

1. **接口先行：** 模块先遵守本规范，再独立开发；不得自行改变公共字段、类型、路径和状态值。
2. **单一事实来源：** 本文及 `backend/contracts/` 中的 Pydantic 模型是接口定义依据；接口变更由罗宇泽审核后统一发布。
3. **分层调用：** 浏览器只调用后端 HTTP API；后端调用 Agent；Agent 调用检索器和模型客户端；资料处理与索引由知识库模块提供。
4. **证据可追溯：** 回答引用必须能定位到文档、版本、知识片段及原始来源；不能用模型生成的文字伪造引用。
5. **状态不冒进：** 文档完成解析或建立索引，不代表政策已核验，也不代表可以进入正式问答检索。
6. **不锁死部署：** PostgreSQL 16、SQLAlchemy 2.0 是现有数据库设计的候选技术基线；本规范不宣称生产数据库已部署，也不强制当前 MVP 立即完成 PostgreSQL 接入。

## 2. 模块边界与负责人

| 模块 | 负责人 | 对外提供的能力 | 主要调用方 |
| --- | --- | --- | --- |
| 项目统筹与接口治理 | 罗宇泽 | 接口规范、公共数据结构、跨模块协调、集成与 PR 审核 | 全体成员 |
| 系统架构分析 | 林世颖 | 模块边界、依赖关系和架构说明 | 罗宇泽及各模块 |
| 学生端前端 | 吴欣键 | 问答输入、消息展示、引用展示 | 学生用户 |
| 前端交互与联调 | 洪添军 | 加载/错误/空状态、引用展开、交互验证 | 学生端、后端 |
| 后端 API 与模型适配 | 赵紫龙 | HTTP API、Agent 调用入口、Qwen 适配 | 前端、Agent |
| 后台管理端 | 林彦翔 | 资料列表、详情、元数据维护、导入/重建索引入口 | 管理人员、知识库服务 |
| Agent 工作流 | 吴诗莹 | 问题理解、路由、追问、工具编排、回答组织 | 后端 |
| 文档解析与资料处理 | 丁晓炜 | 官方资料解析、切片、元数据整理、入库包 | 索引模块、后台管理 |
| 数据库与检索 | 王智洋 | ORM/数据访问、检索、索引构建与检索验证 | Agent、资料处理 |
| 业务规则 | 雷葭雨 | 业务场景、必要条件、追问规则、验收问题 | Agent、测试 |
| 测试与质量保障 | 颜俊宇 | 契约测试、接口测试、集成测试和缺陷复测 | 全体模块 |
| 工程环境与部署 | 薛锦荣 | 依赖、环境变量模板、启动与构建说明 | 全体模块 |

**接口治理规则：** 罗宇泽是公共接口和跨模块集成的最终负责人。林世颖负责架构分析和模块依赖建议，不代替组长决定接口版本。各模块负责人可以提出修改建议，但不得未经确认单方面变更公共契约。

## 3. 总体调用关系

```text
学生浏览器
  │ HTTP/JSON
  ▼
FastAPI 后端（赵紫龙）
  │ AgentRequest / AgentResult
  ▼
Agent 工作流（吴诗莹）
  ├── 业务规则配置（雷葭雨提供）
  ├── 检索接口（王智洋提供）
  │      ▲
  │      └── 资料解析/切片/元数据（丁晓炜提供）
  └── 模型客户端（赵紫龙提供 Qwen 适配）
  │
  ▼
统一 AskResponse
  │ HTTP/JSON
  ▼
学生浏览器（吴欣键、洪添军）

后台管理端（林彦翔）
  │ HTTP/JSON 管理接口
  ▼
后端管理服务
  ├── 文档解析（丁晓炜）
  └── 数据存储与索引（王智洋）
```

浏览器与后端之间使用 HTTP/JSON；后端与 Agent、Agent 与检索/模型之间优先使用 Python 类型化接口，不为内部调用额外引入 HTTP 服务。

## 4. 通用约定

### 4.1 命名与格式

| 项目 | 约定 | 示例 |
| --- | --- | --- |
| API 前缀 | `/api/v1` | `/api/v1/ask` |
| API 路径 | 小写、资源名词 | `/api/v1/admin/documents` |
| JSON 字段 | `snake_case` | `conversation_id` |
| Python 函数/变量 | `snake_case` | `retrieve_chunks` |
| Python 类 | `PascalCase` | `AgentRequest` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_TOP_K` |
| 数据库字段 | 沿用现有关系模型字段名 | `retrieval_status` |
| UUID | 标准 UUID 字符串 | `550e8400-e29b-41d4-a716-446655440000` |
| 日期 | ISO 8601 日期 | `2026-11-17` |
| 时间戳 | ISO 8601，必须带时区 | `2026-11-17T08:30:00Z` |

- JSON 可选字段无值时使用 `null`；空集合使用 `[]`，不使用 `null`。
- 时间戳按 UTC 存储和传递；界面显示时转换为 `Asia/Shanghai`。政策生效日、发布日期等日历日期使用 `DATE` 语义，不擅自补时区。
- 不向浏览器传递数据库连接串、模型密钥、内部堆栈或本地绝对路径。
- 浏览器不得直接访问数据库或 Chroma。

### 4.2 统一状态

**问答执行状态 `status`：**

| 值 | 含义 | 前端处理 |
| --- | --- | --- |
| `answered` | 已形成回答 | 展示回答和引用 |
| `needs_clarification` | 缺少必要条件，需要追问 | 展示 `clarifying_question`，等待用户补充 |
| `insufficient_evidence` | 当前没有足够依据形成可靠结论 | 展示解释和 warnings，不得伪造政策答案 |

**回答用途 `answer_mode`：**

| 值 | 含义 |
| --- | --- |
| `current_policy` | 当前政策结论 |
| `historical` | 历史政策信息 |
| `procedure_reference` | 已核验的历史办理流程参考 |
| `insufficient_data` | 资料不足、条件不明或证据不满足要求 |

`status` 表示本次交互处于什么结果状态；`answer_mode` 表示回答按什么用途使用，两者不能混为一个字段。

**资料与检索状态沿用数据库设计：**

- 来源核验：`pending`、`partial`、`verified`、`failed`。
- 时效核验：`pending`、`current`、`historical`、`superseded`、`expired`、`uncertain`。
- 正文提取：`pending`、`extracted`、`needs_ocr`、`failed`。
- 检索开放：`blocked`、`review_only`、`enabled`。
- 文件角色：`original`、`attachment`、`extracted`、`curated`。
- 片段索引：`pending`、`indexed`、`failed`、`disabled`。

**严禁把“已解析”“已入库”或“已建立向量索引”自动等同于“政策已核验”或“可以正式检索”。** 当前知识库入库设计将资料默认设为 `retrieval_status=blocked`；只有满足审核条件并经人工/业务流程明确开放后，检索器才能用于正式问答。不得为了演示而批量改成 `enabled`。

## 5. 学生端与后端 HTTP API

### 5.1 健康检查

- 方法：`GET`
- 路径：`/api/v1/health`
- 成功状态码：`200`

响应：

```json
{
  "status": "ok",
  "service": "codemind-fzu-api",
  "version": "0.1.0",
  "timestamp": "2026-11-17T08:30:00Z"
}
```

该接口只表示 API 进程可响应，不代表数据库、模型、检索器或 Agent 均已连通。

### 5.2 提交问题

- 方法：`POST`
- 路径：`/api/v1/ask`
- Content-Type：`application/json`
- 成功状态码：`200`

请求：

```json
{
  "query": "申请国家奖学金需要满足什么条件？",
  "conversation_id": null
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `query` | string | 是 | 用户当前问题，去除首尾空白后不能为空，最多 4000 字符 |
| `conversation_id` | UUID / null | 否 | 已有会话标识；首次提问传 null，由后端创建 |

前端不传完整历史消息作为可信依据。后端应根据 `conversation_id` 从会话存储中读取历史；若本阶段尚未实现持久化，可在服务内部暂时使用空历史，但不得让前端和 Agent 各自维护互不一致的历史结构。

成功响应：

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "answered",
  "answer": "根据已核验的相关文件……",
  "answer_mode": "current_policy",
  "clarifying_question": null,
  "citations": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440002",
      "version_id": "550e8400-e29b-41d4-a716-446655440003",
      "chunk_id": "550e8400-e29b-41d4-a716-446655440004",
      "title": "示例政策文件",
      "publisher": "福州大学",
      "source_url": "https://example.edu.cn/policy",
      "published_on": "2026-06-01",
      "effective_on": "2026-09-01",
      "locator": "第三条",
      "original_locator": "PDF 第 2 页",
      "excerpt": "与本次回答直接相关的原文摘录。",
      "source_verification_status": "verified",
      "timeliness_verification_status": "current",
      "retrieval_status": "enabled"
    }
  ],
  "warnings": [],
  "created_at": "2026-11-17T08:30:00Z"
}
```

上述 ID 和内容仅为格式示例，不对应仓库中的真实资料。

追问响应：

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440010",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "needs_clarification",
  "answer": null,
  "answer_mode": null,
  "clarifying_question": "请问你咨询的是哪一学年的奖学金评定？",
  "citations": [],
  "warnings": [],
  "created_at": "2026-11-17T08:31:00Z"
}
```

证据不足响应：

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440011",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "insufficient_evidence",
  "answer": "目前没有找到满足检索开放和核验要求的资料，暂时不能给出确定结论。",
  "answer_mode": "insufficient_data",
  "clarifying_question": null,
  "citations": [],
  "warnings": [
    {
      "code": "NO_ELIGIBLE_EVIDENCE",
      "message": "未找到允许用于正式回答的证据。"
    }
  ],
  "created_at": "2026-11-17T08:31:00Z"
}
```

### 5.3 引用对象 `Citation`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `document_id` | UUID | 逻辑文档 ID |
| `version_id` | UUID | 被引用的具体版本 ID |
| `chunk_id` | UUID | 实际使用的知识片段 ID |
| `title` | string | 引用标题快照 |
| `publisher` | string / null | 发布单位 |
| `source_url` | string | 登记的官方来源网址；存在不等于已核验 |
| `published_on` | date / null | 发布日期 |
| `effective_on` | date / null | 生效日期 |
| `locator` | string / null | 片段在整理文件中的定位 |
| `original_locator` | string / null | 官方原件定位；未核实则 null |
| `excerpt` | string | 实际引用的证据摘录 |
| `source_verification_status` | enum | 来源核验状态 |
| `timeliness_verification_status` | enum | 时效核验状态 |
| `retrieval_status` | enum | 检索开放状态 |

不要把整理稿行号伪装成官方 PDF 页码；未知定位留 null。引用快照应对应本次回答实际采用的版本和片段，不能用“最近一条检索结果”代替真实引用。

## 6. 后端与 Agent 的 Python 接口

后端（赵紫龙）调用 Agent（吴诗莹）时，使用 `backend/contracts/models.py` 中的类型：

```python
async def run_agent(request: AgentRequest) -> AgentResult:
    ...
```

`AgentRequest` 包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `request_id` | UUID | 本次请求追踪标识 |
| `conversation_id` | UUID | 当前会话标识 |
| `query` | string | 当前用户问题 |
| `history` | list[ConversationTurn] | 后端加载的历史消息；初期可为空 |

`AgentResult` 必须返回统一的 `status`、`answer`、`answer_mode`、`clarifying_question`、`citations`、`warnings`。不允许有时返回字符串、有时返回字典或自定义不明结构。

后端负责生成/沿用 `request_id` 和 `conversation_id`，将 AgentResult 包装为 AskResponse；Agent 不直接构造 HTTP Response。

## 7. Agent 与检索模块的接口

Agent（吴诗莹）调用检索器（王智洋）：

```python
async def retrieve(request: RetrievalRequest) -> list[RetrievedChunk]:
    ...
```

`RetrievalRequest`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `query` | string | 待检索问题或检索表达 |
| `top_k` | int | 返回数量，默认 5，范围 1–20 |
| `business_direction_code` | string / null | 五大业务方向代码，可选 |
| `category_name` | string / null | 七类知识主题名称，可选 |

`RetrievedChunk` 至少包含：

- `chunk_id`、`document_id`、`version_id`、`file_id`；
- `content`、`title`、`publisher`、`source_url`；
- `published_on`、`effective_on`；
- `locator`、`original_locator`；
- `score`、`retrieval_method`；
- `source_verification_status`、`timeliness_verification_status`、`retrieval_status`。

检索器默认只返回 `retrieval_status=enabled` 的片段。若没有符合条件的证据，返回空列表 `[]`，不要返回 blocked 资料供 Agent 当作正式政策依据。若未来增加内部审核检索，必须使用单独的审核接口/标记，不得混入正式问答检索结果。

`score` 是排序分数，不保证归一化到 0–1；RRF 分数尤其不能被解释为概率或置信度。

## 8. 文档解析与索引接口

### 8.1 丁晓炜：文档解析

```python
def parse_document(
    file_path: Path,
    metadata: DocumentMetadata,
) -> DocumentPackage:
    ...
```

`DocumentPackage` 由三部分组成：

1. `metadata`：文档身份、版本、来源、发布日期、适用范围和核验状态；
2. `files`：原始网页、附件、提取正文或整理稿的文件记录；
3. `chunks`：切片正文、片段序号和来源定位。

`storage_key` 是相对于受控资料根目录的逻辑键，不是用户电脑的绝对路径。原始文件与附件保留在文件系统/对象存储；关系数据库保存路径键、文件名、哈希和处理状态，不把二进制文件塞进文本字段。

### 8.2 王智洋：入库与索引

```python
async def index_document(package: DocumentPackage) -> IndexResult:
    ...
```

索引结果返回 `document_id`、`version_id`、处理状态、片段总数、成功索引数及 warnings。

索引成功只说明索引构建完成，不得自动将资料 `retrieval_status` 改为 `enabled`。开放检索必须满足数据库设计中的先决条件：首版纳入、来源核验通过、正文提取完成、时效状态已明确，并经负责人员确认。

### 8.3 分类字段不能混用

- `category_name` 对应数据库的七类 `knowledge_categories` 主分类。
- `business_direction_codes` 对应五大 `business_directions` 业务方向标签，可多选。
- 三个重点验收场景（竞赛认定、奖学金、推免）是测试任务，不是新增业务方向代码。

## 9. Agent 与 Qwen 模型接口

赵紫龙提供模型适配器，吴诗莹只依赖统一调用协议：

```python
async def generate(request: LLMGenerateRequest) -> LLMResult:
    ...
```

请求由 `messages`（system/user/assistant）、`temperature` 和 `max_tokens` 组成；结果包含 `content`、实际模型名 `model` 和可用时的 `usage`。

- API Key 只从环境变量读取，不写入源码、文档、日志或 Git 历史。
- Agent 负责构造提示词、组织证据和复核结果；模型客户端负责网络调用、超时、重试策略及供应商响应适配。
- 模型输出不是证据。模型不得自行创造 citation；引用只能来自 Retriever 返回并被本次回答实际采用的片段。

## 10. 后台管理 HTTP API（契约范围）

林彦翔负责管理页面和管理端 API 对接；资料解析由丁晓炜提供，数据存储/索引由王智洋提供。

| 方法 | 路径 | 用途 | 阶段 |
| --- | --- | --- | --- |
| GET | `/api/v1/admin/documents` | 资料分页列表，可按状态筛选 | P1 |
| GET | `/api/v1/admin/documents/{document_id}` | 资料详情、版本与处理状态 | P1 |
| POST | `/api/v1/admin/documents` | 上传/登记资料并触发解析 | P1 |
| PATCH | `/api/v1/admin/documents/{document_id}` | 修改允许维护的元数据 | P1 |
| POST | `/api/v1/admin/documents/{document_id}/reindex` | 重新构建索引 | P1 |

建议分页参数：`page` 从 1 开始，`page_size` 默认 20、最大 100；列表响应使用 `items`、`total`、`page`、`page_size`。

上传成功先返回 `processing`，完成后返回 `indexed` 或 `failed`。管理端不能绕过核验流程直接开放检索。

**安全边界：** 当前项目尚未完成认证/授权接入。管理 API 在鉴权完成前仅用于本地开发或受控测试环境，不得直接暴露到公网，也不得把“前端隐藏按钮”当作权限控制。

## 11. 统一错误格式

所有已实现 API 应返回统一错误 envelope：

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440020",
  "error": {
    "code": "MODEL_TIMEOUT",
    "message": "模型服务暂时不可用，请稍后重试。",
    "retryable": true
  }
}
```

建议错误代码：

| code | 含义 |
| --- | --- |
| `INVALID_REQUEST` | 请求格式或参数错误 |
| `RESOURCE_NOT_FOUND` | 资源不存在 |
| `MODEL_TIMEOUT` | 模型请求超时 |
| `MODEL_UNAVAILABLE` | 模型服务不可用 |
| `RETRIEVAL_FAILED` | 检索模块异常 |
| `NO_ELIGIBLE_EVIDENCE` | 没有满足检索开放条件的证据 |
| `DOCUMENT_PROCESSING_FAILED` | 文档解析或入库失败 |
| `SERVICE_NOT_CONFIGURED` | 对应服务尚未接入 |
| `RATE_LIMITED` | 请求频率超限 |
| `INTERNAL_ERROR` | 未分类的内部错误 |

建议 HTTP 状态码：200（业务正常处理，含追问/证据不足状态）、400（请求错误）、404（资源不存在）、422（参数校验失败）、429（频率限制）、500（内部错误）、502（上游模型异常）、503（依赖服务不可用）。

错误响应不得包含密钥、堆栈、数据库连接串或服务器绝对路径。

## 12. 代码目录与运行约定

本 PR 建立的初始目录：

```text
backend/
├── app/
│   └── main.py                 # FastAPI 应用骨架：health、ask
├── contracts/
│   ├── models.py               # Pydantic v2 公共数据模型
│   └── protocols.py            # Agent、Retriever、Parser、Indexer、LLM协议
└── requirements.txt            # 后端接口骨架依赖

docs/assignment-03/
└── interface-contract-v1.md    # 本接口规范
tests/
└── test_interface_contracts.py # 契约模型测试
```

从仓库根目录启动：

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload
```

- 健康检查：`GET http://127.0.0.1:8000/api/v1/health`
- 问答接口：`POST http://127.0.0.1:8000/api/v1/ask`
- 交互式 API 文档：`http://127.0.0.1:8000/docs`

当前代码骨架只实现健康检查和问答接口的契约入口；Agent 未注入时，问答接口会返回 `503 SERVICE_NOT_CONFIGURED`，不会伪造模型回答。管理 API 先在本规范中约定，待后台开发阶段实现。

## 13. 开发、测试与接口变更流程

1. 各模块负责人先阅读本文和 `backend/contracts/`。
2. 开发前先导入公共模型/Protocol，不在各模块重复定义相同 DTO。
3. 每个模块至少提供一个成功用例和一个失败/边界用例。
4. PR 描述必须写明：实现的接口、输入/输出示例、依赖模块、测试命令及结果。
5. 不提交真实 `.env`、API Key、数据库密码、学生个人信息或原始敏感数据。
6. 修改公共字段、类型、状态、路径或函数签名前，先向罗宇泽提出变更；批准后同步更新文档、Pydantic 模型、调用方和测试。
7. 不兼容变更升级主版本（V2.0）；向后兼容新增字段/接口升级次版本（V1.1）；文档或不影响契约的修正升级补丁版本（V1.0.1）。

## 14. 本次 Alpha 的实施优先级

| 优先级 | 内容 | 说明 |
| --- | --- | --- |
| P0 | `GET /api/v1/health`、`POST /api/v1/ask`、Agent/检索/模型公共类型 | 先打通最小问答闭环 |
| P0 | DocumentPackage、RetrievedChunk、IndexResult | 资料处理与检索能独立联调 |
| P1 | 后台资料列表、详情、导入、元数据修改、重新索引 | 核心问答闭环稳定后推进 |
| P1 | 完整会话持久化、认证授权、复杂管理能力 | 按剩余时间安排；不得以未实现功能冒充完成 |

## 15. 现有设计约束与待确认事项

1. 数据库设计为 23 张表、233 个字段；ORM 设计采用 PostgreSQL 16 + SQLAlchemy 2.0 候选基线。实际数据库部署和 ORM 在线接入尚未完成。
2. 知识库设计中，资料原件/附件存文件系统或对象存储，关系数据库保存元数据、版本、状态、定位和引用；向量索引的具体嵌入模型及部署方案尚未最终确定。
3. 现有知识库入库方案明确：资料默认 blocked；官方来源、时效、适用范围、正文及附件核验未完成时，不得作为正式政策答案依据。
4. 当前没有认证授权实现；管理端 API 不能对公网开放。
5. 本文中的示例 UUID、来源网址和回答仅展示格式，不是实际资料、真实政策结论或已运行结果。

---

**规范维护人：罗宇泽（组长）**  
**架构分析协助：林世颖**  
**版本：V1.0 · Alpha 开发接口基线**
