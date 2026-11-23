# Beta AgentWorkflow 联调记录

2026 年 11 月 23 日，吴诗莹。[PR #46](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/46) 的开发分支为 `feat/beta-agent-history`，已同步 `main` 的 `a789f53`。本次完整回归验证的代码提交为 `860b630`。

## 工作流

- `backend/services/agent_workflow.py` 沿用 `run(AgentRequest) -> AgentResult` 及运行时的业务规则注入。先检查是否需要追问，再检索。业务方向不明确时仍使用全库 BM25，业务场景与适用性由注入的规则判断。
- Agent 从同一个 Retriever 查询每个版本的 `DocumentMetadata` 和 `ParsedChunk`，检查人工审核标记严格为 `true`、来源、开放状态、已知日期、适用范围及片段身份。模型调用返回后重新检查已引用的资料，审核撤回或片段变化时拒答。
- `backend/services/agent_policy_context.py` 处理会话的用户侧补充信息和时间边界。历史回答标注年份、历史属性及是否已被替代。开放期年度通知使用 `procedure_reference`，现行通用政策使用 `current_policy`。
- `backend/services/agent_generation.py` 校验 Qwen 的 `answer` 和 `used_evidence_ids`。每次调用独立分配带随机后缀的临时 ID，引用由 Agent 使用通过门禁的 `RetrievedChunk` 构造。答案保留证据的完整陈述，允许少量等义措辞，并检查明确询问的金额和截止日期是否出现在已选证据中。部分答案须说明缺口。校验失败时返回 `insufficient_evidence`。
- 相关工作流、HTTP 和适配器测试已更新其测试替身。公共 DTO、Protocol、`/api/v1/ask`、业务规则实现、Retriever、QwenClient 和 Runtime 沿用上游实现。

## 验证记录

| 范围 | 实际验证 | 结果 |
| --- | --- | --- |
| 仓库根目录完整 pytest | 验证 `860b630`，包含数据库设计测试和后端测试。Agent 回归覆盖一个片段支持金额和截止日期、重复金额无法补齐截止日期，以及短句追问沿用主题。模型响应使用测试替身。 | 407 通过，31 跳过，1 条警告，另有 144 个子测试通过 |
| 第一阶段 `main` 上游快照 `9016441` | 真实 BM25、元数据与章节查询、S1–S3 规则和 Qwen HTTP 适配器。使用合成资料和 `httpx.MockTransport`。 | 25 通过，3 个 S4 用例跳过 |
| 第一阶段业务规则快照 `100bc1a` | 同一 BM25 与适配器组合，加载雷葭雨的规则分支快照。覆盖 S4 研究方向、过期招募的历史回答、开放期报名及不适用年级。 | 27 通过，1 个要求规则快照与 `main` 字节一致的用例未选中 |

在 `860b630` 上从仓库根目录重新运行并直接保存标准输出与标准错误，退出码为 `0`。日志包含全部跳过原因与警告。[完整 pytest 原始输出](evidence/agent-workflow-pytest-860b630.txt)

```powershell
.venv/Scripts/python.exe -m pytest -q -rs --tb=short
```

第一阶段的联调快照位于临时目录。以下是当时的源码版本与复现命令。使用 `git show <ref>:<path>` 将源码按下表保存并将 `ALPHA_UPSTREAM_SNAPSHOT` 指向目录。

| 仓库路径 | 快照相对路径 | 版本 |
| --- | --- | --- |
| `backend/retrieval/local.py` | `retrieval/local.py` | `9016441` |
| `backend/retrieval/alpha_corpus.py` | `retrieval/alpha_corpus.py` | `9016441` |
| `backend/services/alpha_business_rules.py` | `alpha_business_rules.py` | 第一组 `9016441`，第二组 `100bc1a` |

```powershell
$env:ALPHA_UPSTREAM_SNAPSHOT = '<临时快照目录>'
# 第一组使用 main 快照。
.venv/Scripts/python.exe -m pytest -q tests/test_agent_workflow_qwen.py::UpstreamRulesRetrieverIntegrationTests --tb=short
# 第二组使用 Beta 规则快照。
.venv/Scripts/python.exe -m pytest -q tests/test_agent_workflow_qwen.py::UpstreamRulesRetrieverIntegrationTests --tb=short -k 'not merged_business_rules_match_snapshot'
```

## 正式验收待办

- 第二轮复审待补充 S4 联调。需与雷葭雨确认 R4/R6 在 `applicability_raw=None` 时的适用范围例外，以及过期招募通知可说明对应年度已截止的答复边界。该通知无法证明新一轮招募状态或实时名额。
- Retriever 的两个只读方法已由 V2.1-Final §8.2–8.4 确认为正式接口。`LocalBM25Retriever` 已实现，公共 `Retriever` Protocol 的声明由王智洋负责补齐。
- S4 规则目前在上游 Beta 分支。合入 `main` 后需通过正式 `/api/v1/ask` 入口复跑联调。涉及历年报名的资料需明确适用年度和对象。若业务规则拒绝仅写年份的已替代政策查询，请与规则负责人核对历史意图条件。
- 本地正式 `approved/` 暂无已审核资料包，且本地执行环境未配置 `QWEN_API_KEY`。真实政策和真实 Qwen 的四领域验收仍待具备这些输入后执行。
