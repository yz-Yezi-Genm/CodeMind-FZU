# Beta AgentWorkflow 联调记录

2026 年 11 月 24 日，吴诗莹。开发分支为 `feat/beta-agent-history`，已通过合并提交 `f91cc08` 同步 `main` 的 `5973eef`。本轮测试覆盖该基线及 #46 的复审修订，直接运行仓库中已合入的业务规则和 Retriever 契约。[PR #46](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/46) · [业务规则 #45](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/45) · [Retriever #51](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/51)

## 工作流

- `backend/services/agent_workflow.py` 沿用 `run(AgentRequest) -> AgentResult` 及运行时的业务规则注入。先检查是否需要追问，再检索。业务方向不明确时仍使用全库 BM25，业务场景与适用性由注入的规则判断。
- Agent 从同一个 Retriever 查询每个版本的 `DocumentMetadata` 和 `ParsedChunk`，检查人工审核标记严格为 `true`、来源、开放状态、已知日期、适用范围及片段身份。模型调用返回后重新检查已引用的资料，审核撤回或片段变化时拒答。
- `backend/services/agent_policy_context.py` 处理会话的用户侧补充信息和时间边界。历史回答标注年份、历史属性及是否已被替代。开放期年度通知使用 `procedure_reference`，现行通用政策使用 `current_policy`。
- R4 公开研究介绍和 R6 学院公开联系方式允许 `applicability_raw=None`，仍需通过来源核验、人工审核和注入的 S4 业务规则。R6 的这一例外要求来源是学院官网 `ccds.fzu.edu.cn` 的直接 HTTPS 页面。个人适用性由相应办理或招募规则判断，R1/R2/R3/R5 仍需适用范围。
- 用户询问青禾计划或具名实验室当前是否还招募时，若只有匹配该事项、已审核且年度和截止日期明确的 R3 通知，`historical`、`expired` 两种状态均可返回 `answered / historical`。Agent 根据核验后的元数据说明该年度报名已截止、新一轮状态无法确认，并引用原通知。「现在还招吗」在上轮已明确主题时沿用该主题。实时余量仍按证据不足处理，引用为空。
- `backend/services/agent_generation.py` 校验 Qwen 的 `answer` 和 `used_evidence_ids`。每次调用独立分配带随机后缀的临时 ID，引用由 Agent 使用通过门禁的 `RetrievedChunk` 构造。答案保留证据的完整陈述，允许少量等义措辞，并检查明确询问的金额和截止日期是否出现在已选证据中。部分答案须说明缺口。校验失败时返回 `insufficient_evidence`。
- 相关工作流、HTTP 和适配器测试已更新其测试替身。公共 DTO、Protocol、`/api/v1/ask`、业务规则实现、Retriever、QwenClient 和 Runtime 沿用上游实现。

## Retriever 交接

王智洋已在 #51 声明 `retrieve(request)`、`get_document_metadata(version_id)` 和 `get_parsed_chunk(chunk_id)`。后两个方法在 `LocalBM25Retriever` 中返回深拷贝，遇到未知、未开放或已撤回资料时返回 `None`。#46 在现有方法上接入，`DemoRetriever` 已提供两种只读查询，旧的 `_PackageSnapshotRetriever` 已移除。工作流测试补验 BM25 中的资料在模型生成期间撤回到 `review_only` 或 `blocked` 时，两种查询均返回 `None`，HTTP 问答返回 `insufficient_evidence / insufficient_data` 和空引用。

## 本轮复审修改

- S4 招募期与年度计划人数仍使用通过证据门禁的年度通知。当前剩余名额需要经核验的实时数据。当前接入只有政策资料，因此实时名额问句在模型调用前返回 `insufficient_evidence / insufficient_data`，引用为空。
- 会话中的年份和历史意图分别处理。补充「2024 年呢」会把新年份和上一轮的旧版培养方案主题一起传给业务规则。当前培养方案问句仍会拒绝已被替代的版本。
- 「还可以报名吗」可沿用上一轮的具名实验室。若只召回已审核且年度和截止日期明确的过期通知，Agent 引用该通知说明对应年度报名已截止，并提示新一轮招募状态暂无法确认。
- 联调测试直接导入检出的业务规则、资料加载器和 BM25。常规 pytest 会收集这些用例，涵盖 `POST /api/v1/ask` 及其会话存储。测试使用合成资料和模拟的 Qwen HTTP 响应。

## 验证记录

| 验证 | 结果 |
| --- | --- |
| 仓库根目录完整 pytest | 513 通过，3 跳过，1 条警告，204 个子测试通过。[原始输出](evidence/agent-workflow-pytest-main5973eef.txt) |
| 已合入 #45 的规则、Retriever 和 Agent 联调 | 33 通过，1 条警告，58 个子测试通过。[原始输出](evidence/agent-workflow-merged-rules-main5973eef.txt) |

两个命令均从仓库根目录运行，退出码为 `0`。完整回归跳过了两个需正式资料与真实 Qwen 的用例和一个当前 Windows 账户无法创建符号链接的用例。警告来自 Starlette 测试客户端的依赖弃用提示。

```powershell
.venv/Scripts/python.exe -m pytest -q -rs --tb=short
.venv/Scripts/python.exe -m pytest -q -rs --tb=short tests/test_agent_workflow_qwen.py::MergedRulesRetrieverIntegrationTests
```

## 正式验收待办

- [PR #41](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/41) 的青禾候选包在 `1e9693c` 中仍是 `blocked`、`human_approved=false`，`category_name` 为 `科研实践与实验室`。要用正式资料完成 A4 验收，需由资料负责人对齐 #45 的 R3 类别 `实验室与科研团队`，并经组长审核放行。
- S4 规则目前在上游 Beta 分支。合入 `main` 后需通过正式 `/api/v1/ask` 入口复跑联调。涉及历年报名的资料需明确适用年度和对象。若业务规则拒绝仅写年份的已替代政策查询，请与规则负责人核对历史意图条件。
- 本地正式 `approved/` 暂无已审核资料包，且本地执行环境未配置 `QWEN_API_KEY`。真实政策和真实 Qwen 的四领域验收仍待具备这些输入后执行。
