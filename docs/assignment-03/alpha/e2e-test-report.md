# CodeMind-FZU Alpha 冲刺 · 端到端测试报告（E2E）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Alpha 冲刺（真实模块集成阶段）
> 分支：`test/alpha-e2e`
> 测试基线：`main` = `f5fcabc`（含 #26 真实本地检索 `LocalBM25Retriever`）
> 测试文件：`tests/test_alpha_e2e.py`（新增）

---

## 1. 目标

本轮从「单元/接口契约测试」升级到「真实业务链路端到端测试」，验证这条完整链路：

```
学生提问 → FastAPI /api/v1/ask → AgentWorkflow → 业务规则 → 真实 BM25 检索
        → Qwen 证据选择 → Citation 逐字校验 → 返回结果
```

重点是证明 **Alpha 系统能真正运行**，同时**让每项测试真正验证自己声称的内容**，
不把组件级测试、Mock 测试和完整端到端测试混为一谈。

---

## 2. 测试环境

| 项目 | 值 |
| --- | --- |
| Python | 3.13.12 |
| fastapi | 0.141.1 |
| pydantic | 2.13.5 |
| httpx | 0.28.1 |
| 平台 | Windows 11 |
| 检索 | 真实 `LocalBM25Retriever`（中文 bigram BM25） |
| Qwen | httpx `MockTransport` 离线替身（不依赖真实 API） |
| HTTP | `fastapi.testclient.TestClient`（真实 FastAPI 应用） |

---

## 3. 测试分类（统计口径不得混淆）

| 类别 | 定义 | 本文件对应 | 结果 |
| --- | --- | --- | --- |
| **第一类 Mock** | 全替身（Mock Retriever + Mock LLM） | 其他 `test_*.py` | 已覆盖 |
| **第二类 真实资料** | 真实 DocumentPackage + 真实 BM25 + Mock Qwen | `AlphaE2ETests`（T1/T2/T3/T4空库/T5/T7/T8/T9）+ `AlphaE2EMultiTurnTests`（T10） | ✅ 10 通过 |
| **证据准入规则测试** | 自定义 SingleChunkRetriever 验证 `_eligible` 门槛（**非 BM25 端到端**） | `AgentWorkflowEvidenceGateTests`（T6） | ✅ 1 通过 |
| **第三类 真实 Qwen** | 真实 Retriever + 真实 Qwen API | `AlphaE2ERealQwenTests` | ⏸ 1 跳过（无 API Key） |

**明确标注的「待实现」项**（`@unittest.skip`，不冒充已通过）：

| 待实现项 | 原因 |
| --- | --- |
| `test_future_year_policy_applicability` | 未来年度政策适用性判定未实现（workflow 仅处理历史年度） |
| `test_conversation_isolation` | 会话持久化/隔离未实现（依赖 `alpha-real-runtime`） |

> **重要结论**：第二类测试证明「真实检索 + 工作流 + 引用校验」链路可运行；
> 但**不能**据此宣称「真实 Agent 已通过验收」——真实 Qwen（第三类）、真实核验资料、
> 会话持久化、未来年度适用性均仍待就绪。Mock 通过 ≠ 真实验收。

---

## 4. T1–T10 执行记录

| 编号 | 场景 | 预期结果 | 实际结果 | 是否通过 | 测试性质 |
| --- | --- | --- | --- | --- | --- |
| T1 | 竞赛认定，存在有效政策 | answered | answered + 可追溯引用 | ✅ | 第二类（测试替身资料） |
| T2 | 奖学金，问金额与评定比例 | answered | answered + 逐字摘录（含 1500元/前10%） | ✅ | 第二类（测试替身资料） |
| T3 | 奖学金但未说明学年 | needs_clarification | needs_clarification | ✅ | 第二类 |
| T4 | 空知识库 | insufficient_evidence | insufficient_evidence（NO_ELIGIBLE_EVIDENCE） | ✅ | 第二类 |
| T4' | 未来年度无适用政策 | insufficient_evidence | ⏸ 跳过（判定未实现） | ⏸ 待实现 | 第二类（skip） |
| T5 | 资料 blocked | insufficient_evidence | insufficient_evidence（NO_ELIGIBLE_EVIDENCE） | ✅ | 第二类 |
| T6 | 来源核验未通过 | 不生成正式回答 | insufficient_evidence | ✅ | 证据准入规则（非 BM25） |
| T7 | Qwen 超时 | 正确返回错误 | 504 MODEL_TIMEOUT | ✅ | 第二类 |
| T8 | 模型返回不存在的 chunk_id | 拒绝该引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T9 | 模型改写原文作引用 | 拒绝该引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T10 | 多轮追问（workflow 层） | 使用此前对话信息 | 第二轮补学年后 answered | ✅ | 第二类 |

**补充用例**：
- `test_followup_without_year_still_clarifies`：第二轮仍未补学年时继续追问（证明不是无条件放行）。

**说明**：
- **T2 修正**：原问题问「申请流程」但资料是「金额/比例」，导致无关证据也能 answered。现改为问「金额与评定比例」，与资料语义匹配，并断言摘录包含关键数字（1500元、前10%）。
- **T4 拆分**：原 `packages=[]` 只验证空知识库，未验证未来年度适用性。现拆为 `T4`（空知识库）与 `T4'`（未来年度，因 workflow 不支持该规则，标记 `skip` 待实现）。
- **T6 归类**：T6 用自定义 `SingleChunkRetriever` 而非 `LocalBM25Retriever`，已归入独立的 `AgentWorkflowEvidenceGateTests` 类，**不计入 BM25 端到端统计**。
- **T10 定位**：T10 直接调用 `workflow.run` 手动传 history，只能证明「workflow 能利用历史上下文」，**不能证明 FastAPI 已实现会话持久化**。已改名 `test_T10_workflow_uses_history_context` 并在报告中明确。
- **会话隔离**：原 `test_different_conversation_ids_are_isolated` 只断言两个 UUID 不相等，无实际意义，已删除，改为 `@unittest.skip` 标记的 `test_conversation_isolation`（待 `alpha-real-runtime` 合入后补测）。

---

## 5. 关键验证点结论

### 5.1 三种业务状态转换（任务二）

- `needs_clarification`：奖学金缺学年时，Agent **先追问**，不调用检索与模型（T3）。
- `insufficient_evidence`：blocked 资料、未核验来源、空知识库，均 fail-closed，不调用 Qwen 生成笼统答案（T4/T5/T6）。
- `answered`：仅在「检索到 enabled + verified + current 片段 + Qwen 逐字选中」后才返回，且带 `ALPHA_EXTRACTIVE_ANSWER` 警告（T1/T2）。

### 5.2 Citation 引用安全性（任务三）

| 攻击/异常输入 | 系统行为 | 用例 |
| --- | --- | --- |
| 模型返回不存在的 `chunk_id` | 拒绝，`UNSUPPORTED_GENERATION`，不生成回答 | T8 |
| 模型改写原文作为 quote | 拒绝（quote ≠ chunk.content 全等即拒） | T9 |
| 模型自由生成无引用回答 | 拒绝（workflow 只接受 `{"evidence":[...]}` 结构） | 已有 `test_agent_workflow.py` |
| 来源未核验（partial） | `_eligible` 拒绝，`NO_ELIGIBLE_EVIDENCE` | T6 |
| 资料 blocked | 检索器不返回，`NO_ELIGIBLE_EVIDENCE` | T5 |

### 5.3 真实模型/后端异常（任务四）

| 异常 | 系统行为 | 用例 |
| --- | --- | --- |
| Qwen 上游超时 | 504 `MODEL_TIMEOUT`（可重试），不返回业务 answered | T7 |
| API Key 缺失 | `LLMConfigurationError` → 503 `SERVICE_NOT_CONFIGURED` | 已有 `test_qwen_client.py` |
| 模型返回格式非法 | 拒绝，`UNSUPPORTED_GENERATION` | 已有 `test_agent_workflow.py` |
| 知识库为空 | `NO_ELIGIBLE_EVIDENCE` | T4 |

### 5.4 多轮会话（任务五）

- **workflow 层**：第二轮补上学年后，workflow 通过 `history` 合并 user 上下文，跳过追问进入检索并 answered（T10）。此为**组件级验证**。
- **会话持久化/隔离**：**未实现**。当前 `main` 的 AgentWorkflow 无会话持久化，`conversation_id` 仅作为请求字段透传。真正持久化依赖 `feat/alpha-real-runtime` 的 `InMemoryConversationStore`，待合入后补测（已用 `test_conversation_isolation` 占位标记）。

---

## 6. 缺陷与阻塞清单

| 编号 | 问题 | 严重度 | 状态 | 责任方 |
| --- | --- | --- | --- | --- |
| B-1 | `approved/` 目录无正式核验资料，T1/T2 的「真实核验资料 answered」无法验证 | 高 | 阻塞 | 丁晓炜 |
| B-2 | 真实运行装配（`alpha_runtime.py`/`alpha.py`）未合入 main，会话持久化未接入 | 中 | 待合入 | 赵紫龙 |
| B-3 | 真实 Qwen 集成测试需 `QWEN_API_KEY`，当前环境未配置 | 中 | 待配置 | 赵紫龙 |
| B-4 | 业务规则运行时未合入，workflow 用保守默认规则 | 中 | 待合入 | 吴诗莹/丁晓炜 |
| B-5 | **未来年度政策适用性判定未实现**：workflow 仅处理历史年度（today > period_end），对「未来年度」无专门规则 | 中 | 待实现 | 吴诗莹 |

> B-1~B-4 为「模块未交付/未合入」导致的阻塞，B-5 为「功能缺口」（未来年度适用性未实现）。
> 本文件未发现被测代码（AgentWorkflow / LocalBM25Retriever / Qwen 适配器 / FastAPI）在已实现范围内的功能缺陷。

---

## 7. 结论

1. **第二类端到端链路已打通**：真实 BM25 检索 + AgentWorkflow + Qwen 适配器 + FastAPI HTTP 的完整链路，在测试替身资料上能正确完成 T1（竞赛）、T2（奖学金金额）、T3（追问）、T4（空库）、T5（blocked）、T7~T9（异常/引用安全）、T10（多轮）等场景。
2. **三状态机与 Citation 安全校验在真实组件上验证通过**。
3. **每项测试已对齐其真实验证目标**：T6 归入证据准入规则测试、T10 明确为 workflow 层、会话隔离/未来年度标记为「待实现」skip，不再把组件级测试冒充完整端到端。
4. **尚未达到「真实验收」标准**：真实核验资料（B-1）、真实 Qwen（B-3）、会话持久化（B-2）、未来年度适用性（B-5）未就绪，须如实标注。
5. **下一步**：待 `feat/alpha-real-runtime`、`feat/alpha-business-rules` 等合入 main 且 `approved/` 有正式资料后，升级为真实运行时装配 + 真实核验资料，补测会话持久化、未来年度适用性与真实 Qwen。

---

## 8. 复现方式与原始输出

```bash
# 单个文件
python -m unittest tests.test_alpha_e2e -v

# 全量（含本文件）
python -m unittest discover -s tests -v
```

### 8.1 本文件结果

```
Ran 14 tests，11 通过，0 失败，3 跳过
```

3 个跳过：`test_future_year_policy_applicability`（未来年度待实现）、
`test_conversation_isolation`（会话隔离待实现）、`test_real_qwen_end_to_end`（无 API Key）。

### 8.2 全量结果

```
Ran 185 tests in 9.733s
OK (skipped=4)
```

4 个跳过：上述 3 个 + `test_symlink_escaping_storage_root_is_rejected`（Windows 账户无符号链接权限）。

**原始终端输出**：`docs/assignment-03/alpha/evidence/e2e-unittest.txt`
