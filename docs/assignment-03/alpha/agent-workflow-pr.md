# PR 标题

feat(agent): 实现遵循 Alpha 契约的最小 Agent 工作流

# PR 正文

当问题缺少必要信息时，独立的 `AgentWorkflow` 返回 `needs_clarification`；无可用证据时返回 `insufficient_evidence`；检索证据满足门禁后，通过注入的 `LLMClient` 选择和排列证据，并以 `answered` 返回摘录回答。引用仅从本轮实际采用的检索片段构造，模型伪造 ID、改写原文或额外政策结论会被拒绝。

复用现有公共模型及异步协议，未修改公共接口或 FastAPI 主入口。补充三状态测试、异常/超时/禁用资料/版本冲突测试、现有 `create_app(agent_service=...)` 注入验证、流程图、使用文档及实际测试记录。

验证命令：`python scripts/verify_agent_workflow.py`。实际结果见 `docs/assignment-03/alpha/evidence/test-record.md`。

基于 `main@3baee66` 开发，并使用已合并的 `QwenLLMClient` + 模拟 HTTP 验证成功回答、自由回答拦截和 401/408/429/500 错误映射。最近一次完整验证为全仓 105 项测试：104 项通过、1 项因 Windows 账户不能创建符号链接而跳过；三状态演示退出码 0。新增文件未覆盖其他成员的文件。

已根据 PR #24 复核意见修正跨年度学年识别，并依据福大校历调整边界：2026-08-30 查询 2025-2026 学年仍可进入检索，2026-08-31 及之后进入历史/不支持模式。回归测试覆盖不同连接符、空格、历史与当前学年范围及切换日期。代码、测试和实际运行证据已随提交 `8392be7` 更新到本 PR。

真实检索器与付费 Qwen 服务尚未联通；测试和演示均使用明确标记的替身，Qwen 适配器组合验证使用模拟 HTTP。初版关键词追问规则待雷葭雨确认；复杂政策适用性、历史版本及跨文档冲突判断需后续协作接入。

分支：`feat/alpha-agent-workflow-wushiying` → `main`。现有 PR：[\#24](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/24)，本文件保存与 GitHub PR 描述同步使用的正文。
