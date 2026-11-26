# Beta 第二阶段：真实 Qwen 与最终 AgentWorkflow 联调

日期：2026-11-26
分支：`feat/beta-runtime-qwen-integration`
同步基线：`origin/main` `a27c13d`

## 1. 阶段边界

第一阶段 FastAPI、Runtime、QwenClient、会话和统一异常处理已通过 PR #49
合并。#46 已合入 main，提供 V2.1 受约束生成、动态 evidence ID、答案校验、
历史政策处理及 Citation 构造。

第二阶段只增加真实模型技术联调、隔离合成资料和证据记录，不修改公共 DTO、
Protocol、AgentWorkflow、Retriever 或业务规则。

## 2. 真实链路

固定 main `a27c13d` 后，通过本机 uvicorn TCP HTTP 执行：

```text
POST /api/v1/ask
  -> FastAPI
  -> ConversationAgentService
  -> AgentWorkflow
  -> LocalBM25Retriever
  -> 正式业务规则
  -> 真实 qwen-flash
  -> V2.1 JSON 与 evidence ID 校验
  -> RetrievedChunk 构造 Citation
  -> AskResponse
```

联调资料固定为
`tests/fixtures/beta_live_synthetic/`。该目录明确标注为合成数据，来源域名为
保留测试域名 `example.invalid`，不属于正式 `approved/` 知识库。
其中 `temporal_notes.human_approved=true` 仅用于覆盖现有加载器和 Agent
审核门禁，是合成测试字段，不代表真实人工签核，正式审核机制未被放宽。
重命名后已通过真实审核加载器、索引与 BM25 检索测试。

正向请求：

```json
{"query":"2026年优秀学生综合奖学金申请需要提交什么材料？"}
```

结果：

- HTTP 200，`status=answered`，`answer_mode=current_policy`；
- 真实模型返回受约束 JSON，使用本次请求生成的随机 evidence ID；
- Citation 的 `chunk_id`、`excerpt`、来源和审核状态来自同一次真实检索；
- `X-Request-ID` 与响应 `request_id` 一致。

脚本会实际断言 `answer_mode`、Citation excerpt 与检索片段一致，以及
`X-Request-ID` 与响应 `request_id` 一致，不是仅记录响应结果。

模型原始内容：

```json
{"answer":"根据已核验资料，2026年优秀学生综合奖学金申请需提交申请表和成绩单。","used_evidence_ids":["E1-<本次随机命名空间>"]}
```

完整脱敏记录见 [runtime-http-smoke.txt](evidence/runtime-http-smoke.txt)。

## 3. 安全拒答

- 合成资料未载明奖学金金额时，`POST /api/v1/ask` 返回 HTTP 200、
  `insufficient_evidence`、空引用，warning 为 `REQUESTED_FACT_NOT_FOUND`。
- E2E 脚本会实际断言拒绝状态的 `answer_mode=insufficient_data` 和 warning
  集合等于 `REQUESTED_FACT_NOT_FOUND`。
- 正式 `knowledge_base/processed/alpha/approved/` 尚未放行资料时，运行时启动
  失败关闭，问答返回 HTTP 503、`KNOWLEDGE_BASE_UNAVAILABLE`，不会调用 Qwen
  或返回 Mock 答案。

## 4. MockTransport 边界验证

以下结果全部来自 Mock Qwen 或离线测试，不代表真实模型返回：

- 未知、重复、跨轮 evidence ID 被拒绝；
- 有效 ID 搭配编造答案被拒绝；
- 自由文本或不符合 JSON envelope 的输出不能绕过证据校验；
- 两个真实模型入口在未提供 `--live` 时于读取配置前退出；
- `create_alpha_app` 延迟到 `--live` 检查后导入，避免默认构造应用；
- 非法或空模型 envelope 返回 HTTP 503 `MODEL_UNAVAILABLE`；
- 限流保持 HTTP 429 `RATE_LIMITED`；
- 超时返回 HTTP 504 `MODEL_TIMEOUT`，连接失败返回 HTTP 503；
- 工作流总超时会取消底层模型调用。

定向结果：`13 passed, 1 warning, 30 subtests passed`。记录见
[qwen-negative-mock.txt](evidence/qwen-negative-mock.txt)。
两个入口的直接无授权退出结果见
[qwen-live-guards.txt](evidence/qwen-live-guards.txt)。

最新 main `a27c13d` 的 Agent、业务规则、Retriever 与 HTTP 专项集成结果为
`Ran 48 tests, OK`，记录见
[upstream-integration.txt](evidence/upstream-integration.txt)。

早期
[qwen-constrained-live.txt](evidence/qwen-constrained-live.txt)
是真实模型的独立适配器探针，不等同于本次最终 `/api/v1/ask` 全链路验收。
该探针只有一条证据，因此要求 `used_evidence_ids` 精确等于 `["E1"]`；
空列表或其他 ID 组合都会被判定失败。

## 5. 全量回归

```text
Python 3.14.4:
643 passed, 3 skipped, 1 warning, 274 subtests passed

Python 3.10.11:
643 passed, 3 skipped, 1 warning, 274 subtests passed
```

跳过项：

1. 1 项需显式启用的真实 Qwen 正式资料验收；
2. 1 项 `RUN_LIVE_QWEN_TESTS=1` 的正式资料 E2E；
3. 1 项当前 Windows 账户无符号链接权限。

本轮真实 Qwen 技术联调由独立脚本执行，不与上述跳过项混淆。完整输出见：

- [stage2-pytest-py314.txt](evidence/stage2-pytest-py314.txt)
- [stage2-pytest-py310.txt](evidence/stage2-pytest-py310.txt)

前端 #54 回归：`9` 项学生端 API 测试通过，TypeScript 与 Vite 生产构建通过。
记录见 [stage2-frontend-check.txt](evidence/stage2-frontend-check.txt)。

## 6. 资料与模型边界

| 类型 | 本次用途 | 结果 |
| --- | --- | --- |
| 合成资料 | 技术联调 | 真实链路正向通过 |
| 正式资料 | 人工审核状态检查 | 未放行，503 安全拒答 |
| Mock Qwen / Live Guard | 边界、异常与授权保护 | 13 项定向测试通过 |
| 真实 Qwen | 正向生成 | qwen-flash 通过 |

正式人工审核资料放行后，再补一次真实政策问答验收，不需要等待该事项才能
完成当前技术联调。
