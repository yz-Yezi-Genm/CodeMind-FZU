# PR: Alpha FastAPI 真实运行组装

## 修改目的

把已经合入的 `LocalBM25Retriever`、`AgentWorkflow` 和 `QwenLLMClient` 装配成可启动的 FastAPI 服务，并补上服务端多轮会话、异常边界和运行测试。

## 主要修改

- 新增 `backend.app.alpha:app` 和 lifespan 运行组装；
- 新增 `backend/services/alpha_runtime.py`；
- 通过 #35 统一加载器只加载 manifest 和 `temporal_notes` 均人工审核通过的 `enabled` 资料包；
- 实现按 `conversation_id` 隔离、有界且串行写入的内存会话；
- 将知识库、Retriever、Agent 和 Qwen 异常映射为统一 HTTP 错误；
- 新增运行配置、测试夹具、运行文档与证据。

## 上下游依赖

- 吴诗莹的 `AgentWorkflow` 构造函数和 `run(AgentRequest) -> AgentResult`；
- 王智洋的 `LocalBM25Retriever(file_root=...)` 和异步索引/检索；
- 现有 Qwen OpenAI-compatible 适配器；
- 丁晓炜后续交付人工签核的 `knowledge_base/processed/alpha/approved/` 正式包。

最终代码使用已合并的 #32 `create_alpha_workflow()` 和 #36
`build_from_retriever(retriever)`，不再使用未绑定 Retriever 的全局证据规则。

## 测试命令

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q
```

最终全量结果：`345 passed, 27 skipped, 136 subtests passed`。

最终定向运行、API、Retriever、审核加载器和 #36 规则测试：
`198 passed, 26 skipped, 48 subtests passed`。

`scripts.verify_alpha_upstream_integration`：25 项全部通过。

## 运行证据

- HTTP 进程冒烟：`docs/assignment-03/alpha/evidence/real-runtime-smoke.txt`
- 最终真实 Qwen HTTP：`docs/assignment-03/alpha/evidence/final-qwen-http.txt`
- 测试分层和完整结果：`docs/assignment-03/alpha/evidence/real-runtime-tests.txt`
- 配置与启动说明：`docs/assignment-03/alpha/real-runtime.md`

## 未完成事项

- 当前 `approved/` 没有人工签核后开放的正式资料包；
- 2026-11-21 已在最终合并 main 上完成真实 Qwen HTTP 200 / answered / 非空引用验收；
- 合成审核夹具仅用于技术验收，仍需在正式签核资料到达后执行政策正向验收；
- 正式默认目录缺少资料时正确返回 `KNOWLEDGE_BASE_UNAVAILABLE`。

任何 MockTransport 或合成 `example.invalid` 测试都不视为真实模型或正式政策验收成功。

## 第二轮审核修复

- 资料加载改为 #35 `load_approved_alpha_retriever()`，核对人工审核标记、路径安全、完整索引、warnings 和片段数量。
- 业务规则改为 #36 `build_from_retriever(retriever)`。
- 已同步最终 main `e86f6b8`，直接使用 #32 `create_alpha_workflow()`。
- Agent API 合并冲突保留双方测试：#32 的安全 envelope 测试与 #34 的 lifespan/运行组装测试同时保留。
- 兼容 Python 3.10 的 `asyncio.TimeoutError` 与内置 `TimeoutError`，统一映射为 HTTP 504。
- 奇数消息上限向下归一化；会话增加数量上限、空闲回收、活动请求保护和后台清理。
- 新增未审核、部分索引、warnings、业务拒绝和正式审核成功路径测试。

第二轮集成版本、定向/全量测试结果和失败关闭记录见
[运行时上游集成复核](evidence/runtime-upstream-review.md)。
