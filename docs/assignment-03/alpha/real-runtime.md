# Alpha FastAPI 真实运行组装

日期：2026-11-19
分支：`feat/alpha-real-runtime`
基线：`origin/main` `f5fcabc`

## 1. 当前接口确认

直接复用最新 `main` 上的既有模块，不修改 AgentWorkflow、Retriever 或公共 HTTP 契约：

| 模块 | 构造与调用 |
|---|---|
| `AgentWorkflow` | `AgentWorkflow(retriever, llm_client, clarification_rule=..., evidence_check=...)` |
| Agent 调用 | `await workflow.run(AgentRequest) -> AgentResult` |
| `LocalBM25Retriever` | `LocalBM25Retriever(file_root=repo_root)`，逐个 `await index_document(package)`，再 `await retrieve(request)` |
| `QwenLLMClient` | `create_qwen_client_from_env()`，实现 `await generate(LLMGenerateRequest) -> LLMResult` |
| HTTP 适配 | FastAPI 将 `AgentResult` 的三种状态包装为既有 `AskResponse` |

`QwenLLMClient` 的 `ServiceError` 由工作流原样上抛，FastAPI 返回统一错误 envelope。超时、限流、上游不可用或认证失败不会被转换成 `answered`。

## 2. 组装结构

`backend/services/alpha_runtime.py` 负责：

1. 只调用 #35 的 `load_approved_alpha_retriever()`，由其执行 manifest、路径安全、人工审核标记和资料包发现；
2. 要求 manifest（如存在）与 `temporal_notes["human_approved"]` 都是严格布尔 `true`；
3. 使用仓库根目录作为 `file_root`，核对加载报告中的非空包列表、片段总数、全部 `IndexingStatus.INDEXED` 和无 warnings；
4. 业务规则使用 #36 的 `build_from_retriever(retriever)` 绑定当前 Retriever 的元数据与片段查询；
5. 初始化 Qwen 客户端和 #32 提供时的 `create_alpha_workflow()`，旧 main 期间使用同签名的 `AgentWorkflow`；
6. 用 `InMemoryConversationStore` 和 `ConversationAgentService` 管理会话。

`backend/app/alpha.py` 使用 FastAPI lifespan 异步完成上述组装，不在模块导入时运行嵌套事件循环。知识库或模型配置失败时，应用仍可启动并提供健康检查；问答返回脱敏的 503，不会切换到 Raw/Mock 资料。

## 3. 服务端会话

- 以 `conversation_id` 保存此前的用户和 Agent 消息；
- 每个会话使用独立 `asyncio.Lock`，同一会话的并发请求串行执行，后一个请求能看到前一个成功轮次；
- 不同 `conversation_id` 使用不同状态，不共享历史；
- 默认最多保留 12 条消息，并按 6000 字符预算从最早的完整问答对开始裁剪；
- 奇数的 `CONVERSATION_MAX_MESSAGES` 会向下取整，保持用户/助手消息成对；
- 只保存成功返回的 `AgentResult`；模型、检索或工作流异常不写入失败轮次；
- 后台按空闲时间和会话数量上限清理非活动状态，正在处理的会话不会被回收。

第一轮追问与第二轮补充信息会进入同一工作流。AgentWorkflow 只使用用户历史补齐必要字段，助手历史不会被当作政策证据。

## 4. 环境变量与启动

复制模板并只在本地填写密钥：

```powershell
Copy-Item backend\.env.example backend\.env
```

关键变量：

```env
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-flash
QWEN_TIMEOUT_SECONDS=28
QWEN_MAX_RETRIES=0
ALPHA_PACKAGE_DIR=knowledge_base/processed/alpha/approved
CONVERSATION_MAX_MESSAGES=12
CONVERSATION_HISTORY_CHAR_LIMIT=6000
CONVERSATION_MAX_COUNT=1000
CONVERSATION_IDLE_SECONDS=3600
CONVERSATION_CLEANUP_INTERVAL_SECONDS=300
```

从仓库根目录启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.alpha:app --port 8000 --env-file backend/.env
```

Mock 入口保持不变：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.dev:app --port 8000
```

## 5. 测试层次与当前结论

| 层次 | 使用的真实组件 | 替身或限制 |
|---|---|---|
| 运行组装 API 测试 | FastAPI、lifespan、#35 审核资料加载器、BM25、AgentWorkflow、Citation 校验 | 合成 `example.invalid` 资料包和证据选择 LLM 替身 |
| 多轮与隔离测试 | 内存会话、AgentService 调用链 | Agent 使用记录型替身 |
| Qwen 适配器测试 | `QwenLLMClient` 请求/响应与异常映射 | `httpx.MockTransport`，不是付费联网调用 |
| 真实正式资料 | 当前无人工签核 `enabled` 包 | 正确返回知识库未就绪或证据不足 |

因此，以下结论明确不能混写：

- 自动化测试通过的是运行组装、检索、会话和证据校验；
- `QWEN_API_KEY` 未配置时，真实 Qwen 联网调用没有执行；
- 当前 `approved/` 尚未包含正式资料，不能宣称竞赛、奖学金或推免政策正向回答已经验收；
- 合成测试夹具不属于正式知识库，也不应复制到 `approved/`。

## 6. 复跑命令

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_backend_runtime tests.test_agent_workflow_api -v
```

当前通过项覆盖：

- Alpha lifespan 使用真实 BM25 和 AgentWorkflow；
- `/api/v1/ask` 返回带可追溯 Citation 的 `answered`；
- 追问后的第二轮使用此前用户消息；
- 不同 `conversation_id` 隔离；
- 同一 `conversation_id` 并发请求串行更新；
- 历史条数与字符预算限制；
- 知识库目录缺失、模型超时、非法参数和 Agent 异常的错误响应。
- 未人工审核、部分索引或带 warnings 的资料包失败关闭；
- `build_from_retriever()` 绑定当前 Retriever，业务拒绝时零模型调用；
- 奇数消息上限归一化、LRU 数量上限、空闲清理与活动会话保护。

第二轮审核对应的 #32/#36 临时集成版本、全量结果和上游测试口径冲突见
[运行时上游集成复核](evidence/runtime-upstream-review.md)。

## 7. 待上游交付

- 丁晓炜完成人工签核，并提供 `knowledge_base/processed/alpha/approved/` 下的正式 `enabled` 包；
- 王智洋确认正式包的最终加载与索引边界；
- 吴诗莹确认业务规则模块合入后的两个回调签名；
- 配置本地真实 `QWEN_API_KEY` 后执行一次正向联网调用，并单独记录模型、延迟、请求时间与响应状态；
- 薛锦荣将 `backend.app.alpha:app` 启动方式同步到统一环境文档。
