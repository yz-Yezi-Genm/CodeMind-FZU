# PR: Beta 第二阶段真实 Qwen 与 Agent 联调

## 修改目的

在 PR #49 和 #46 合入后，使用最终 AgentWorkflow 完成真实 Qwen 经
`POST /api/v1/ask` 的技术联调，并明确区分合成资料、正式资料、Mock Qwen
和真实 Qwen。

## 修改文件

- `scripts/check_beta_qwen_generation.py`
- `scripts/check_beta_qwen_e2e.py`
- `tests/fixtures/beta_live_approved/`
- `docs/assignment-03/beta/qwen-integration-stage2.md`
- `docs/assignment-03/beta/evidence/qwen-constrained-live.txt`
- `docs/assignment-03/beta/evidence/runtime-http-smoke.txt`
- `docs/assignment-03/beta/evidence/qwen-negative-mock.txt`
- `docs/assignment-03/beta/evidence/stage2-pytest-py310.txt`
- `docs/assignment-03/beta/evidence/stage2-pytest-py314.txt`

## 完成功能

- 同步 main `179e618`，包含 #46 AgentWorkflow 和 #49 运行稳定性；
- 通过本机 uvicorn TCP HTTP 调用最终 `/api/v1/ask`；
- 真实 `qwen-flash` 返回 `answer + used_evidence_ids` 受约束 JSON；
- Agent 校验本次动态 evidence ID，并用真实检索片段构造 Citation；
- 合成资料正向请求返回 200、answered、非空引用；
- 缺少金额证据时返回 200、insufficient_evidence、空引用；
- 正式 approved 资料未放行时返回 503、KNOWLEDGE_BASE_UNAVAILABLE；
- 未知、重复、跨轮 ID、伪造答案、非法模型响应、限流和超时由独立 Mock
  Transport 测试覆盖。

## 依赖

- 第一阶段：PR #49，已合并
- Agent：PR #46，已合并
- 最新 main：`179e618`
- 正式资料：项目负责人最终人工审核

## 测试

```text
Python 3.14.4: 632 passed, 3 skipped, 1 warning, 274 subtests passed
Python 3.10.11: 632 passed, 3 skipped, 1 warning, 274 subtests passed
Mock Transport 定向: 10 passed, 1 warning, 30 subtests passed
上游专项: Ran 48 tests, OK
真实 Qwen HTTP 联调: HTTP 200, answered, non-empty citation
```

## 已知问题

- 当前正式 approved 目录仍无人工签核资料，因此未执行真实政策正向验收；
  该场景已验证为 HTTP 503 安全拒答。
- 正式资料放行后需追加真实政策问答记录，不阻塞当前合成资料技术联调。
