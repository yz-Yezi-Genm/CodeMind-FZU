# Alpha Runtime 最终集成复核

日期：2026-11-21（Asia/Shanghai）

## 集成版本

| 模块 | 最终 `main` 版本 | 最终使用方式 |
|---|---|---|
| #35 已审核资料加载器 | `main a87182c` | `load_approved_alpha_retriever()` |
| #36 业务规则 | `main 474574e` | `build_from_retriever(retriever)` |
| #32 AgentWorkflow | `main e86f6b8` | `create_alpha_workflow()` |

#34 已同步 `origin/main e86f6b8`。正式运行时不再使用临时快照、全局证据函数或旧
AgentWorkflow fallback。

## main 同步与冲突解决

唯一冲突为 `tests/test_agent_workflow_api.py`。最终逐段合并双方测试：

- 保留 #32 的模型未知异常脱敏、`MODEL_UNAVAILABLE` 与 request ID 校验；
- 保留 #34 的 lifespan、真实 BM25、运行失败隔离、模型超时、多轮历史测试；
- 没有用任一分支文件整体覆盖另一方。

公共运行入口和 `backend/services/alpha_runtime.py` 自动合并，无未解决冲突。

## Python 3.10 超时兼容

`AgentWorkflow`、FastAPI 路由和异常处理器现在同时识别
`asyncio.TimeoutError` 与内置 `TimeoutError`，统一转换为：

```json
{"error":{"code":"MODEL_TIMEOUT","retryable":true}}
```

当前机器只有 Python 3.14，无法执行 3.10.11 二进制环境；已增加直接抛出
`asyncio.TimeoutError` 的回归测试，并通过显式异常类型处理覆盖 3.10 分支。

## 测试结果

全量项目测试：

```text
pytest tests -q
345 passed, 27 skipped, 136 subtests passed
```

最终定向测试：

```text
tests/test_backend_runtime.py
tests/test_agent_workflow_api.py
tests/test_agent_workflow_qwen.py
tests/test_local_retrieval.py
tests/test_alpha_corpus.py
tests/test_alpha_business_rules.py

198 passed, 26 skipped, 48 subtests passed
```

正式上游集成脚本：

```text
python -m scripts.verify_alpha_upstream_integration
Ran 25 tests, OK
```

## 真实 Qwen HTTP

最终代码已启动真实 Uvicorn，并通过本地 HTTP 请求完成：

```text
GET /api/v1/health -> 200
POST /api/v1/ask -> 200
status=answered
citations.length=1
```

请求经过正式 #35 加载器、#32 工作流、#36 业务规则、真实 Qwen 和 Citation
逐字校验。脱敏请求、响应、模型和资料标记见
[final-qwen-http.txt](final-qwen-http.txt)。

本次 HTTP 验收使用 `tests/fixtures/alpha_approved` 中的 `example.invalid`
合成审核夹具，未开放 #31 候选政策资料。

## 失败关闭覆盖

全量测试已验证：

- approved 目录缺失；
- 未人工审核；
- manifest 与包内审核标记不一致；
- 部分索引、失败索引和 warnings；
- 正式业务规则判定证据不适用；
- 历史证据不进入当前政策回答；
- 业务拒绝时 Qwen 调用为零；
- 引用伪造、改写原文、未知 chunk ID；
- 模型调用期间资料撤回后的二次核验。

## 正式资料状态

默认 `knowledge_base/processed/alpha/approved/` 仍没有人工签核后开放的正式
`enabled` 文档包。缺少正式资料时运行时失败关闭并返回
`KNOWLEDGE_BASE_UNAVAILABLE`，不会加载 #31 候选包。
