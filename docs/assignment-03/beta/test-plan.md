# CodeMind-FZU Beta 冲刺 · 测试计划（Draft）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Beta 冲刺（2026-11-23 至 2026-12-06）
> 规范基线：《CodeMind-FZU Beta 接口规范 V2.1-Final》
> 分支：`test/beta-e2e`
> 状态：**Draft**（第一阶段测试准备，核心功能尚未集成）

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
2. 测试不通过就保留在 Draft PR，如实标注「待上游集成」。
3. 不擅自修改吴诗莹、王智洋、雷葭雨、赵紫龙的生产代码，发现问题只反馈。

---

## 二、四大业务领域测试用例（S1-S4）

每个场景至少覆盖 5 类断言：正常回答 / 缺信息追问 / 证据不足 / 正确引用 / 过期资料不冒充当前。

### S1 竞赛认定（创新学分、综测加分）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S1-1 | 「蓝桥杯是国家级竞赛吗？能认定创新学分吗？」 | answered + 引用竞赛级别认定目录 |
| S1-2 | 「竞赛认定」 | needs_clarification（追问具体竞赛/用途） |
| S1-3 | 「XXX 竞赛是什么级别？」（库中无） | insufficient_evidence |
| S1-4 | 正常问答的 citation 溯源 | chunk_id 映射真实 RetrievedChunk，原文逐字一致 |
| S1-5 | 已废止的旧版竞赛认定办法 | historical，不冒充当前 |

### S2 奖学金申请

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S2-1 | 「优秀学生综合奖学金申请需要什么材料？」 | answered + 引用奖学金办法 |
| S2-2 | 「奖学金怎么申请？」 | needs_clarification（追问校级/国家/院级） |
| S2-3 | 「XX 奖学金」（库中无） | insufficient_evidence |
| S2-4 | citation 溯源 | 引用原文逐字一致 |
| S2-5 | 2024 旧版奖学金办法 | historical，不冒充 2026 现行 |

### S3 推免条件咨询

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S3-1 | 「计算机学院 2026 届推免资格条件？」 | answered + 引用推荐资格方案 |
| S3-2 | 「推免」 | needs_clarification（追问届别/学院） |
| S3-3 | 「未来年度推免条件」（库中无） | insufficient_evidence |
| S3-4 | citation 溯源 | 引用原文逐字一致 |
| S3-5 | 已过申请期的往年推免方案 | historical + 标注届别 |

### S4 学院资源导航（Beta 新增）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| S4-1 | 「计算机学院有哪些实验室？」 | answered + 引用官方资源目录 |
| S4-2 | 「实验室」（无明确范围） | needs_clarification（追问资源类型/适用对象，仅当确实影响结果） |
| S4-3 | 「某实验室报名」（库中无） | insufficient_evidence |
| S4-4 | citation 溯源 | 引用官方来源 URL |
| S4-5 | 往年实验室招募通知 | 不得描述为「当前仍在招募」 |

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
| Q-1 | 正常 JSON | 通过，Agent 映射 ID → 构造 Citation |
| Q-2 | 非法 JSON | 拒绝 |
| Q-3 | 缺 `answer` 字段 | 拒绝 |
| Q-4 | `answer` 为空 | 拒绝 |
| Q-5 | 缺 `used_evidence_ids` | 拒绝 |
| Q-6 | 引用不存在 evidence_id | 拒绝 |
| Q-7 | 引用不属于本次请求的 evidence_id | 拒绝 |
| Q-8 | 引用其他请求的证据 ID | 拒绝 |
| Q-9 | 模型自行生成 Citation / 来源 URL | 拒绝 |
| Q-10 | 回答含证据无法支持的确定性结论 | 拒绝/降级 insufficient_evidence |
| Q-11 | 模型试图引用未审核/未开放资料 | 拒绝 |

**核心原则**：Citation 必须由 Agent 根据真实 RetrievedChunk 构造，不直接信任 Qwen 返回的引用；证据 ID 合法 ≠ 答案正确，须检查答案与原文一致。

> 当前进度：Q-1~Q-9 的格式/ID 校验规则已在 `tests/test_beta_qwen_output.py` 用参考校验函数固化（Draft 阶段，非生产实现）。Q-10（事实一致性）需在 Final 阶段接真实证据后补测。

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

> 当前：R-1~R-9 的底层检索能力在 Alpha 已实现（`test_local_retrieval.py`），Beta 需配合王智洋确认 Retriever Protocol 三方法正式纳入（V2.1 §8.4）。

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

## 七、已完成 / 待办清单

### 已完成（Draft 阶段）

- [x] `tests/test_beta_contracts.py`：V2.1 契约测试（AnswerMode 四枚举、AgentResult 三状态、Retriever 三方法、时效/检索状态枚举）
- [x] `tests/test_beta_qwen_output.py`：Qwen 受约束输出格式 + 证据 ID 安全校验规则测试

### 待办（需上游集成后接入）

- [ ] S1-S4 真实 E2E 测试（`test_beta_e2e.py`，等雷葭雨 S4 规则 + 吴诗莹工作流）
- [ ] 历史政策专项测试（等吴诗莹调整 `_eligible` 支持 historical/superseded/expired）
- [ ] Qwen 受约束生成真实校验（等赵紫龙/吴诗莹实现 evidence_id 机制）
- [ ] 检索门禁 + 异常测试接入真实模块

---

## 八、协作对接清单

| 成员 | 需确认 |
| --- | --- |
| 王智洋 | Retriever Protocol 三方法正式纳入、测试数据、元数据/章节查询 |
| 雷葭雨 | S1-S4 业务规则及边界条件、S4 资源分类 |
| 吴诗莹 | AgentWorkflow 历史政策处理、evidence_id 校验行为 |
| 赵紫龙 | Qwen 调用、受约束生成、模型异常处理 |
