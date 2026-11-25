# CodeMind-FZU Beta 冲刺 · 测试计划

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Beta 冲刺（2026-11-23 至 2026-12-06）
> 规范基线：《CodeMind-FZU Beta 接口规范 V2.1-Final》
> 分支：`test/beta-e2e`
> 状态：**第二阶段模块联调**（#45/#46/#49/#51/#55/#56/#57 已合并）

---

## 一、测试策略（三阶段）

按任务书分三阶段推进，Mock / 合成资料 / 真实 Qwen 三类结果**严格分开记录**：

| 阶段 | 内容 | 当前状态 |
| --- | --- | --- |
| 第一阶段：测试准备 | 场景整理、Fixture、契约测试、Qwen 非法输出测试 | ✅ 完成（契约测试 + verify_answer 黑盒测试 + 本计划） |
| 第二阶段：模块联调 | 随成员合并逐步接入，记录失败案例反馈 | ✅ 进行中（#45/#46/#49/#51/#55 已合并，可独立联调） |
| 第三阶段：最终 E2E 验收 | 真实资料 + 真实 Qwen + 完整链路 + 最终报告 | ⏳ 待正式资料签核 + 真实 Qwen |

**关键原则**：
1. 不依赖尚未实现的功能写测试；不能为了 CI 变绿而删测试或降标准。
2. 测试不通过就保留在测试分支，如实标注「待上游集成」。
3. 不擅自修改吴诗莹、王智洋、雷葭雨、赵紫龙的生产代码，发现问题只反馈。

---

## 二、模块状态与资料现状（同步最新 main `0251ec5`）

### 2.1 已合并模块

| PR | 模块 | 状态 |
| --- | --- | --- |
| #45 | 业务规则（S4 资源分类收紧、官方来源核对） | ✅ 已合并 |
| #46 | AgentWorkflow 历史政策处理 + 证据校验 | ✅ 已合并（`verify_answer` 生产实现就绪） |
| #49 | Beta Runtime + Qwen 适配器（stage 1） | ✅ 已合并 |
| #51 | Retriever Protocol 三方法正式纳入 | ✅ 已合并 |
| #55 | 公共响应契约（AgentResult / AskResponse shape 强制） | ✅ 已合并 |
| #56 | 候选资料范围受限人工签核（保持检索 blocked） | ✅ 已合并 |
| #57 | 2027 届推免志愿服务原始分口径 | ✅ 已合并 |

> 未合并：#53（复审整改中）。

### 2.2 正式候选资料（#41，审核状态由 #56 更新）

#41 交付的四领域候选资料位于
`knowledge_base/processed/alpha/pending-review/beta-2026-11-23/`，manifest 统计为
**8 包、501 片段**（qinghe 青禾计划另有 r3/r4 拆分目录）。

审核状态（#56 后）：

- `human_approved_packages = 6`（**6 个包已有范围受限的人工签核**）
- `enabled_packages = 0`（**0 个正式开放检索**）
- 全部包 `retrieval_status = blocked`

| 包 | record_code | 片段数 | 人工签核 | 检索状态 |
| --- | --- | --- | --- | --- |
| 竞赛项目级别认定 | 福大-2026-竞赛项目级别认定 | 224 | ✅ 已签核（范围受限） | blocked |
| 本科奖学金 | 福大-2026-本科奖学金 | 59 | ✅ 已签核（范围受限） | blocked |
| 院级奖学金 | 计算机学院-2026-院级奖学金 | 33 | ✅ 已签核（范围受限） | blocked |
| 星火奖学金 | 计算机学院-2026-星火奖学金 | 35 | ✅ 已签核（范围受限） | blocked |
| 创新创业学分认定 | 福大-2024-创新创业学分认定 | 86 | ✅ 已签核（范围受限） | blocked |
| 推免复试参考 | 计算机学院-2026-推免复试参考 | 9 | ✅ 已签核（范围受限） | blocked |
| 推免资格推荐 | 计算机学院-2027-推免资格推荐 | 20 | ❌ 未签核 | blocked |
| 青禾计划 | 计算机学院-2026-青禾计划 | 35 | ❌ 未签核 | blocked |

> **重要（边界澄清）**：**人工签核 ≠ 正式检索放行**。6 个包虽有范围受限的
> 人工签核，但 `retrieval_status` 仍全部为 `blocked`、`enabled_packages=0`，
> **仍不能进入正式问答**。第二阶段联调用合成 Fixture 验证技术链路；真实资料 +
> 真实 Qwen 的完整 E2E 验收，留待资料正式开放检索后。

---

## 三、四大业务领域测试用例（S1-S4）

每个场景统一采用**双测试设计**：

- **真实资料**（blocked、未签核）→ 必须预期 `insufficient_evidence`，不绕过审核门禁。
- **审核通过的合成 Fixture**（明确标注测试 Fixture）→ 验证正常 `answered + citation`。

### S1 竞赛认定（创新学分、综测加分）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S1-1 | 「蓝桥杯是国家级竞赛吗？」（真实资料 blocked） | insufficient_evidence（不绕过审核门禁） |
| S1-1b | 「蓝桥杯是国家级竞赛吗？」（审核 Fixture） | answered + 引用竞赛级别认定目录 |
| S1-2 | 「竞赛认定」 | needs_clarification（追问具体竞赛/用途） |
| S1-3 | 「XXX 竞赛是什么级别？」（库中无） | insufficient_evidence |
| S1-4 | citation 溯源 | chunk_id 映射真实 RetrievedChunk，原文逐字一致 |
| S1-5 | 已废止的旧版竞赛认定办法（福大-2024 创新创业学分） | historical，不冒充当前 |

### S2 奖学金申请

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S2-1 | 「优秀学生综合奖学金申请需要什么材料？」（真实资料 blocked） | insufficient_evidence |
| S2-1b | 「优秀学生综合奖学金申请需要什么材料？」（审核 Fixture） | answered + 引用奖学金办法 |
| S2-2 | 「奖学金怎么申请？」 | needs_clarification（追问校级/国家/院级） |
| S2-3 | 「XX 奖学金」（库中无） | insufficient_evidence |
| S2-4 | citation 溯源 | 引用原文逐字一致 |
| S2-5 | 旧版奖学金办法 | historical，不冒充现行 |

### S3 推免条件咨询

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S3-1 | 「计算机学院 2027 届推免资格条件？」（真实资料 blocked） | insufficient_evidence |
| S3-1b | 「计算机学院 2027 届推免资格条件？」（审核 Fixture） | answered + 引用推荐资格方案 |
| S3-2 | 「推免」 | needs_clarification（追问届别/学院） |
| S3-3 | 「2030 届推免条件」（库中无） | insufficient_evidence |
| S3-4 | citation 溯源 | 引用原文逐字一致 |
| S3-5 | 已过申请期的往年推免方案 | historical + 标注届别 |

### S4 学院资源导航（Beta 新增）

> 青禾计划资料（`qinghe`）须明确**年度（2026—2027 学年）与截止时间**，
> 不得把历史招募信息描述为「当前仍在招募」。

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S4-1 | 「计算机学院有哪些实验室？」（真实资料 blocked） | insufficient_evidence |
| S4-1b | 「计算机学院有哪些实验室？」（审核 Fixture） | answered + 引用官方资源目录 |
| S4-2 | 「实验室」（无明确范围） | needs_clarification（追问资源类型/适用对象） |
| S4-3 | 「某实验室报名」（库中无） | insufficient_evidence |
| S4-4 | citation 溯源 | 引用官方来源 URL |
| S4-5 | **历史招募通知** | 不得描述为「当前仍在招募」，须标注年度与截止时间 |
| S4-6 | **实时名额查询**（如「青禾计划还有几个名额？」） | 无官方实时名额资料时拒答 / insufficient_evidence |
| S4-7 | **中文实验室名称**（如「机器学习与数据挖掘实验室」） | 正确召回中文名称对应的实验室（不因分词/编码问题漏召回） |
| S4-8 | **多轮主题切换**（先问实验室，再问奖学金） | 新主题不污染场景识别，历史上下文正确切换 |
| S4-9 | **混合事项**（一句问含实验室 + 奖学金） | 分项回答或明确提示部分无法确认，不串答 |

> **统一说明**：S1-1/S2-1/S3-1/S4-1 用真实资料（blocked）验证 insufficient_evidence；
> S1-1b/S2-1b/S3-1b/S4-1b 用审核 Fixture 验证 answered + citation。S4-5~S4-9 为
> 本轮新增验收边界（历史招募、实时名额、中文名称、多轮切换、混合事项）。
> **团队分类口径（业务方向代码）暂时等待雷葭雨和吴诗莹确认。**

---

## 四、历史政策专项测试（Beta 重点）

| 用例 | 输入 | 预期 answer_mode |
| --- | --- | --- |
| H-1 | 当前有效政策 | `current_policy` |
| H-2 | 已结束年度通知，问历史情况 | `historical`（可作为历史信息回答） |
| H-3 | 已被新政策替代的旧政策 | `historical` + 说明已被替代，不冒充当前 |
| H-4 | 未来年度、库中无资料 | `insufficient_evidence`（正确拒答） |
| H-5 | 未说明年度且年度影响答案 | `needs_clarification`（主动追问年度） |
| H-6 | 历史回答明确标记年度 + 适用范围 | 回答含对应年度 + 失效/替代说明 |

**核心原则**：历史资料 ≠ 无效资料；关键是不能把历史信息描述成现行政策。

> **实现状态**：#46 已合并，AgentWorkflow 已支持 `HISTORICAL` / `SUPERSEDED` /
> `EXPIRED` / `PROCEDURE_REFERENCE` 四种 answer_mode（见 `agent_workflow.py`）。
> 吴诗莹的 `test_agent_workflow.py` / `test_agent_workflow_qwen.py` 已覆盖大量
> 历史政策场景，本计划不再重复，第二阶段联调时核对覆盖、补缺失边界。

---

## 五、Qwen 受约束生成与引用安全测试（V2.1 新增）

模型内部输出格式：

```json
{"answer": "基于已提供证据形成的自然语言回答。", "used_evidence_ids": ["E1", "E2"]}
```

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| Q-1 | 正常 JSON 输出 | 格式 + evidence_id 合法性校验通过 |
| Q-2 | 非法 JSON | 拒绝 |
| Q-3 | 缺 `answer` 字段 | 拒绝 |
| Q-4 | `answer` 为空 | 拒绝 |
| Q-5 | 缺 `used_evidence_ids` | 拒绝 |
| Q-6 | 引用不存在的 evidence_id | 拒绝 |
| Q-7 | 引用不属于本次证据集合的 evidence_id | 拒绝 |
| Q-8 | 引用另一请求的 evidence_id（跨请求） | 拒绝 |
| Q-9 | 模型自行生成 Citation / 来源 URL / 额外字段 | 拒绝 |
| Q-10 | 答案改写原文 / 含证据无法支持的额外文本 | 拒绝 |
| Q-11 | 请求金额/日期事实未被所选证据覆盖 | 拒绝 |

**核心原则**：Citation 必须由 Agent 根据真实 RetrievedChunk 构造，不直接信任 Qwen
返回的引用；证据 ID 合法 ≠ 答案正确，须检查答案与原文一致。

> **实现状态（更新）**：#46 已合并，生产 `verify_answer()`（
> `backend/services/agent_generation.py`）已实现全部上述校验。本计划的
> `tests/test_beta_qwen_output.py` 已从「参考校验函数」改为**直接对生产
> `verify_answer()` 做独立黑盒测试**（17 用例），覆盖格式/ID/答案一致性/事实覆盖。
> 吴诗莹的 `test_agent_workflow.py` 通过 workflow 集成层覆盖了跨请求证据隔离
> （`test_model_cannot_select_filtered_or_previous_round_evidence`）等，不重复。

---

## 六、检索与证据门禁测试

| 用例 | 检查点 | 层次 | 已有测试 |
| --- | --- | --- | --- |
| R-1 | BM25 正常召回 | BM25 检索 | `test_local_retrieval.py` |
| R-2 | 无匹配返回空列表 | BM25 检索 | `test_local_retrieval.py` |
| R-3 | `get_document_metadata` 元数据查询正确 | BM25 检索 | `test_local_retrieval.py` + `test_beta_contracts.py` |
| R-4 | `get_parsed_chunk` 章节查询正确 | BM25 检索 | `test_local_retrieval.py` + `test_beta_contracts.py` |
| R-5 | 未审核资料不能进入正式回答 | 业务证据门禁 | `test_alpha_business_rules.py` |
| R-6 | `retrieval_status` 非 enabled 不能进入 | 业务证据门禁 | `test_alpha_business_rules.py` |
| R-7 | 来源核验失败不能使用 | 业务证据门禁 | `test_alpha_business_rules.py` |
| R-8 | 资料适用范围不符不能作为证据 | 业务证据门禁 | `test_alpha_business_rules.py` |
| R-9 | 未明确业务方向时不擅自单一方向过滤 | Agent 工作流 | `test_agent_workflow.py` / `test_agent_workflow_qwen.py` |

> 公共 `Retriever Protocol` 三方法已由 #51 纳入，签名一致性测试在
> `test_local_retrieval.py` / `test_interface_contracts.py`。

---

## 七、公共响应契约（#55 已修复，含反向用例清单）

### 7.1 契约约束与修复状态

对照 V2.1 §5.3 / §6.2，#55 已修复 `AgentResult` 与 `AskResponse` 的响应 shape 校验：

| 状态 | 规范要求 | 修复状态 | 已有测试 |
| --- | --- | --- | --- |
| `answered` | `answer` 非空 + `answer_mode` 非空 | ✅ 已修复 | `test_beta_response_contract_validation.py::test_answered_requires_explicit_mode` |
| `needs_clarification` | `answer`=null、`answer_mode`=null、`clarifying_question` 非空、`citations` 为空 | ✅ 已修复 | `test_beta_response_contract_validation.py::test_clarification_rejects_incompatible_fields` |
| `insufficient_evidence` | `answer_mode`=insufficient_data、说明原因、`citations` 为空 | ✅ 已修复 | `test_beta_response_contract_validation.py::test_insufficient_rejects_citations` / `test_insufficient_requires_reason` |

### 7.2 反向用例清单（记录用，非本 PR 测试代码）

以下反向用例用于固化契约边界，已由 #55 的测试覆盖，本 PR 不重复编写：

| 反向用例 | 期望拒绝 |
| --- | --- |
| `answered` + `answer_mode=None` | ValidationError |
| `needs_clarification` + 非空 `answer_mode` | ValidationError |
| `needs_clarification` + 非空 `citations` | ValidationError |
| `insufficient_evidence` + 非 `insufficient_data` mode | ValidationError |
| `insufficient_evidence` + 非空 `citations` | ValidationError |
| `insufficient_evidence` + 无原因说明 | ValidationError |

> 说明：这些反向用例**不降低测试标准**，也**不自行修改公共 DTO**——由组长协调
> 公共契约负责人（#55）修复，本计划仅记录边界与对应测试位置。

---

## 八、已完成 / 待办清单

### 已完成（第一阶段 + 第二阶段进行中）

- [x] `tests/test_beta_contracts.py`：V2.1 契约测试（AnswerMode/AgentResult/Retriever 实现类/状态枚举）
- [x] `tests/test_beta_qwen_output.py`：生产 `verify_answer()` 独立黑盒测试（17 用例）
- [x] 同步最新 main（`0251ec5`），#45/#46/#49/#51/#55 已合并
- [x] test-plan.md 更新资料路径、模块状态、S4 新增边界用例

### 待办（第三阶段 + 后续 PR）

- [ ] S1-S4 真实资料 + 真实 Qwen 完整 E2E（待资料签核）
- [ ] 正式资料签核后，将 blocked 候选资料转 enabled 的正向验收
- [ ] 团队分类口径（业务方向代码）确认后，补多业务方向检索测试
- [ ] 最终 E2E 验收报告

> #46 合并后，另开测试 PR 将 Qwen 校验测试接入实际生产实现（本 PR 已用生产
> `verify_answer` 完成独立黑盒测试，后续核对吴诗莹覆盖、补真正缺失边界，不重复）。

---

## 九、协作对接清单

| 成员 | 需确认 |
| --- | --- |
| 王智洋 | 候选资料签核、元数据/章节查询（Protocol 已 #51 纳入） |
| 雷葭雨 | S1-S4 业务规则边界、S4 资源分类、团队分类口径 |
| 吴诗莹 | AgentWorkflow 历史政策、evidence_id 校验（已 #46 合并，核对覆盖） |
| 赵紫龙 | Qwen 调用、受约束生成、模型异常（已 #49 合并） |
| 组长 | 公共契约修复（已 #55）、正式资料最终签核 |
