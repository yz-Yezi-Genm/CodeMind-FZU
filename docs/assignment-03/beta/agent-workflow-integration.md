# Beta AgentWorkflow 联调记录

2026 年 11 月 24 日，吴诗莹。开发分支为 `feat/beta-agent-history`，通过 `f91cc08` 同步 `main` 的 `5973eef`。本轮联调直接运行已合入的 #45 业务规则和 #51 Retriever 契约。[PR #46](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/46) · [业务规则 #45](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/45) · [Retriever #51](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/51)

本轮验收代码提交为 `f4002459acf2d465ccbe229628c3f1d847ebefd9`。

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

- 实时名额门禁按问句中的事项关联主题。明确的奖学金主题会结束实验室主题的继承，「EDA 实验室研究什么？另外，奖学金还有几个名额？」会完整进入原有工作流，由实际业务规则询问奖学金类别。只有确认为实验室实时名额的子问句才会被拦截。
- 新增跨领域 HTTP 回归，覆盖明确的奖学金名额、省略主语但刚切换到奖学金的名额、已明确奖学金类别后保留完整检索问句，以及两类名额同问时只拦截实验室名额。原有实验室名额单问、实验室研究方向单问和同主题混合问句在同一套件中复跑。
- S4 招募期与年度计划人数使用通过证据门禁的年度通知。单独询问实时剩余名额时，当前接入缺少经核验的实时数据，Agent 在模型调用前返回 `insufficient_evidence / insufficient_data`，引用为空。
- 按业务规则 §2.4 处理混合事项。问「EDA 实验室研究什么，还有几个名额？」时，Agent 将研究方向交给原有工作流，并单独说明实时名额无法确认。通过门禁的 R4 介绍可以形成 `answered / current_policy` 并提供引用，`warnings` 记录 `LIVE_LAB_QUOTA_UNVERIFIED`。只有 R3 年度计划时整问返回证据不足。只问研究方向时按原流程返回。
- 新增 `/api/v1/ask` 联调覆盖名额单问、研究单问、正反顺序的混合问句及缺少 R4 资料的场景。BM25 同时召回 R3 年度计划和 R4 公开介绍，真实业务规则只让 R4 进入 Mock Qwen 的证据及最终引用。
- 会话中的年份和历史意图分别处理。补充「2024 年呢」会把新年份和上一轮的旧版培养方案主题一起传给业务规则。当前培养方案问句仍会拒绝已被替代的版本。
- 「还可以报名吗」可沿用上一轮的具名实验室。若只召回已审核且年度和截止日期明确的过期通知，Agent 引用该通知说明对应年度报名已截止，并提示新一轮招募状态暂无法确认。
- 联调测试直接导入检出的业务规则、资料加载器和 BM25。常规 pytest 会收集这些用例，涵盖 `POST /api/v1/ask` 及其会话存储。测试使用合成资料和模拟的 Qwen HTTP 响应。

## 验证记录

| 验证 | 结果 |
| --- | --- |
| 仓库根目录完整 pytest | 515 通过，3 跳过，1 条警告，209 个子测试通过。[原始输出](evidence/agent-workflow-full-cross-domain-quota-py31011.txt) |
| 已合入 #45 的规则、Retriever 和 Agent 联调 | 35 通过，1 条警告，63 个子测试通过。[原始输出](evidence/agent-workflow-integration-cross-domain-quota-py31011.txt) |

两个命令均从仓库根目录使用 Python 3.10.11（Windows AMD64）运行，退出码为 `0`。日志首行保留了 `python -VV`。完整回归跳过了两个正式资料与真实 Qwen 用例和一个当前 Windows 账户无法创建符号链接的用例。警告来自 Starlette 测试客户端的依赖弃用提示。

```powershell
$python = '..\python-3.10.11\tools\python.exe'
& $python -VV
& $python -m pytest -q -rs --tb=short
& $python -m pytest -q -rs --tb=short tests/test_agent_workflow_qwen.py::MergedRulesRetrieverIntegrationTests
```

## 正式验收待办

- #41 在 `d76de3c` 已提交青禾 R3 `实验室与科研团队` 和 R4 `研究方向与公开介绍` 两个候选包，均为 `blocked`、`human_approved=false`，待最终人工审核。[PR #41](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/41)
- 正式资料和真实 Qwen 的四领域验收留待后续集成。
