# CodeMind-FZU Beta 冲刺 · 测试计划（第一阶段）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Beta 冲刺（2026-11-23 至 2026-12-06）
> 规范基线：《CodeMind-FZU Beta 接口规范 V2.1-Final》
> 分支：`test/beta-e2e`
> 状态：**第一阶段测试准备**（核心功能尚未集成）

---

## 一、测试策略（三阶段）

按任务书分三阶段推进，Mock / 合成资料 / 真实 Qwen 三类结果**严格分开记录**：

| 阶段 | 内容 | 当前状态 |
| --- | --- | --- |
| 第一阶段：测试准备 | 场景整理、Fixture、契约测试、Qwen 非法输出测试 | ✅ 进行中（本文档 + 契约测试 + Qwen 输出校验） |
| 第二阶段：模块联调 | 随成员合并逐步接入，记录失败案例反馈 | ⏳ 待上游 |
| 第三阶段：最终 E2E 验收 | 真实资料 + 真实 Qwen + 完整链路 + 最终报告 | ⏳ 待上游 |

**关键原则**：
1. 不依赖尚未实现的功能写测试；不能为了 CI 变绿而删测试或降标准。
2. 测试不通过就保留在测试分支，如实标注「待上游集成」。
3. 不擅自修改吴诗莹、王智洋、雷葭雨、赵紫龙的生产代码，发现问题只反馈。

---

## 二、四大业务领域测试用例（S1-S4）

每个场景统一采用**双测试设计**（与 S3 一致）：

- **真实资料**（`retrieval_status` 非 enabled、未通过人工审核）→ 必须预期 `insufficient_evidence`，不绕过审核门禁。
- **审核通过的合成 Fixture**（明确标注为测试 Fixture，不冒充真实政策资料）→ 验证正常 `answered + citation` 路径。

### S1 竞赛认定（创新学分、综测加分）

> 现有官方资料：`knowledge_base/processed/alpha/competition-recognition-2026.json`
> （`retrieval_status=blocked`、`source=partial`、`timeliness=pending`，**未审核未开放**）。

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S1-1 | 「蓝桥杯是国家级竞赛吗？」（真实资料，未审核未开放） | insufficient_evidence（不绕过审核门禁） |
| S1-1b | 「蓝桥杯是国家级竞赛吗？」（审核通过的测试 Fixture） | answered + 引用竞赛级别认定目录 |
| S1-2 | 「竞赛认定」 | needs_clarification（追问具体竞赛/用途） |
| S1-3 | 「XXX 竞赛是什么级别？」（库中无） | insufficient_evidence |
| S1-4 | 正常问答的 citation 溯源 | chunk_id 映射真实 RetrievedChunk，原文逐字一致 |
| S1-5 | 已废止的旧版竞赛认定办法 | historical，不冒充当前 |

### S2 奖学金申请

> 现有官方资料：`knowledge_base/processed/alpha/scholarship-2026.json`
> （`retrieval_status=blocked`、`source=pending`、`timeliness=pending`，**未审核未开放**）。

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S2-1 | 「优秀学生综合奖学金申请需要什么材料？」（真实资料，未审核未开放） | insufficient_evidence（不绕过审核门禁） |
| S2-1b | 「优秀学生综合奖学金申请需要什么材料？」（审核通过的测试 Fixture） | answered + 引用奖学金办法 |
| S2-2 | 「奖学金怎么申请？」 | needs_clarification（追问校级/国家/院级） |
| S2-3 | 「XX 奖学金」（库中无） | insufficient_evidence |
| S2-4 | citation 溯源 | 引用原文逐字一致 |
| S2-5 | 2024 旧版奖学金办法 | historical，不冒充 2026 现行 |

### S3 推免条件咨询

> 现有官方资料：`knowledge_base/processed/alpha/recommendation-eligibility-2027.json`，
> 对应「计算机与大数据学院（软件学院）2027 年推荐优秀应届本科毕业生免试攻读研究生工作方案」。
> 该资料当前 `retrieval_status=blocked`、`source_verification_status=partial`、
> `timeliness_verification_status=pending`（**未审核、未开放**）。

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S3-1 | 「计算机学院 2027 届推免资格条件？」（真实资料，未审核未开放） | insufficient_evidence（不能直接回答，不绕过审核门禁） |
| S3-1b | 「计算机学院 2027 届推免资格条件？」（审核通过的测试 Fixture） | answered + 引用推荐资格方案 |
| S3-2 | 「推免」 | needs_clarification（追问届别/学院） |
| S3-3 | 「2030 届推免条件」（库中无） | insufficient_evidence |
| S3-4 | citation 溯源 | 引用原文逐字一致 |
| S3-5 | 已过申请期的往年推免方案 | historical + 标注届别 |

### S4 学院资源导航（Beta 新增）

> 现有资料：2026—2027 学年青禾计划（XLSX 附件，尚未核验入库，当前无 approved 正式资料）。
> 使用青禾计划资料时，必须明确其**年度（2026—2027 学年）与截止时间**，不得把
> 历史招募信息描述为「当前仍在招募」。

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S4-1 | 「计算机学院有哪些实验室？」（真实资料，未核验未开放） | insufficient_evidence（不绕过审核门禁） |
| S4-1b | 「计算机学院有哪些实验室？」（审核通过的测试 Fixture） | answered + 引用官方资源目录 |
| S4-2 | 「实验室」（无明确范围） | needs_clarification（追问资源类型/适用对象，仅当确实影响结果） |
| S4-3 | 「某实验室报名」（库中无） | insufficient_evidence |
| S4-4 | citation 溯源 | 引用官方来源 URL |
| S4-5 | 往年实验室招募通知 | 不得描述为「当前仍在招募」，须标注年度与截止时间 |

> **统一说明**：S1-1/S2-1/S3-1/S4-1 用真实资料（未审核未开放）验证
> `insufficient_evidence`；S1-1b/S2-1b/S3-1b/S4-1b 用审核通过的合成 Fixture
> 验证 `answered + citation`。不得为让正向测试通过而绕过资料审核门禁。

---

## 三、历史政策专项测试（Beta 重点）

| 用例 | 输入 | 预期 answer_mode |
| --- | --- | --- |
| H-1 | 当前有效政策 | `current_policy` |
| H-2 | 已结束年度通知，问历史情况 | `historical`（可作为历史信息回答） |
| H-3 | 已被新政策替代的旧政策 | `historical` + 说明已被替代，不冒充当前 |
| H-4 | 未来年度、库中无资料 | `insufficient_evidence`（正确拒答） |
| H-5 | 未说明年度且年度影响答案 | `needs_clarification`（主动追问年度） |
| H-6 | 历史回答明确标记年度 + 适用范围 | 回答含对应年度 + 失效/替代说明 |

**核心原则**：历史资料 ≠ 无效资料；关键是不能把历史信息描述成现行政策。

---

## 四、Qwen 受约束生成与引用安全测试（V2.1 新增）

模型内部输出格式：

```json
{"answer": "基于已提供证据形成的自然语言回答。", "used_evidence_ids": ["E1", "E2"]}
```

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| Q-1 | 正常 JSON 输出 | 格式与 evidence_id 合法性校验通过（**仅验证格式/ID，不验证 ID→Citation 映射**） |
| Q-2 | 非法 JSON | 拒绝 |
| Q-3 | 缺 `answer` 字段 | 拒绝 |
| Q-4 | `answer` 为空 | 拒绝 |
| Q-5 | 缺 `used_evidence_ids` | 拒绝 |
| Q-6 | 引用不存在的 evidence_id | 拒绝 |
| Q-7 | 引用 ID 不属于本次证据集合（同一次请求内） | 拒绝 |
| Q-8 | 两个不同请求的证据集合，引用对方请求的 ID | 拒绝（真正验证跨请求 ID 隔离） |
| Q-9 | 模型自行生成 Citation / 来源 URL | 拒绝 |
| Q-10 | 回答含证据无法支持的确定性结论 | 拒绝/降级 insufficient_evidence |
| Q-11 | 模型试图引用未审核/未开放资料 | 拒绝 |

**核心原则**：Citation 必须由 Agent 根据真实 RetrievedChunk 构造，不直接信任 Qwen 返回的引用；证据 ID 合法 ≠ 答案正确，须检查答案与原文一致。

> **边界说明（重要）**：
> - 当前 `tests/test_beta_qwen_output.py` 的参考校验函数只覆盖 **Q-1~Q-9 的「格式 +
>   evidence_id 合法性」**，**不包含**「ID 映射到真实 RetrievedChunk → 构造 Citation」
>   的完整过程（这需要 Agent 生产实现，属后续集成测试）。
> - Q-7 与 Q-8 的区别：Q-7 是**同一次请求内**引用一个不属于本次可用集合的 ID；
>   Q-8 是**两个不同请求**各自持有独立证据集合，用对方请求的 ID 验证跨请求隔离。
> - Q-10（事实一致性）需接真实证据后补测，属于后续阶段。

---

## 五、检索与证据门禁测试

| 用例 | 检查点 |
| --- | --- |
| R-1 | BM25 正常召回 |
| R-2 | 无匹配返回空列表 |
| R-3 | `get_document_metadata` 元数据查询正确 |
| R-4 | `get_parsed_chunk` 章节查询正确 |
| R-5 | 未审核资料（human_approved≠true）不能进入正式回答 |
| R-6 | `retrieval_status` 非 enabled 不能进入正式回答 |
| R-7 | 来源核验失败（source≠verified）不能使用 |
| R-8 | 资料适用范围不符不能作为证据 |
| R-9 | 多业务方向问题不因错误单一分类漏掉资料 |

> 当前：R-1~R-9 的底层检索能力在 Alpha 已实现（`test_local_retrieval.py`）。
> 注意：公共 `Retriever Protocol`（`backend/contracts/protocols.py`）目前只声明了
> `retrieve`，`get_document_metadata` / `get_parsed_chunk` 两方法待王智洋补齐后，
> 再补充公共 Protocol 的三方法契约测试（V2.1 §8.4）。本测试计划当前只检查
> `LocalBM25Retriever` 实现类，不擅自修改他人负责的公共接口。

---

## 六、模型与后端异常测试

| 用例 | 预期 |
| --- | --- |
| E-1 模型超时 | 504 MODEL_TIMEOUT |
| E-2 模型限流 | 429 RATE_LIMITED |
| E-3 API Key 错误 | 503 SERVICE_NOT_CONFIGURED |
| E-4 模型服务不可用 | 503 MODEL_UNAVAILABLE |
| E-5 知识库不可用 | 503 KNOWLEDGE_BASE_UNAVAILABLE |
| E-6 会话 ID 异常 | 400 INVALID_REQUEST |
| E-7 新旧会话历史隔离 | 新会话不继承旧历史 |
| E-8 连续多轮对话 | 正常，历史正确注入 |

---

## 七、AgentResult 契约缺口（待公共接口负责人确认）

对照 V2.1-Final §5.3 / §6.2，以下约束在**当前 `backend/contracts/models.py` 尚未完整落实**，
本测试计划如实记录，不擅自修改公共接口（先反馈给组长协调公共接口负责人）：

| 状态 | 规范要求 | 当前实现现状 | 待补测试 |
| --- | --- | --- | --- |
| `answered` | 必须具有**非空** `answer_mode` | 现有 validator 仅校验 `answer` 非空，未强制 `answer_mode` 非空 | 补充 `answered` 且 `answer_mode=None` 应拒绝 |
| `needs_clarification` | `citations` 必须为空 | 现有 validator 校验 `answer` 为 null、`clarifying_question` 非空，但未显式校验 `citations` 为空 | 补充 `needs_clarification` 携带非空 `citations` 应拒绝 |
| `insufficient_evidence` | 必须说明证据不足原因，且 `citations` 为空 | 现有 validator 校验 `answer_mode=insufficient_data`，但未强制 `warnings` 说明原因、未强制 `citations` 为空 | 补充 `insufficient_evidence` 无原因说明或携带 `citations` 应拒绝 |

> **处理方式**：以上为公共契约缺口，不擅自修改 `backend/contracts/models.py`，
> 已反馈给组长协调公共接口负责人；确认后再补充对应契约测试。

---

## 八、已完成 / 待办清单

### 已完成（第一阶段）

- [x] `tests/test_beta_contracts.py`：V2.1 契约测试（AnswerMode 四枚举、AgentResult 三状态、LocalBM25Retriever 三方法实现检查、时效/检索状态枚举）
- [x] `tests/test_beta_qwen_output.py`：Qwen 受约束输出格式 + 证据 ID 安全校验规则测试

### 待办（需上游集成后接入）

- [ ] S1-S4 真实 E2E 测试（`test_beta_e2e.py`，等雷葭雨 S4 规则 + 吴诗莹工作流）
- [ ] 历史政策专项测试（等吴诗莹调整 `_eligible` 支持 historical/superseded/expired）
- [ ] Qwen 受约束生成真实校验（等赵紫龙/吴诗莹实现 evidence_id 机制）
- [ ] 检索门禁 + 异常测试接入真实模块
- [ ] 公共 Retriever Protocol 三方法契约测试（等王智洋补齐 Protocol 后补充）

---

## 九、协作对接清单

| 成员 | 需确认 |
| --- | --- |
| 王智洋 | Retriever Protocol 三方法正式纳入、测试数据、元数据/章节查询 |
| 雷葭雨 | S1-S4 业务规则及边界条件、S4 资源分类 |
| 吴诗莹 | AgentWorkflow 历史政策处理、evidence_id 校验行为 |
| 赵紫龙 | Qwen 调用、受约束生成、模型异常处理 |
