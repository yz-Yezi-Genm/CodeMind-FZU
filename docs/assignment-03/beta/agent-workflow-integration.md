# Beta AgentWorkflow 联调记录

2026 年 11 月 23 日，吴诗莹。[PR #46](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/46) 的开发分支为 `feat/beta-agent-history`。本轮验证使用分支同步提交 `d7e3a6d`、`main` 基线 `306c15d`。该基线已包含 [PR #51](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/51) 的 Retriever 契约。S4 联调继续使用 [PR #45](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/45) 的规则快照 `265de18`。

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

## 验证记录

| 同步 `main` 后的测试 | 结果 |
| --- | --- |
| 仓库根目录完整 pytest，直接使用已合入的 #51 | 410 通过，35 跳过，1 条警告，另有 146 个子测试通过。[原始输出](evidence/agent-workflow-pytest-d7e3a6d.txt) |
| 已合入的 #51 与 #45 规则快照组合回归 | 441 通过，3 跳过，1 未选中，1 条警告，另有 201 个子测试通过。[原始输出](evidence/agent-workflow-main51-pr45-d7e3a6d.txt) |

两个命令均从仓库根目录运行，退出码为 `0`。完整回归运行 `.venv/Scripts/python.exe -m pytest -q -rs --tb=short`。组合回归启用 `ALPHA_UPSTREAM_SNAPSHOT`，使用 `306c15d` 的 Retriever、`265de18` 的业务规则，并传入 `-k 'not merged_business_rules_match_snapshot'`。

### 同步前的测试记录（`a789f53`）

| 范围 | 实际验证 | 结果 |
| --- | --- | --- |
| 仓库根目录完整 pytest | 包含数据库设计与后端测试。新增真实 BM25 与 Qwen HTTP 适配器的撤回回归，模型响应使用测试替身。 | 408 通过，35 跳过，1 条警告，另有 146 个子测试通过 |
| `#45` 实际规则快照 | 使用 `265de18` 的规则、`a789f53` 的 BM25 与资料加载器、Qwen HTTP 适配器及合成资料。覆盖 R4/R6 缺适用范围的正反向、R1/R2/R3/R5 缺适用范围、个人资格、青禾招募两种历史状态、短句追问、实时名额拒答和 `/api/v1/ask` 响应。 | 31 通过，1 个要求规则快照与当前检出源码相同的用例未选中，1 条警告，另有 55 个子测试通过 |
| `#45` 与 `#51` 组合回归 | 在临时副本加载 #51 的公共 Protocol 与检索测试，并启用 #45 的规则快照。覆盖签名、元数据与片段查询、资料撤回、Agent 和 S4 联调。 | 441 通过，3 跳过，1 未选中，1 条警告，另有 201 个子测试通过 |

从仓库根目录运行并直接保存标准输出与标准错误，退出码为 `0`。本轮新增了四个需 #45 快照的用例，默认完整回归中随快照组跳过，专项联调中均通过。[本轮完整 pytest 原始输出](evidence/agent-workflow-pytest-s4-review.txt) · [第一轮复审 `860b630` 的 pytest 原始输出](evidence/agent-workflow-pytest-860b630.txt)

```powershell
.venv/Scripts/python.exe -m pytest -q -rs --tb=short
```

专项联调使用临时规则快照。可用 `git fetch origin refs/pull/45/head` 取得上游提交，再用 `git show <ref>:<path>` 将下表源码保存到临时目录，并将 `ALPHA_UPSTREAM_SNAPSHOT` 指向该目录。[专项联调原始输出](evidence/agent-workflow-s4-pr45-265de18.txt)

| 仓库路径 | 快照相对路径 | 版本 |
| --- | --- | --- |
| `backend/retrieval/local.py` | `retrieval/local.py` | `a789f53` |
| `backend/retrieval/alpha_corpus.py` | `retrieval/alpha_corpus.py` | `a789f53` |
| `backend/services/alpha_business_rules.py` | `alpha_business_rules.py` | `265de18` |

```powershell
$env:ALPHA_UPSTREAM_SNAPSHOT = '<临时快照目录>'
.venv/Scripts/python.exe -m pytest -q tests/test_agent_workflow_qwen.py::UpstreamRulesRetrieverIntegrationTests -k 'not merged_business_rules_match_snapshot' --tb=short
```

组合回归在当前检出的临时副本上执行。取 `eeefacc` 中的 `backend/contracts/protocols.py`、`tests/test_interface_contracts.py` 和 `tests/test_local_retrieval.py` 覆盖副本中的同名文件，沿用上表的 `ALPHA_UPSTREAM_SNAPSHOT`，再从副本根目录运行 `python -m pytest -q -rs --tb=short -k 'not merged_business_rules_match_snapshot'`。该筛选排除了要求规则快照与本地 `main` 源码一致的用例。[组合回归原始输出](evidence/agent-workflow-pr45-pr51-combined.txt)

## 正式验收待办

- [PR #41](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/41) 的青禾候选包在 `1e9693c` 中仍是 `blocked`、`human_approved=false`，`category_name` 为 `科研实践与实验室`。要用正式资料完成 A4 验收，需由资料负责人对齐 #45 的 R3 类别 `实验室与科研团队`，并经组长审核放行。
- S4 规则目前在上游 Beta 分支。合入 `main` 后需通过正式 `/api/v1/ask` 入口复跑联调。涉及历年报名的资料需明确适用年度和对象。若业务规则拒绝仅写年份的已替代政策查询，请与规则负责人核对历史意图条件。
- 本地正式 `approved/` 暂无已审核资料包，且本地执行环境未配置 `QWEN_API_KEY`。真实政策和真实 Qwen 的四领域验收仍待具备这些输入后执行。
