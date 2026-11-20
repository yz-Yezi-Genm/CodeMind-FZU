# Agent 与后端/Qwen 接口对齐

> 2026-11-20更新：赵紫龙已提供真实短片段测试记录，qwen-flash/qwen-plus通过JSON及逐字匹配；这是上游报告，不是本Agent正式政策验收结果。联调模型改为qwen-flash（qwen-plus显式备选），28秒、0次重试。最新后端分支3606eda已修改其默认值，本工作分支的旧客户端文件未同步，故联调务必显式配置环境变量。当前不使用受限的qwen-turbo。

2026-11-19，依据赵紫龙提供的《后端与 Qwen 模块说明》及新发的《后端与 Qwen 接入补充说明》核对。客户端基础实现已在 main 中；正式运行组装在 `feat/alpha-real-runtime`，尚未合入本工作分支基线。本轮不修改赵紫龙维护的 `qwen_client.py`、`backend/app/main.py`、`alpha_runtime.py` 或公共契约。

## 已对齐的部分

- 调用协议：`await llm_client.generate(LLMGenerateRequest) -> LLMResult`。
- 默认客户端：`create_qwen_client_from_env()`；配置来自当前进程的 `QWEN_*` 环境变量。
- FastAPI 通过 `create_app(agent_service=workflow, llm_client=workflow.llm_client)` 注入，健康检查和问答路径不变。
- `ServiceError` 保留适配器给出的状态、错误码和 `retryable`。工作流等待模型超时转换为 `LLMTimeoutError`，取消向适配器传播。
- Qwen 不创建 Citation。Agent 校验模型选择后，从本轮合格 RetrievedChunk 构建 Citation。

新版补充说明已确认 Agent 路径为 `backend.services.agent_workflow`，构造时同时传入 Retriever 和 LLMClient；旧说明中的路径和参数示例差异已解决。

## 模型输出约定

本轮采用证据摘录，而不是自由生成政策结论。适配器仍只返回 `LLMResult.content` 字符串，字符串内容必须是下面的 JSON：

```json
{"evidence":[{"chunk_id":"本轮提供的UUID","quote":"该片段完整content"}]}
```

Agent 请求参数为 `temperature=0`、`max_tokens=8192`。无合适证据时输出 `{"evidence":[]}`；不要添加 Markdown 代码围栏、解释文字、标题、来源、金额推断或其他键。每个 quote 必须与对应片段的完整 content 逐字相等。只提供子串、改写原文、未知 chunk_id、重复引用或任一条引用错误，整轮都会拒答。

两种失败不能混淆：

| 情况 | HTTP / 业务结果 |
| --- | --- |
| Qwen HTTP 响应合法，但 content 为自由文本、错误选择 JSON 或伪造引用 | 200 + `insufficient_evidence`，无引用 |
| 供应商响应无法解析、choices 缺失、content 为空 | 502 + `MODEL_UNAVAILABLE` |
| 401/403 | 503 + `SERVICE_NOT_CONFIGURED` |
| 超时或工作流等待模型超时 | 504 + `MODEL_TIMEOUT` |
| 429 | 429 + `RATE_LIMITED` |
| 连接失败、连续 5xx | 503 + `MODEL_UNAVAILABLE` |
| 模型调用阶段发生未分类异常 | Agent 转为脱敏 `LLMUnavailableError`，503 |
| 其他阶段的普通未预期 Agent 异常 | 保留后端 500 + `INTERNAL_ERROR` 处理 |

模型阶段的未分类异常转换为 503 是当前 Agent 的行为，需要告知后端负责人；不影响已分类 ServiceError，也不代表整个 Agent 的 RuntimeError 都改为 503。

## 正式启动入口与本地排查工具

正式联调统一使用赵紫龙维护的 `backend.app.alpha:app`，由 `backend.services.alpha_runtime` 组装并注入 ConversationAgentService。以下命令要求该分支代码已在集成环境就绪：

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.alpha:app --port 8000 --env-file backend/.env
```

`backend/.env` 由账号持有人在本地配置。推荐把 [Agent 联调配置片段](../../../examples/alpha-qwen.env.example) 中的非敏感参数合入现有文件，保留其他 CORS、ALPHA_PACKAGE_DIR、会话设置及本地密钥。不要直接覆盖团队已有环境文件。部署由薛锦荣通过运行环境 Secret 注入。

`scripts/run_alpha_agent.py` 作为 Agent 本地排查工具保留：显式读取资料包、组装 Retriever/规则/Qwen、注入基础 FastAPI。它不带正式运行入口的会话包装，不作为第二套正式部署入口。

```powershell
# 在仓库根目录执行，先查看参数；这一步不需要密钥或规则模块。
.venv\Scripts\python.exe -X utf8 -m scripts.run_alpha_agent --help

# 仅用于显式资料包的本地排查，环境变量需提前注入。
# --package 可重复；文件路径及包内 storage_key 均相对于 --file-root。
.venv\Scripts\python.exe -X utf8 -m scripts.run_alpha_agent `
  --package 'path/to/approved-package.json' `
  --workflow-timeout-seconds 30
```

示例包路径需要替换为实际交付的 JSON 文件。启动入口默认使用仓库根目录、`127.0.0.1:8000`；不自动扫描资料目录，不自动修改 `blocked/review_only` 状态，不提供 demo 回退。缺规则、缺密钥、索引损坏或不完整时启动失败。可以显式加载 blocked 包验证拒答，但这不构成正向正式资料验收。

`QwenSettings.from_env()` 和排查脚本不自动读取 `.env`；正式 Uvicorn 命令通过 `--env-file backend/.env` 加载，部署时直接注入进程环境。不要在 PR、聊天、日志中发送密钥。

会话口径按入口区分：基础 `create_app()`/main 和本地排查脚本没有会话存储，应重发完整问题；正式 alpha 入口的 ConversationAgentService 会按 conversation_id 注入用户历史，第二轮可以补充信息。待该分支集成后应通过正式入口验证多轮追问和会话隔离。

## 超时预算

适配器公共默认值仍为 20 秒、最多重试一次；Agent 对完整 `generate()` 等待最多 30 秒。按新版补充说明，本轮真实联调通过环境采用以下配置，不修改公共默认值：

```env
QWEN_TIMEOUT_SECONDS=28
QWEN_MAX_RETRIES=0
```

保持 Agent 外层 30 秒，先验证一次完整 JSON 输出，避免二次调用在边界取消。后续是否改为 14 秒、1 次重试，依据实测与负责人确认，不自动切换。

技术限制：httpx 配置的超时约束连接、读写等阶段，不是整次请求的墙钟时长承诺。不能将 28 秒直接当作完整调用保证，也不能将两次 14 秒加退避当作严格总时限；最终由 Agent 的外层等待上限取消超时调用。检索有独立等待上限，完整 API 延迟可能更长。

## 验证与限制

使用真实 BM25、文件/哈希检查、工作流、Qwen 适配器和 FastAPI，新增启动路径、网络超时/连接失败、模型响应异常、CORS/request ID、总等待取消及共享重试预算检查。供应商网络仍使用 MockTransport；业务函数仍使用明确标记的测试替身。

真实付费验收测试已补齐 FastAPI 问答层，在环境与资料就绪后可通过 `ALPHA_LIVE_QWEN_TEST=1` 显式运行。它会经过真实规则、BM25、真实模型端点和 Citation 校验；当前没有执行付费调用，也没有把测试替身当成正式规则。

完整最新结果见 `evidence/agent-integration/unittest.txt` 和 `environment.json`。原有三个真实 blocked 包仍只验证安全拒答。

## 新版补充说明后的确认与剩余协调

新版补充说明已经回答：端点和模型、账号持有人本地配置、真实短片段探测结果、28秒且不重试的建议、环境加载及正式入口。不再要求他重复提供这些信息。原始记录已在其运行分支的 `docs/assignment-03/alpha/qwen-real-probe.md`；未把上游真实探测伪装成本机执行结果。

可直接转发给赵紫龙：

赵紫龙你好，补充说明收到，路径、输出协议、账号分工和环境加载方式都已确认。我的文档已统一正式启动入口为 backend.app.alpha:app，自有脚本只保留作本地排查；真实联调采用 QWEN_TIMEOUT_SECONDS=28、QWEN_MAX_RETRIES=0，Agent 外层保留30秒，并补了配置传递与不重试的离线测试。

还有两处运行组装需要一起收口：

1. 我查看的 alpha_runtime 分支仍有自建资料加载和缺业务规则时回退旧默认规则的逻辑。请在正式组装中与 PR #35 的统一加载/元数据查询对齐，并在正式规则不可用时保持“未就绪”。雷葭雨PR #36已确认 `build_from_retriever(retriever, today=...)`，Agent现已接入并用PR #35/#36原始代码完成跨分支测试；请正式运行组装同样使用这个工厂绑定同一索引，不要传未绑定的裸证据函数。
2. 候选资料继续可用于加载、隔离和安全拒答测试；正式正向验收待审核资料和账号就绪后再安排。届时一起记录请求时间、模型、HTTP状态、总耗时、可分享的脱敏证据JSON和引用校验结果，当前不标为真实模型已通过。

补充：引用允许集合应是本轮经过基础门槛和业务规则过滤后实际交给Qwen的合格片段集合；原始检索命中但被业务规则剔除的片段也不能引用。httpx超时不是严格总时长，最终由Agent外层30秒取消保障。

业务函数交付和正式资料审核另由对应负责人完成，不需要你代写。上述文字由用户转发，本轮没有代发新消息。

## 本地API Key使用和短片段复测

账号持有人在自己的 `backend/.env` 中填写QWEN_API_KEY，其他配置参考 `examples/alpha-qwen.env.example`，模型qwen-flash、超时28秒、0重试。保留文件已有的CORS、资料目录和会话设置。仅在本地编辑器填写密钥，不把值放到终端命令参数或测试记录；也不要覆盖已有.env来创建空配置。

新增 `scripts/check_qwen_live.py` 供接入方复测。没有 `--live` 时不会读取.env或创建模型客户端。以下命令会发送一次真实付费短片段请求，只在账号配置好且确定要复测时由用户运行：

```powershell
# 查看帮助，不请求模型。
.venv\Scripts\python.exe -X utf8 -m scripts.check_qwen_live --help

# 真实小样本复测：仅“测试原文。”、真实UUID、max_tokens=128。
.venv\Scripts\python.exe -X utf8 -m scripts.check_qwen_live --live --env-file backend/.env
```

可选 `--env-file` 使用python-dotenv（后端uvicorn standard依赖已包含）；已存在的进程环境变量优先，不覆盖。客户端仍通过原有 `create_qwen_client_from_env()` 生成并内部传Authorization，无需组员拼接鉴权头。Key不可用时返回脱敏错误码；不在日志打印供应商原始响应或异常。

成功输出时间、模型、耗时、usage及经过Agent生产引用校验器验证的固定测试证据。适配器不暴露供应商成功HTTP状态，输出使用adapter_result=success，不凭空记为直接观测HTTP 200；需要原始HTTP状态的完整正式联调记录由后端负责人采集。

此工具不调用Retriever/业务规则、不加载政策，不替代正式验收。它改用真实UUID，可通过Agent引用验证；赵紫龙的flash-probe-001只是其独立格式探测ID，不应直接作为Agent的RetrievedChunk身份。

工具的离线测试覆盖显式启用前零调用、短片段参数和引用核验、篡改引用拒绝。本机未运行上述--live命令；真实正式资料及账户授权就绪后再执行端到端验收。
