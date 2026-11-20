# PR: Alpha FastAPI 真实运行组装

## 修改目的

把已经合入的 `LocalBM25Retriever`、`AgentWorkflow` 和 `QwenLLMClient` 装配成可启动的 FastAPI 服务，并补上服务端多轮会话、异常边界和运行测试。

## 主要修改

- 新增 `backend.app.alpha:app` 和 lifespan 运行组装；
- 新增 `backend/services/alpha_runtime.py`；
- 只加载人工审核目录中 `retrieval_status=enabled` 的资料包；
- 实现按 `conversation_id` 隔离、有界且串行写入的内存会话；
- 将知识库、Retriever、Agent 和 Qwen 异常映射为统一 HTTP 错误；
- 新增运行配置、测试夹具、运行文档与证据。

## 上下游依赖

- 吴诗莹的 `AgentWorkflow` 构造函数和 `run(AgentRequest) -> AgentResult`；
- 王智洋的 `LocalBM25Retriever(file_root=...)` 和异步索引/检索；
- 现有 Qwen OpenAI-compatible 适配器；
- 丁晓炜后续交付人工签核的 `knowledge_base/processed/alpha/approved/` 正式包。

当前业务规则模块未合入时，运行入口使用 AgentWorkflow 已有的保守默认追问规则，不伪造 `alpha_business_rules.py`。模块合入后会自动导入两个正式回调。

## 测试命令

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_backend_runtime tests.test_agent_workflow_api tests.test_agent_workflow_qwen tests.test_qwen_client -v
```

结果：44 项执行，43 项通过，1 项在 #36 合入前按条件跳过。

全仓库结果：199 项中 195 通过、2 失败、2 跳过。两个失败均为现有 `scholarship-2026` 原始资料 SHA-256 与登记值不一致；跳过项分别为 Windows 符号链接权限和 #36 合入前条件测试。本次运行/会话/Qwen 测试均通过。

## 运行证据

- HTTP 进程冒烟：`docs/assignment-03/alpha/evidence/real-runtime-smoke.txt`
- 测试分层和完整结果：`docs/assignment-03/alpha/evidence/real-runtime-tests.txt`
- 配置与启动说明：`docs/assignment-03/alpha/real-runtime.md`

## 未完成事项

- 当前 `approved/` 没有人工签核后开放的正式资料包；
- 2026-11-20 已完成真实 Qwen `qwen-flash` 最小调用及合成运行时端到端调用；正式资料正向验收仍需 #32/#36 合并；
- 现有奖学金来源文件 SHA-256 不一致，需资料/检索负责人确认后重生成或修正；
- 业务规则模块合入后需再跑一次正式政策正向端到端测试。

任何 MockTransport 或合成 `example.invalid` 测试都不视为真实模型或正式政策验收成功。

## 第二轮审核修复

- 资料加载改为 #35 `load_approved_alpha_retriever()`，核对人工审核标记、路径安全、完整索引、warnings 和片段数量。
- 业务规则改为 #36 `build_from_retriever(retriever)`。
- 若 #32 的 `create_alpha_workflow()` 已合入则自动使用；当前未合入时保留同签名 fallback。
- 奇数消息上限向下归一化；会话增加数量上限、空闲回收、活动请求保护和后台清理。
- 新增未审核、部分索引、warnings、业务拒绝和正式审核成功路径测试。

第二轮集成版本、定向/全量测试结果和失败关闭记录见
[运行时上游集成复核](evidence/runtime-upstream-review.md)。
