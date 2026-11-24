# Beta 后端运行稳定性与 Qwen 适配

日期：2026-11-24
分支：`feat/beta-runtime-stability`
基线：`origin/main` `5973eef`

## 1. 交付范围

本轮只修改后端运行与模型适配范围：

- `backend/app/alpha.py`
- `backend/services/alpha_runtime.py`
- `backend/services/qwen_client.py`
- `backend/app/main.py`
- `backend/services/errors.py`
- `backend/app/config.py`（保持现有 Beta 会话配置）
- `tests/test_backend_runtime.py`
- `tests/test_qwen_client.py`

未修改公共 Pydantic 模型、Protocol、学生端 HTTP 路径、AgentWorkflow、Retriever 或业务规则。经组长批准，本轮只统一 V2.1-Final 已规定的两项 HTTP 错误状态。

## 2. Runtime 行为

`backend.app.alpha:app` 使用 FastAPI lifespan：

1. 通过 #35 `load_approved_alpha_retriever()` 加载人工审核资料。
2. 通过 #36 `build_from_retriever(retriever)` 绑定业务规则。
3. 通过 #32 `create_alpha_workflow()` 创建工作流。
4. 将工作流包装为 `ConversationAgentService`。
5. 应用关闭时取消会话清理任务并关闭 Qwen 适配器自有连接。

知识库、业务规则或 Qwen 配置失败时，健康检查仍可用，问答返回统一 503 错误，不会加载待审核资料或返回 Mock 答案。

## 3. 重试预算语义

`maximum_call_budget_seconds = (max_retries + 1) * timeout_seconds + backoff`
是依据配置计算的理论调用预算，用于在 Runtime 组装阶段提前发现明显超出
AgentWorkflow 单阶段时限的组合。

该值不是单次网络请求的严格实际耗时上界：`httpx.Timeout` 约束的是连接、
读取等 HTTP 操作，而不是整次请求的墙钟总时限。正式运行时的实际阶段总时限由
`AgentWorkflow` 内的 `asyncio.wait_for()` 控制。

## 4. Qwen 适配器

`QwenLLMClient.generate(LLMGenerateRequest) -> LLMResult` 保持公共协议不变。

本轮修复：

- 适配器自有 `httpx.AsyncClient` 首次调用创建并复用，避免每次请求重复建连。
- 调用方注入的 HTTP client 仍归调用方所有，`AlphaRuntime.close()` 不会将其永久关闭。
- 模型内容不再在适配器内做额外裁剪；内部换行和 JSON 结构完整交给 Agent。
- 适配器不解析 `answer` / `used_evidence_ids`，不创建 Citation；这些由 AgentWorkflow 负责。
- 非有限超时值 `nan`/`inf` 在配置阶段拒绝。
- usage 只保留非负整数，拒绝 bool、字符串和负数。
- 超时、连接失败、限流、鉴权失败、5xx、非法/空响应继续映射为统一 `ServiceError`。

## 5. 会话管理

继续使用 `InMemoryConversationStore`：

- 默认最大消息数 12；
- 历史字符预算 6000；
- 最大会话数 1000；
- 空闲过期 3600 秒；
- 同一 `conversation_id` 请求串行，失败轮次不写入历史；
- 不同会话严格隔离；
- 后台清理不会删除正在执行的轮次。

## 6. 测试结果

全量：

```text
Python 3.14.4:
449 passed, 28 skipped, 1 warning, 154 subtests passed

Python 3.10.11:
449 passed, 28 skipped, 1 warning, 154 subtests passed
```

定向 Runtime、Qwen、API、Agent-Qwen、Retriever 和业务规则：

```text
Python 3.14.4: 306 passed, 26 skipped, 1 warning, 66 subtests passed
Python 3.10.11: 306 passed, 26 skipped, 1 warning, 66 subtests passed
```

原始记录见 [runtime-tests.txt](evidence/runtime-tests.txt)，完整标准输出见
[Python 3.14](evidence/runtime-pytest-py314.txt) 和
[Python 3.10.11](evidence/runtime-pytest-py310.txt)。

最新 main `5973eef` 的 Beta 上游专项测试结果：

```text
Ran 25 tests
OK
```

记录见 [upstream-integration.txt](evidence/upstream-integration.txt) 和
[upstream-integration.json](evidence/upstream-integration.json)。原 Alpha
验收档案保留在 `docs/assignment-03/alpha/evidence/agent-integration/`，未由
Beta 回归覆盖。

覆盖：

- 无 API Key 时健康检查 200、问答 503；
- 超时和 Python 3.10 `asyncio.TimeoutError`；
- 鉴权、限流、网络失败、非法模型 envelope；
- JSON 内容完整传输且不在适配器内解析；
- 自有 HTTP client 复用与关闭；
- 外部 HTTP client 生命周期由调用方控制；
- 直接构造 Settings 时拒绝非有限/布尔超时和非法重试次数；
- Qwen 重试预算超过 AgentWorkflow 阶段超时时失败关闭；
- HTTP 400/503 最终口径及对应 OpenAPI 声明；
- 前端统一 envelope 错误处理和 TypeScript/Vite 生产构建；
- `check_qwen_live.py`、`check_qwen_runtime_live.py`、`run_alpha_agent.py` 在成功和异常路径均关闭客户端；
- 多轮历史、隔离、并发串行、数量与空闲清理；
- 未审核、部分索引和知识库缺失失败关闭；
- #45 业务规则、#51 Retriever 接口和已审核资料加载器的兼容性。

## 7. 真实 Qwen 验证拆分

按管理要求，本 PR 只承担第一阶段运行代码和离线契约测试，不包含真实模型调用证据。

真实 Qwen 受约束 JSON、Agent 联调和 HTTP 验收放在独立第二阶段分支，只有吴诗莹的 Beta Agent 集成验证完成后才具备合并条件。第一阶段使用 `httpx.MockTransport` 验证请求、响应和异常适配，不宣称真实模型已经验收。

## 8. 启动方式

正式资料：

```powershell
$env:ALPHA_PACKAGE_DIR='knowledge_base/processed/alpha/approved'
.\.venv\Scripts\python.exe -m uvicorn backend.app.alpha:app `
  --host 127.0.0.1 --port 8000 --env-file backend\.env
```

合成运行验收：

```powershell
$env:ALPHA_PACKAGE_DIR='tests/fixtures/alpha_approved'
.\.venv\Scripts\python.exe -m uvicorn backend.app.alpha:app `
  --host 127.0.0.1 --port 8000 --env-file backend\.env
```

合成夹具使用 `example.invalid`，只能用于技术验收，不能进入正式 `approved/`。

## 9. HTTP 错误码

经组长确认，统一以 Beta 接口规范 V2.1-Final 为准：

- `INVALID_REQUEST` 返回 HTTP 400；
- 非法或空模型响应映射为 `MODEL_UNAVAILABLE`，返回 HTTP 503；
- `RATE_LIMITED`、`MODEL_TIMEOUT`、`INTERNAL_ERROR` 等其他状态保持不变；
- `/api/v1/ask` OpenAPI 声明包含 400、429、500、503、504，不再生成旧版 422 声明。

前端统一通过错误响应 envelope 中的 `error.code`、`error.message` 和
`error.retryable` 处理失败，不依赖本轮发生变化的两个具体数字。

## 10. 待集成事项

- 第二阶段在吴诗莹 Beta Agent 合并后，使用真实 Qwen 复跑 `answer + used_evidence_ids` 的完整 `/api/v1/ask` 链路。
- 正式 `approved/` 仍无人工签核资料包，四领域正式政策正向验收等待资料放行。
- Windows 干净环境与文档由薛锦荣同步验证。
