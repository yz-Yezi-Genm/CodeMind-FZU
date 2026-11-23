# CodeMind-FZU Beta 接口规范 V2.1-Final

> **项目：** CodeMind-FZU（AgentX 团队）  
> **文档状态：** Beta 冲刺正式执行版  
> **版本：** V2.1-Final  
> **基础版本：** Alpha 接口规范 V1.0、Beta 接口规范 V2.0-Draft  
> **规范负责人：** 罗宇泽  
> **适用阶段：** Beta 冲刺（2026-11-23 至 2026-12-06）  
> **适用范围：** 前端、后端 API、Agent、业务规则、文档解析、知识库及模型服务  
> **仓库：** https://github.com/yz-Yezi-Genm/CodeMind-FZU

------------------------------------------------------------------------

## 本次修订摘要

V2.1-Final 在保留 Alpha 已有公共接口和实现基础的前提下，冻结 Beta 阶段的技术范围和模块协作约定。

| 项目                              | V2.1-Final 决定                                                            |
|-----------------------------------|----------------------------------------------------------------------------|
| Agent 业务场景                    | S1 竞赛认定、S2 奖学金申请、S3 推免条件咨询、S4 学院资源导航               |
| 数据库业务方向                    | 保留五大方向；实际 code 以仓库正式字典为准，不得自行创造                   |
| 检索技术                          | LocalBM25Retriever / BM25 为 Beta 正式验收基线                             |
| Qwen 回答                         | 使用受约束的自然语言生成；引用由 Agent 根据真实证据构造和校验              |
| XLSX 资料                         | 本轮采用提取后转换为 Markdown/TXT 的方式，不新增通用 XLSX 解析接口         |
| 会话存储                          | 继续使用 InMemoryConversationStore，支持单进程本机运行                     |
| 数据库持久化                      | 不要求 PostgreSQL 在线接入或持久化改造                                     |
| 管理端                            | 不要求完整管理端后端 HTTP API；已有前端原型不代表后端功能已实现            |
| Chroma / Embedding / RRF / Tavily | 不列入 Beta 必做和验收范围                                                 |
| 正式资料                          | 必须经过来源、适用范围、时效核验及项目负责人最终人工审核，才能进入正式问答 |

**兼容性声明：** V2.1-Final 不要求将 HTTP API 升级为 `/api/v2`，不擅自修改 Alpha 已有 HTTP 路径、公共字段及状态枚举。本文新增的 S4 和模型内部输出约定不等于新增学生端 HTTP 字段。

------------------------------------------------------------------------

## 一、修订目的

Alpha 阶段已经建立公共数据模型和模块接口，并完成了以下基础能力：

1.  FastAPI 问答入口及统一请求响应模型。
2.  AgentWorkflow 基础工作流。
3.  Qwen 模型适配器。
4.  Markdown/TXT 文档解析。
5.  本地 BM25 检索器。
6.  S1、S2、S3 业务规则。
7.  基于 `conversation_id` 的服务端会话历史管理。

Beta 阶段的重点不是重新设计一套系统，而是让上述模块在统一契约下协同工作，并补齐现有接口中的不足。

本规范主要解决：

- Agent 与 Retriever 的调用及元数据查询接口不完整。
- 业务规则与 Agent 工作流之间的历史政策处理不一致。
- 业务场景与数据库业务方向容易混淆。
- S4 学院资源导航尚未纳入与 S1—S3 同等级的正式业务规则。
- 多轮对话中的历史信息需要统一管理。
- 模型生成答案时的证据边界和引用构造方式需要统一。
- XLSX 等非当前解析范围的资料需要明确处理边界。
- 各模块的错误处理和测试验收标准需要统一。

本规范是 Beta 阶段的公共接口基线。各负责人可以自由设计模块内部实现，但不得擅自修改公共契约。

## 二、接口设计原则

1.  **单一事实来源：** 公共模型以 `backend/contracts/models.py` 为准，接口协议以 `backend/contracts/protocols.py` 为准。
2.  **兼容 Alpha：** 不随意修改已有公共字段、状态值及 HTTP 路径。
3.  **模块独立：** 各负责人可以自由设计内部实现，但不得擅自修改模块间接口。
4.  **类型明确：** Python 模块之间使用 Pydantic DTO 和 Protocol，不使用无约束的字典作为主要交换格式。
5.  **证据优先：** Agent 不能创造政策依据，所有引用必须来自本次真实检索且通过证据门禁的结果。
6.  **失败关闭：** 资料适用范围、时效、来源核验或人工审核状态无法确认时，不得放行。
7.  **可测试：** 每个模块必须提供独立单元测试和符合公共契约的测试替身。
8.  **范围受控：** Beta 以本规范和 Beta 冲刺任务书列出的交付范围为准，不因开题 PPT 中的远期技术设想而自动扩大本轮任务。

特别说明：V2.1 是接口规范的文档版本，不代表 HTTP API 必须升级为 `/api/v2`。

## 三、系统总体调用关系

``` text
                         学生浏览器
                              |
                          HTTP / JSON
                              |
                              v
                         FastAPI 后端
                              |
                  会话管理、请求追踪、服务组装
                              |
                              v
                         AgentRequest
                              |
                              v
                         AgentWorkflow
                    /         |          \
                   /          |           \
                  v           v            v
              业务规则     Retriever     QwenClient
                  |           |
                  |           v
                  |     RetrievedChunk
                  |           |
                  |     DocumentMetadata
                  |           |
                  |       ParsedChunk
                  |           ^
                  |           |
                  |    KnowledgeIndexer
                  |           ^
                  |           |
                  |    DocumentPackage
                  |           ^
                  |           |
                  |    DocumentParser
                  |
                  v
              证据适用性判断
                  |
                  v
             受约束答案生成与引用校验
                  |
                  v
               AgentResult
                  |
                  v
               AskResponse
                  |
                  v
               学生浏览器
```

模块职责：

| 模块             | 主要职责                                             |
|------------------|------------------------------------------------------|
| FastAPI 后端     | HTTP 接口、会话管理、请求追踪、请求校验、服务组装    |
| AgentWorkflow    | 工作流编排、场景识别、追问、检索、证据过滤、答案组织 |
| 业务规则         | 场景判断、必要信息检查、证据适用性判断、历史政策判定 |
| Retriever        | 资料检索、片段返回、元数据及章节信息查询             |
| DocumentParser   | 文件解析、元数据整理、知识切片                       |
| KnowledgeIndexer | 资料入库、索引构建、索引结果返回                     |
| QwenClient       | 模型调用、超时处理、响应适配                         |
| 项目负责人       | 正式资料最终审核、公共接口冻结、PR 集成及最终验收    |

模块之间不得绕过公共接口直接访问其他模块的内部变量。

## 四、业务领域与场景编号

必须区分**数据库业务方向**和 **Agent 业务场景**。两者不是同一套编号。

### 4.1 数据库业务方向

依据现有数据库设计，保留以下五大业务方向：

| 业务方向               | 主要内容                         | Beta 范围 |
|------------------------|----------------------------------|-----------|
| 政策与事务办理         | 奖学金、评优评奖、校园事务       | 纳入      |
| 升学与就业发展         | 推免、升学及发展政策             | 纳入      |
| 竞赛与科研信息         | 竞赛认定、创新学分、科研实践     | 纳入      |
| 学院资源导航           | 培养方案、学习科研资源、办事渠道 | 纳入      |
| 个人成长档案与长期规划 | 长期成长记录及规划               | 后续迭代  |

一份资料允许关联多个业务方向。

数据库字段 `business_direction_codes` 保存业务方向代码。**实际代码值必须以仓库现有数据库正式字典、初始化数据或已合并代码为准，不得自行创造、猜测或另起一套代码。**

如果当前仓库中尚不能确认某个代码值，应由项目负责人协调数据库设计负责人核对后再使用。

### 4.2 Beta 阶段 Agent 业务场景

Beta 阶段正式采用四个 Agent 业务场景：

| 场景编号 | 场景名称                       | 对应数据库业务方向 | Beta 范围 |
|----------|--------------------------------|--------------------|-----------|
| S1       | 竞赛认定（创新学分、综测加分） | 竞赛与科研信息     | 正式纳入  |
| S2       | 奖学金申请                     | 政策与事务办理     | 正式纳入  |
| S3       | 推免条件咨询                   | 升学与就业发展     | 正式纳入  |
| S4       | 学院资源导航                   | 学院资源导航       | Beta 新增 |

S4 主要覆盖：

- 学院官方资源、办事渠道和公开信息查询。
- 实验室名称、研究方向、报名流程及适用对象查询。
- 官方培养方案、学习和科研资源导航。
- 资源信息缺失、来源不明或时效无法确认时的提示与拒答。

S4 不代表本轮必须实现动态科研机会推荐、实时招生名额查询或未经官方资料支持的导师评价。

注意：

- S1—S4 是 Agent 业务场景编号，不是数据库业务方向代码。
- S4 在 Beta 中必须有正式业务规则、检索测试和端到端验收。
- 个人成长档案与长期规划不属于 S1—S4，不纳入本轮必做范围。
- 不得把五大数据库业务方向直接命名为 S1—S5。

### 4.3 多业务方向问题的检索约定

当前 `RetrievalRequest` 仅定义单个 `business_direction_code`，本轮不擅自将其改为列表字段。

当问题涉及多个业务方向，或者 Agent 无法可靠确定唯一方向时：

1.  不得猜测一个方向代码并据此缩小检索范围。
2.  可以不传 `business_direction_code`，执行全库检索。
3.  由 Agent 和业务规则根据检索证据进行后续筛选。
4.  如果后续确实需要多方向过滤，应先由项目负责人发起公共接口变更，不得由成员自行增加字段。

## 五、学生端 HTTP API

Beta 阶段保留 Alpha 的 HTTP API，不修改路径。

### 5.1 健康检查

``` http
GET /api/v1/health
```

返回示例：

``` json
{
  "status": "ok",
  "service": "codemind-fzu-api",
  "version": "0.1.0",
  "timestamp": "2026-11-23T00:00:00Z"
}
```

该接口仅用于确认 API 进程可用，不代表数据库、Agent、检索器及模型均已正常工作。

### 5.2 问答接口

``` http
POST /api/v1/ask
Content-Type: application/json
```

请求示例：

``` json
{
  "query": "申请校级奖学金需要什么条件？",
  "conversation_id": null
}
```

字段：

| 字段            | 类型      | 必填 | 说明                         |
|-----------------|-----------|------|------------------------------|
| query           | string    | 是   | 当前用户问题，1—4000 字符    |
| conversation_id | UUID/null | 否   | 已有会话 ID；首次请求传 null |

前端不得自行传递完整历史消息作为可信会话上下文。后端负责创建、维护和读取会话历史。

### 5.3 统一响应结构

``` json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "answered",
  "answer": "根据已核验资料……",
  "answer_mode": "current_policy",
  "clarifying_question": null,
  "citations": [],
  "warnings": [],
  "created_at": "2026-11-23T00:00:00Z"
}
```

继续使用原有状态枚举：

| status                | 含义         |
|-----------------------|--------------|
| answered              | 已形成回答   |
| needs_clarification   | 需要补充信息 |
| insufficient_evidence | 证据不足     |

继续使用原有回答模式：

| answer_mode         | 含义         |
|---------------------|--------------|
| current_policy      | 当前政策     |
| historical          | 历史政策     |
| procedure_reference | 办理流程参考 |
| insufficient_data   | 资料不足     |

响应约束：

- `answered`：`answer` 非空，`answer_mode` 必须明确。
- `needs_clarification`：`answer` 为 null，`answer_mode` 为 null，`clarifying_question` 非空，`citations` 为空。
- `insufficient_evidence`：`answer_mode` 为 `insufficient_data`，必须说明证据不足原因，`citations` 为空。
- `citations` 只能包含本次回答实际使用的来源。
- `warnings` 用于说明限制、资料缺口和部分问题未能确认的情况。
- 不得为适配前端而擅自新增状态值或改变现有字段含义。

## 六、后端与 Agent 接口

保持 Alpha 已有接口：

``` python
async def run(request: AgentRequest) -> AgentResult:
    ...
```

### 6.1 AgentRequest

``` python
class AgentRequest(ContractModel):
    request_id: UUID
    conversation_id: UUID
    query: str
    history: list[ConversationTurn]
```

`history` 由后端会话管理器注入。

Agent 不负责生成 `request_id` 和 `conversation_id`，也不直接构造 HTTP Response。

### 6.2 AgentResult

``` python
class AgentResult(ContractModel):
    status: AnswerStatus
    answer: str | None = None
    answer_mode: AnswerMode | None = None
    clarifying_question: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
```

实际实现继续使用 `Field(default_factory=list)`，不得直接使用可变列表作为默认值。

Agent 必须保证返回对象符合公共模型，不能返回字符串、随意字典或自定义不透明对象。

## 七、Agent 与业务规则接口

### 7.1 追问规则

保留现有接口：

``` python
def alpha_clarification_rule(
    request: AgentRequest
) -> str | None:
    ...
```

规则：

- 返回非空字符串：表示需要向用户追问。
- 返回 None：表示用户信息满足当前规则要求。
- 每轮最多返回一个问题。
- 只追问用户侧缺失的信息。
- 资料本身缺失时，不能通过追问掩盖问题。
- 优先使用本轮用户明确提供的信息，历史信息只用于补齐本轮缺失字段。
- S1—S4 均应纳入场景识别和必要信息检查。
- 对 S4，只有当资源类型、适用对象或查询范围确实影响结果时才追问，不为追问而追问。

### 7.2 证据适用性判断

保留现有接口：

``` python
def alpha_evidence_check(
    request: AgentRequest,
    chunk: RetrievedChunk
) -> bool:
    ...
```

规则：

- True：允许当前片段进入后续回答流程。
- False：拒绝当前片段。
- 发生异常时必须拒绝，不允许默认放行。
- 不允许使用模型生成的判断代替人工审核状态检查。
- S4 资源信息同样必须经过来源核验、适用范围和时效检查。

### 7.3 元数据绑定

业务规则需要读取 Retriever 中的文档元数据和章节定位。

统一使用工厂函数：

``` python
evidence_check = build_from_retriever(
    retriever,
    today=today
)
```

要求：

1.  metadata 查询与 parsed chunk 查询来自同一个 Retriever 实例。
2.  使用闭包绑定，不使用模块级全局变量保存当前 Retriever。
3.  元数据和章节信息均采用只读方式。
4.  不存在或无法读取的元数据一律按不适用处理。

不得为了接入业务规则而修改 `RetrievedChunk` 的既有公共字段。

### 7.4 S4 规则接入

- S4 规则由业务规则负责人实现，并纳入现有业务规则模块。
- S4 的官方资源信息应能识别资源类别、适用对象和来源。
- 对来源不明、适用对象不清或时效无法确认的资源，不得给出确定性结论。
- 不得把实验室历史介绍、往年报名通知直接描述为当前仍在招募。
- S4 不新增学生端 HTTP 路径；通过现有 `/api/v1/ask` 入口完成问答。

## 八、Agent 与 Retriever 接口

Beta 阶段以现有 `LocalBM25Retriever` 为正式检索实现和验收基线。

### 8.1 检索接口

保留：

``` python
async def retrieve(
    request: RetrievalRequest
) -> list[RetrievedChunk]:
    ...
```

`RetrievalRequest`：

``` python
class RetrievalRequest(ContractModel):
    query: str
    top_k: int = 5
    business_direction_code: str | None = None
    category_name: str | None = None
```

要求：

- `top_k` 范围为 1—20。
- 没有符合条件的结果时返回空列表。
- 正式问答只能返回 `retrieval_status=enabled` 的片段。
- `score` 仅用于排序，不代表概率或置信度。
- 不确定业务方向时允许不传 `business_direction_code`，进行全库检索。
- 多业务方向问题不得因为错误的单一分类而漏掉必要证据。
- S1—S4 均使用统一 Retriever，不为 S4 单独绕过检索接口。
- 检索结果仍需经过 Agent 业务规则和证据门禁，BM25 命中不等于资料可用。

### 8.2 新增元数据查询接口

``` python
def get_document_metadata(
    version_id: UUID
) -> DocumentMetadata | None:
    ...
```

用途：根据版本 ID 获取文档完整元数据。

必须能够读取：

- `record_code`
- `version_no`
- `applicability_raw`
- `deadline_on`
- `temporal_notes`
- `source_verification_status`
- `timeliness_verification_status`
- `retrieval_status`

### 8.3 新增章节查询接口

``` python
def get_parsed_chunk(
    chunk_id: UUID
) -> ParsedChunk | None:
    ...
```

用途：获取知识片段的完整解析信息，包括：

- `content`
- `locator`
- `locator_note`
- `original_locator`
- `source_file_key`
- `chunk_no`

要求：

- 返回深拷贝，不允许外部直接修改索引内部数据。
- 未知、未开放或不存在的片段返回 None。
- 不能通过查询方法绕过检索开放状态。

### 8.4 Retriever 最终 Protocol

公共协议为：

``` python
class Retriever(Protocol):

    async def retrieve(
        self,
        request: RetrievalRequest
    ) -> list[RetrievedChunk]:
        ...

    def get_document_metadata(
        self,
        version_id: UUID
    ) -> DocumentMetadata | None:
        ...

    def get_parsed_chunk(
        self,
        chunk_id: UUID
    ) -> ParsedChunk | None:
        ...
```

当前 `LocalBM25Retriever` 已实现这三个方法，因此主要工作是将其正式纳入公共 Protocol，并补齐契约测试。

### 8.5 Beta 检索技术范围

本轮正式验收以 BM25 为准：

- 必须验证四个业务场景的检索结果。
- 必须验证片段与原始资料、标题、来源、版本和定位信息的一致性。
- 必须验证未审核、未开放或无效资料不能进入正式问答。
- 不要求本轮将 BM25 替换为 Embedding、Chroma 或 RRF 混合检索。
- 不得将开题 PPT 中的候选技术路线描述为已经实现或 Beta 必须交付的能力。

Embedding、Chroma、RRF 可作为后续优化方向，是否实施由后续阶段另行评估。

## 九、历史政策与时效处理

这是 Beta 阶段必须重点修复的工作流问题。

### 9.1 基本原则

历史资料不等于无效证据。

如果某份正式审核资料真实有效，只是对应年度的办理周期已经结束，仍然可以回答历史情况，但必须标记为 `historical`。

历史资料可以用于回答历史问题，但不能作为现行政策或当前办理依据。

### 9.2 处理规则

| 资料情况                        | 处理方式                     |
|---------------------------------|------------------------------|
| 当前有效的通用政策              | `current_policy`             |
| 当前正在办理的年度通知及流程    | `procedure_reference`        |
| 已结束的年度通知                | `historical`                 |
| 已被新版本替代的旧政策          | `historical`，并说明已被替代 |
| 无法确认是否为现行版本          | `insufficient_data`          |
| 来源未核验                      | 拒绝使用                     |
| `retrieval_status` 不为 enabled | 拒绝使用                     |
| 年度不匹配                      | 按业务规则拒绝或追问         |

### 9.3 证据门禁

所有回答模式都必须满足：

1.  `retrieval_status=enabled`。
2.  `source_verification_status=verified`。
3.  人工审核标记严格为 true。
4.  已有发布日期和生效日期不得在未来。
5.  文档版本和片段身份必须一致。
6.  适用范围和时效信息必须足以支撑当前回答。

对于当前政策，只允许使用满足当前时效要求的证据。

对于历史问题，允许使用已明确标记的 `historical`、`superseded` 或 `expired` 资料，但必须经过业务规则判断，且不得将其作为现行政策使用。

以下状态不能放行：

- `pending`
- `uncertain`
- `failed`
- `blocked`
- `review_only`

如果必要元数据缺失，导致无法确认来源、适用范围、审核状态或时效，应拒绝将该资料作为正式证据。

### 9.4 必须修改的现有工作流

当前 `AgentWorkflow` 的 `_eligible()` 只接受 `TimelinessVerificationStatus.CURRENT`，并且对历史年度问题有提前拒绝逻辑。

这与 `business-rules.md` 中已经制定的历史政策处理规则不一致。

Beta 必须调整工作流，使其根据问题时间范围和业务规则选择允许的证据，而不是简单地拒绝所有历史资料。

不得仅修改一个状态判断就宣称历史政策功能完成，必须通过真实资料结构及自动化测试验证。

## 十、文档解析与索引接口

### 10.1 文档解析

保持：

``` python
def parse_document(
    file_path: Path,
    metadata: DocumentMetadata
) -> DocumentPackage:
    ...
```

返回结构：

``` python
class DocumentPackage(ContractModel):
    metadata: DocumentMetadata
    files: list[ParsedFile]
    chunks: list[ParsedChunk]
```

约束：

- `storage_key` 必须是受控资料目录下的相对路径。
- 必须保留原始文件信息及 SHA-256。
- 每个片段必须能定位到来源文件。
- Markdown/TXT 为当前已实现的解析范围。
- PDF/OCR 尚未可靠解析时，不得生成伪造正文片段。
- 解析成功不代表人工审核通过。

解析结果默认：

``` python
retrieval_status = RetrievalStatus.BLOCKED
```

### 10.2 XLSX 资料处理约定

Beta 任务书要求核验青禾计划实验室需求 XLSX 附件。本轮采用资料提取和格式转换方式，不新增通用 XLSX 解析接口。

处理流程：

1.  保留原始 XLSX 文件，不得只保留转换后的文本。
2.  由资料负责人使用人工检查或本地工具提取表格内容。
3.  将核验后的有效内容整理为 Markdown/TXT，供现有解析流程处理。
4.  保留原始文件名、来源、必要的文件校验信息及转换说明，确保转换后的内容能够追溯到原始 XLSX。
5.  核对表格行列、合并单元格及关键字段，避免转换过程中丢失适用对象、联系方式、报名条件等信息。
6.  对实验室名称、研究方向、联系方式、适用对象和报名流程进行来源核验。
7.  转换或解析成功不代表资料已经通过人工审核。

**禁止：** 将 XLSX 直接描述为当前 `DocumentParser` 已支持的原生解析格式；不得为了完成本项任务擅自修改公共 `parse_document` 接口。

### 10.3 知识索引

保持：

``` python
async def index_document(
    package: DocumentPackage
) -> IndexResult:
    ...
```

返回：

``` python
class IndexResult(ContractModel):
    document_id: UUID
    version_id: UUID
    status: IndexingStatus
    chunk_count: int
    indexed_count: int
    warnings: list[WarningItem]
```

状态：

- `indexed`
- `partial`
- `failed`

索引成功不等于允许正式问答检索。人工审核及资料开放必须通过独立流程完成。

### 10.4 正式资料审核与开放

资料至少区分以下阶段：

| 阶段          | 含义                                       | 是否允许正式问答   |
|---------------|--------------------------------------------|--------------------|
| `processing/` | 待整理、待核验资料                         | 否                 |
| `processed/`  | 已完成解析或技术处理，仍需审核             | 否                 |
| `approved/`   | 完成来源、适用范围、时效核验及最终人工审核 | 满足开放条件后允许 |

实际目录以仓库现有结构为准，不得由成员另建一套互不兼容的正式资料目录。

项目负责人负责最终人工审核。合成测试资料、待审核资料不得冒充正式政策资料。

## 十一、Agent 与 Qwen 接口

保持原有接口：

``` python
async def generate(
    request: LLMGenerateRequest
) -> LLMResult:
    ...
```

请求：

``` python
class LLMGenerateRequest(ContractModel):
    messages: list[LLMMessage]
    temperature: float = 0.2
    max_tokens: int = 1024
```

响应：

``` python
class LLMResult(ContractModel):
    content: str
    model: str
    usage: dict[str, int] | None = None
```

### 11.1 基本要求

1.  Agent 不直接依赖 Qwen SDK。
2.  模型 API Key 只能从环境变量读取。
3.  模型调用失败必须转换为统一 `ServiceError`。
4.  模型生成内容必须经过校验。
5.  模型不能自行创建 `Citation`。
6.  `Citation` 必须来自本次检索并通过证据门禁的片段。
7.  不得将未通过门禁的资料放入模型上下文。
8.  不得把模型的常识补充或无来源推断作为正式政策结论。

### 11.2 Beta 回答生成策略：受约束的自然语言生成

Beta 采用受约束的自然语言生成，不直接接受无约束的自由文本作为政策答案。

Agent 的处理顺序：

1.  接收用户问题并完成必要的场景识别和追问。
2.  调用 Retriever 获取候选片段。
3.  对候选片段执行来源、审核、时效和适用范围检查。
4.  只将通过证据门禁的片段提供给 Qwen。
5.  Agent 为本次请求中的可用证据分配临时 `evidence_id`，并保存其与真实 `RetrievedChunk` 的映射。
6.  Qwen 根据用户问题和给定证据生成自然语言答案。
7.  Qwen 返回的 `evidence_id` 由 Agent 校验，并映射回真实证据。
8.  Agent 根据真实检索片段构造 `Citation`，再生成 `AgentResult`。

### 11.3 模型内部输出格式

Beta 回答生成路径要求模型以严格 JSON 内容返回，不使用 Markdown 代码围栏：

``` json
{
  "answer": "基于已提供证据形成的自然语言回答。",
  "used_evidence_ids": ["E1", "E2"]
}
```

字段说明：

| 字段                | 类型       | 说明                          |
|---------------------|------------|-------------------------------|
| `answer`            | string     | 基于已提供证据生成的回答      |
| `used_evidence_ids` | string\[\] | 本次回答实际使用的临时证据 ID |

约束：

- `evidence_id` 由 Agent 在当前请求内分配，不是数据库业务方向代码，也不是新的公共 HTTP 字段。
- 模型只能返回本次提示中提供的 `evidence_id`。
- 模型不得自行填写来源 URL、文件名、发布日期或 `Citation` 对象。
- Agent 必须验证 JSON 格式、答案非空、证据 ID 存在且属于本次通过门禁的证据集合。
- Agent 根据证据 ID 映射到真实 `RetrievedChunk`，再由自身构造引用。
- 不存在的 ID、空答案、非法 JSON 或没有可用证据 ID 时，不得直接返回模型生成内容。
- 若无法通过安全校验，应按既有安全回退策略处理；无法形成可靠答案时返回 `insufficient_evidence`。
- 证据 ID 校验只能证明引用指向真实片段，不能单独证明回答中的每项事实都被原文支持。测试仍须检查答案与原文是否一致，不能宣称仅凭 ID 校验即可消除幻觉。

该约定属于 Agent 与 Qwen 之间的内部调用协议，不改变 `LLMGenerateRequest`、`LLMResult` 或学生端 HTTP 响应结构。

### 11.4 模型失败与引用安全

- 超时、限流、鉴权失败等错误必须转换为统一 `ServiceError`。
- 模型输出格式错误不得被当作正常答案。
- 不存在的引用 ID 不得进入最终回答。
- 引用原文必须来自真实检索片段，不得由模型改写后冒充原文。
- 如果证据只能支持部分问题，回答必须明确限定范围，不得扩展为确定性结论。
- 无可靠证据时，应明确说明无法确认。

## 十二、多轮会话

由后端统一维护会话。

当前接口：

``` python
class ConversationAgentService:

    async def run(
        self,
        request: AgentRequest
    ) -> AgentResult:
        ...
```

当前实现采用 `InMemoryConversationStore`。

Beta 暂时沿用：

| 配置           |  默认值 |
|----------------|--------:|
| 最大历史消息数 |      12 |
| 历史字符限制   |    6000 |
| 最大会话数     |    1000 |
| 空闲过期时间   | 3600 秒 |

要求：

- 每个 `conversation_id` 的历史相互隔离。
- 每次请求只读取当前会话历史。
- 尽可能保留完整的用户—助手轮次。
- 新会话不继承旧会话内容。
- 历史消息只用于补齐当前问题必要的信息。
- 本轮明确更换事项时，不得让旧事项污染当前场景识别。
- 前端只传 `conversation_id`，不得将客户端自行拼接的历史消息作为可信上下文。

当前会话存储仅为内存实现，不具备跨进程持久化能力。Beta 单进程本地运行可以继续使用，后续部署多实例时需要另行设计共享存储。

**Beta 不要求增加 PostgreSQL 会话持久化，也不要求为此改变现有会话接口。**

## 十三、统一错误处理

所有 HTTP 错误使用：

``` json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": {
    "code": "MODEL_TIMEOUT",
    "message": "模型服务响应超时，请稍后重试。",
    "retryable": true
  }
}
```

主要错误码：

| 错误码                       | HTTP 状态 | 含义         |
|------------------------------|----------:|--------------|
| `INVALID_REQUEST`            |       400 | 请求参数错误 |
| `RESOURCE_NOT_FOUND`         |       404 | 资源不存在   |
| `MODEL_TIMEOUT`              |       504 | 模型超时     |
| `MODEL_UNAVAILABLE`          |       503 | 模型不可用   |
| `RATE_LIMITED`               |       429 | 模型限流     |
| `KNOWLEDGE_BASE_UNAVAILABLE` |       503 | 知识库不可用 |
| `SERVICE_NOT_CONFIGURED`     |       503 | 服务未配置   |
| `INTERNAL_ERROR`             |       500 | 内部异常     |

业务层证据不足属于正常问答结果：

``` text
HTTP 200
status = insufficient_evidence
answer_mode = insufficient_data
```

不得把正常的证据不足当成服务器内部错误。

不得向前端返回密钥、堆栈、数据库连接串及服务器绝对路径。

## 十四、当前实现边界与 Beta 范围

以下内容必须区分已实现和待实现，不得仅凭接口定义宣称已经完成。

| 能力                | Alpha 当前状态         | Beta 要求                                 |
|---------------------|------------------------|-------------------------------------------|
| FastAPI 问答入口    | 已实现                 | 保持兼容                                  |
| Qwen 适配           | 已实现                 | 保持统一协议，完成受约束回答生成          |
| AgentWorkflow       | 已实现                 | 补齐历史政策处理和 S4 接入                |
| 多轮会话            | 内存实现               | 保持隔离和有界管理                        |
| BM25 检索           | 已实现                 | 作为正式验收基线，补齐 Protocol           |
| 元数据查询          | 已实现                 | 正式纳入公共接口                          |
| 章节查询            | 已实现                 | 正式纳入公共接口                          |
| 业务规则 S1—S3      | 已实现                 | 补齐工作流对齐                            |
| 业务规则 S4         | 尚待补齐               | Beta 新增并验收                           |
| Markdown/TXT 解析   | 已实现                 | 保持统一入库格式                          |
| XLSX 解析           | 未作为通用解析接口实现 | 提取后转 Markdown/TXT，不新增公共解析接口 |
| PDF/OCR             | 尚未完整实现           | 不得伪造解析结果                          |
| PostgreSQL 在线接入 | 尚未完成               | 不要求本轮完成                            |
| Chroma/RRF 混合检索 | 尚未完成               | 不强制替换当前 BM25                       |
| Embedding 检索      | 非 Beta 验收基线       | 不要求本轮完成                            |
| Tavily 联网检索     | PPT 中的候选方案       | 不列入 Beta 必做范围                      |
| 后台管理 HTTP API   | 尚未完整实现           | 不要求完整后端 API                        |
| 管理端认证授权      | 尚未完成               | 不得公网开放未受保护的管理入口            |
| ESP32 终端          | 可选拓展               | 不纳入 Beta                               |

## 十五、Beta 接口验收标准

所有模块必须至少满足以下测试要求。

### 15.1 公共契约

- Pydantic 模型校验正常。
- 非法字段能够被拒绝。
- UUID、日期、枚举值符合规范。
- `AgentResult` 三种状态结构正确。
- 学生端 HTTP 路径和响应字段保持兼容。

### 15.2 Agent 与业务规则

- S1—S4 均能识别对应问题。
- 信息不足时能够正确追问。
- 每轮最多追问一个问题。
- 追问时不调用 Retriever 和 Qwen。
- 资料不足时直接返回证据不足。
- 历史信息可以补齐本轮缺失条件。
- 新主题不会被历史主题污染。
- S4 不能把历史实验室通知描述为当前招募信息。
- 规则异常时按失败关闭处理。

### 15.3 Agent 与 Retriever

- `retrieve` 正常返回 `RetrievedChunk`。
- 无命中返回空列表。
- 元数据查询返回正确版本。
- 章节查询返回正确片段。
- 不同 Retriever 实例之间不存在元数据串用。
- 不符合开放和核验条件的资料不能进入回答。
- 多业务方向问题不会因错误的单一分类过滤而漏掉必要证据。
- BM25 检索结果能够回溯到原始资料和章节定位。

### 15.4 历史政策

- 当前政策可以正常回答。
- 已结束的年度通知可以作为历史信息回答。
- 已废止政策不能冒充当前政策。
- 未来年度没有资料时返回证据不足。
- 历史回答必须明确标记年份和失效情况。
- 用户没有说明年度且年度会影响结论时，能够主动追问。
- 历史资料必须通过来源核验、人工审核和适用性检查。

### 15.5 Qwen 模型适配与回答生成

- 正常模型响应。
- 模型超时。
- 模型限流。
- 模型鉴权失败。
- 非法 JSON。
- 输出缺少 `answer`。
- 输出缺少或包含空的 `used_evidence_ids`。
- 不存在的证据 ID。
- 证据 ID 属于其他请求或不在本次证据集合中。
- 引用原文与检索原文不一致。
- 模型试图引用未审核或未开放资料。
- 回答包含证据无法支持的确定性结论。

所有非法引用均不得进入最终回答。真实 Qwen 测试必须与 Mock 测试分别记录。

### 15.6 前后端联调

- 健康检查正常。
- 新建会话正常。
- 连续追问正常。
- 新建会话不继承旧历史。
- 三种问答状态正确展示。
- 引用与警告正常展示。
- 历史政策提示正常展示。
- S4 学院资源类回答正常展示。
- HTTP 错误能够显示统一错误信息。
- 学生端仍通过同一个正式 API 完成四大场景问答。

### 15.7 正式资料与验收证据

- 正式资料均有可追溯来源。
- 资料适用范围和时效信息有核验记录。
- 正式资料进入 `approved/` 前有项目负责人最终审核记录。
- 合成测试资料与正式政策资料明确区分。
- 检索命中结果能够与原文对应。
- 保留自动化测试结果、真实模型调用记录及必要运行日志。

## 十六、接口变更及 PR 规则

1.  公共接口由组长统一维护。
2.  修改公共模型前必须先提出变更申请。
3.  不允许成员自行修改其他模块的公共接口。
4.  每个模块通过独立 PR 提交。
5.  PR 必须说明修改的接口、影响范围、兼容性和测试结果。
6.  公共模型修改必须同步检查前端 TypeScript 类型。
7.  不允许通过删除测试、降低校验标准或 Mock 正式业务逻辑来使测试通过。
8.  涉及真实政策资料的正向测试必须明确区分正式审核资料和合成测试资料。
9.  公共接口变更合并后，其他模块必须以 `main` 最新版本为准。
10. 不得把本规范中的内部模型输出约定擅自扩展为学生端 HTTP 字段。
11. 发现规范与现有代码不一致时，先向组长提交差异说明，不得直接按个人理解重构公共接口。

### 16.1 PR 必须包含

1.  修改目的。
2.  修改文件。
3.  完成的功能。
4.  上下游依赖。
5.  实际运行的测试命令。
6.  测试结果。
7.  尚未完成的事项。
8.  必要的截图、日志或其他证据。

### 16.2 分支与协作

所有成员必须从最新 `main` 分支创建自己的开发分支。

建议分支名称：

| 成员   | 分支名称                        |
| ------ | ------------------------------- |
| 丁晓炜 | `feat/beta-policy-review`       |
| 王智洋 | `feat/beta-corpus-retrieval`    |
| 雷葭雨 | `feat/beta-business-rules`      |
| 吴诗莹 | `feat/beta-agent-history`       |
| 赵紫龙 | `feat/beta-runtime-stability`   |
| 颜俊宇 | `test/beta-e2e`                 |
| 洪添军 | `feat/beta-student-ui`          |
| 吴欣键 | `test/beta-browser-regression`  |
| 薛锦荣 | `docs/beta-windows-runtime`     |
| 林彦翔 | `docs/beta-resource-navigation` |
| 林世颖 | `docs/beta-architecture`        |

项目负责人负责统一集成和最终验收。

协作约束：

- 不直接向 `main` 推送代码。
- 未经协商不修改公共 API。
- 不覆盖其他成员已经完成的代码。
- 不用 Mock 测试代替真实集成测试。
- 不将未审核资料用于正式政策回答。
- 上游 PR 合并后，下游成员及时同步最新 `main`。
- 测试负责人可以提前编写测试用例，不必等全部功能合并后才开始工作。
- 架构文档可以先提交初稿，但最终版本必须与实际合并代码一致。

## 十七、Beta 阶段冻结决策

V2.1-Final 对 V2.0-Draft 中的待确认事项作如下处理：

| 编号 | 原待确认事项                           | V2.1-Final 决定                                                                               |
|------|----------------------------------------|-----------------------------------------------------------------------------------------------|
| D01  | 学院资源导航是否作为 Beta 独立业务场景 | **已确定：是。** 正式采用 S4，纳入业务规则、检索和 E2E 验收                                   |
| D02  | 数据库五大业务方向的正式 code 字典     | **规则已确定，具体值按仓库核对。** 不得自行创造代码；以正式字典、初始化数据或已合并代码为准   |
| D03  | 历史政策正向回答的完整验收范围         | **已确定：** 按第九章和第十五章执行                                                           |
| D04  | 是否要求模型生成自然语言综合回答       | **已确定：** Beta 采用受约束自然语言生成，按第十一章内部 JSON 输出约定执行；引用由 Agent 构造 |
| D05  | 后台管理 HTTP API 是否纳入 Beta        | **已确定：否。** 不要求完整管理端后端 API                                                     |
| D06  | 是否增加会话持久化                     | **已确定：否。** 继续使用 InMemoryConversationStore，支持单进程本机运行                       |
| D07  | 是否要求 Chroma/RRF/Embedding          | **已确定：否。** BM25 为 Beta 正式验收基线                                                    |
| D08  | XLSX 附件如何进入知识库                | **已确定：** 提取后转 Markdown/TXT，保留原始文件及来源追溯，不新增通用解析接口                |
| D09  | 正式资料由谁最终审核                   | **已确定：** 项目负责人罗宇泽负责最终人工审核                                                 |

D02 的具体代码值属于对现有数据库字典的核对工作，不是允许成员自行设计新代码的开放事项。未核对清楚前不得猜测或提交虚构代码。

## 十八、规范生效与版本管理

1.  本规范 V2.1-Final 替代 V2.0-Draft，作为 Beta 阶段统一接口与技术范围依据。
2.  所有模块负责人应以本规范和 Beta 冲刺任务书为共同依据。
3.  本规范与仓库实际公共模型存在差异时，必须先由项目负责人核对并统一修订，不能由成员各自选择版本。
4.  后续确需修改公共字段、HTTP 路径、状态枚举或 Protocol 时，应由项目负责人发布新的规范版本，并通知所有受影响成员。
5.  文档版本号与 HTTP API 版本相互独立。

------------------------------------------------------------------------

**规范负责人：罗宇泽**  
**文档版本：V2.1-Final**  
**适用阶段：CodeMind-FZU Beta 冲刺**  
**统一原则：以仓库最新 `main`、本规范和正式审核资料为准。**
