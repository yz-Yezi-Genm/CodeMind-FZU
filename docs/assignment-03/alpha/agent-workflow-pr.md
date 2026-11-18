# PR 标题

feat(agent): 实现遵循 Alpha 契约的最小 Agent 工作流

# PR 正文草稿

当问题缺少必要信息时，独立的 `AgentWorkflow` 返回 `needs_clarification`；无可用证据时返回 `insufficient_evidence`；检索证据满足门禁后，通过注入的 `LLMClient` 选择和排列证据，并以 `answered` 返回摘录回答。引用仅从本轮实际采用的检索片段构造，模型伪造 ID、改写原文或额外政策结论会被拒绝。

复用现有公共模型及异步协议，未修改公共接口或 FastAPI 主入口。补充三状态测试、异常/超时/禁用资料/版本冲突测试、现有 `create_app(agent_service=...)` 注入验证、流程图、使用文档及实际测试记录。

验证命令：`python scripts/verify_agent_workflow.py`。实际结果见 `docs/assignment-03/alpha/evidence/test-record.md`。

已同步 `main@3baee66`，并使用已合并的 `QwenLLMClient` + 模拟 HTTP 验证成功回答、自由回答拦截和 401/408/429/500 错误映射。全仓 102 项测试：101 项通过、1 项因 Windows 账户不能创建符号链接而跳过；三状态演示退出码 0。新增文件与本次远程 main 没有同路径冲突，其他成员的文件未被覆盖。

真实检索器与 Qwen 尚未接入；测试和演示均为明确标记的替身。初版关键词追问规则待雷葭雨确认；复杂政策适用性、历史版本及跨文档冲突判断需后续协作接入。

分支：`feat/alpha-agent-workflow-wushiying` → `main`。本文件仅为草稿，未创建或提交线上 PR。
