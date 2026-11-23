# Beta AgentWorkflow 联调记录

2026 年 11 月 23 日，吴诗莹。开发分支为 `feat/beta-agent-history`，基于远端 `main` 的 `9016441`。

## 工作流

- `backend/services/agent_workflow.py` 沿用 `run(AgentRequest) -> AgentResult` 及运行时的业务规则注入。先检查是否需要追问，再检索。业务方向不明确时仍使用全库 BM25，业务场景与适用性由注入的规则判断。
- Agent 从同一个 Retriever 查询每个版本的 `DocumentMetadata` 和 `ParsedChunk`，检查人工审核标记严格为 `true`、来源、开放状态、已知日期、适用范围及片段身份。模型调用返回后重新检查已引用的资料，审核撤回或片段变化时拒答。
- `backend/services/agent_policy_context.py` 处理会话的用户侧补充信息和时间边界。历史回答标注年份、历史属性及是否已被替代。开放期年度通知使用 `procedure_reference`，现行通用政策使用 `current_policy`。
- `backend/services/agent_generation.py` 校验 Qwen 的 `answer` 和 `used_evidence_ids`。每次调用独立分配带随机后缀的临时 ID，引用由 Agent 使用通过门禁的 `RetrievedChunk` 构造。答案保留证据的完整陈述，允许少量等义措辞，并检查明确询问的金额和截止日期是否出现在已选证据中。部分答案须说明缺口。校验失败时返回 `insufficient_evidence`。
- 相关工作流、HTTP 和适配器测试已更新其测试替身。公共 DTO、Protocol、`/api/v1/ask`、业务规则实现、Retriever、QwenClient 和 Runtime 沿用上游实现。

## 验证记录

| 范围 | 实际验证 | 结果 |
| --- | --- | --- |
| 仓库后端测试套件 | 工作流单元测试、三种响应状态、跨请求 ID、资料撤回、错误映射和多轮会话隔离。模型响应使用测试替身。 | 368 通过，31 跳过，另有 139 个子测试通过 |
| `main` 上游快照 | 真实 BM25、元数据与章节查询、S1–S3 规则和 Qwen HTTP 适配器。使用合成资料和 `httpx.MockTransport`。 | 25 通过，3 个 S4 用例跳过 |
| 业务规则 Beta 分支 `100bc1a` | 同一 BM25 与适配器组合，加载雷葭雨的规则分支快照。S4 覆盖研究方向、过期招募的历史回答、当前招募拒答、开放期报名及不适用年级。 | 27 通过，1 个要求规则快照与 `main` 字节一致的用例未选中 |

在仓库根目录运行基础回归。

```powershell
.venv/Scripts/python.exe -m pytest -q tests --tb=short
.venv/Scripts/python.exe -m examples.agent_workflow_demo
```

联调快照位于临时目录。使用 `git show <ref>:<path>` 将源码按下表保存并将 `ALPHA_UPSTREAM_SNAPSHOT` 指向目录。

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

- S4 规则目前在上游 Beta 分支。合入 `main` 后需通过正式 `/api/v1/ask` 入口复跑联调。涉及历年报名的资料需明确适用年度和对象。若业务规则拒绝仅写年份的已替代政策查询，请与规则负责人核对历史意图条件。
- 本地正式 `approved/` 暂无已审核资料包，且本地执行环境未配置 `QWEN_API_KEY`。真实政策和真实 Qwen 的四领域验收仍待具备这些输入后执行。
