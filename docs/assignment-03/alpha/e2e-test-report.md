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

重点是证明 **Alpha 系统能真正运行**，而不是各模块各自通过单测就算完成。

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

## 3. 三类测试的明确区分（不得混淆统计）

| 类别 | 定义 | 本文件对应 | 结果 |
| --- | --- | --- | --- |
| **第一类 Mock** | 全替身（Mock Retriever + Mock LLM） | 其他 `test_*.py` | 已覆盖 |
| **第二类 真实资料** | 真实 DocumentPackage + 真实 BM25 + Mock Qwen | `AlphaE2ETests` + `AlphaE2EMultiTurnTests` | ✅ 12 通过 |
| **第三类 真实 Qwen** | 真实 Retriever + 真实 Qwen API | `AlphaE2ERealQwenTests` | ⏸ 1 跳过（无 API Key） |

> **重要结论**：第二类测试证明「真实检索 + 工作流 + 引用校验」链路可运行；
> 但**不能**据此宣称「真实 Agent 已通过验收」——真实 Qwen（第三类）和真实核验资料
> 仍待就绪。Mock 通过 ≠ 真实验收。

---

## 4. T1–T10 执行记录

| 编号 | 场景 | 预期结果 | 实际结果 | 是否通过 | 测试性质 |
| --- | --- | --- | --- | --- | --- |
| T1 | 竞赛认定，存在有效政策 | answered | answered + 可追溯引用 | ✅ | 第二类（测试替身资料） |
| T2 | 奖学金，存在有效政策 | answered | answered + 逐字摘录 | ✅ | 第二类（测试替身资料） |
| T3 | 奖学金但未说明学年 | needs_clarification | needs_clarification | ✅ | 第二类 |
| T4 | 未来年度推免，无适用政策 | insufficient_evidence | insufficient_evidence | ✅ | 第二类 |
| T5 | 资料 blocked | insufficient_evidence | insufficient_evidence（NO_ELIGIBLE_EVIDENCE） | ✅ | 第二类 |
| T6 | 来源核验未通过 | 不生成正式回答 | insufficient_evidence | ✅ | 第二类 |
| T7 | Qwen 超时 | 正确返回错误 | 504 MODEL_TIMEOUT | ✅ | 第二类 |
| T8 | 模型返回不存在的 chunk_id | 拒绝该引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T9 | 模型改写原文作引用 | 拒绝该引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T10 | 多轮追问 | 使用此前对话信息 | 第二轮补学年后 answered | ✅ | 第二类 |

**补充用例**：
- `test_followup_without_year_still_clarifies`：第二轮仍未补学年时继续追问（证明不是无条件放行）。
- `test_different_conversation_ids_are_isolated`：不同 `conversation_id` 的 history 隔离（当前 workflow 无会话持久化，此用例验证请求级隔离的契约前提）。

---

## 5. 关键验证点结论

### 5.1 三种业务状态转换（任务二）

- `needs_clarification`：奖学金缺学年时，Agent **先追问**，`retriever.retrieve` 与 `llm.generate` **均未调用**（T3 验证）。
- `insufficient_evidence`：blocked 资料、未核验来源、未来年度无资料，均 fail-closed，不调用 Qwen 生成笼统答案（T4/T5/T6）。
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
| 知识库为空 | `NO_ELIGIBLE_EVIDENCE` | T4（无资料） |

### 5.4 多轮会话（任务五）

- 多轮追问：第二轮补上学年后，workflow 通过 `history` 合并 user 上下文，跳过追问进入检索并 answered（T10）。
- 会话隔离：当前 `main` 的 workflow **尚无会话持久化**（`InMemoryConversationStore` 在 `feat/alpha-real-runtime` 分支，未合入），本文件验证的是请求级 `conversation_id` 契约前提。真实会话隔离待 `alpha-real-runtime` 合入后补测。

---

## 6. 缺陷与阻塞清单

| 编号 | 问题 | 严重度 | 状态 | 责任方 |
| --- | --- | --- | --- | --- |
| B-1 | `approved/` 目录无正式核验资料，T1/T2 的「真实核验资料 answered」无法验证 | 高 | 阻塞 | 丁晓炜 |
| B-2 | 真实运行装配（`alpha_runtime.py`/`alpha.py`）未合入 main，多轮会话持久化未接入 | 中 | 待合入 | 赵紫龙 |
| B-3 | 真实 Qwen 集成测试需 `QWEN_API_KEY`，当前环境未配置 | 中 | 待配置 | 赵紫龙 |
| B-4 | `feat/alpha-business-rules` 业务规则运行时未合入，workflow 用保守默认规则 | 中 | 待合入 | 吴诗莹/丁晓炜 |

> 以上均为「模块未交付/未合入」导致的阻塞，**非代码缺陷**。本文件未发现被测代码（AgentWorkflow / LocalBM25Retriever / Qwen 适配器 / FastAPI）的功能缺陷。

---

## 7. 结论

1. **第二类端到端链路已打通**：真实 BM25 检索 + AgentWorkflow + Qwen 适配器 + FastAPI HTTP 的完整链路，在测试替身资料上能正确完成 T1-T10 全部场景。
2. **三状态机与 Citation 安全校验在真实组件上验证通过**：追问、fail-closed、逐字校验、错误 chunk_id/改写原文拒绝，均按预期工作。
3. **尚未达到「真实验收」标准**：真实核验资料（B-1）、真实 Qwen（B-3）未就绪，第三类测试仅跳过，须如实标注。
4. **下一步**：待 `feat/alpha-real-runtime`、`feat/alpha-business-rules`、`feat/alpha-retrieval-loader`、`feat/alpha-policy-review` 合入 main 且 `approved/` 有正式资料后，把 `test_alpha_e2e.py` 升级为真实运行时装配 + 真实核验资料，补测多轮会话持久化与真实 Qwen。

---

## 8. 复现方式

```bash
# 单个文件
python -m unittest tests.test_alpha_e2e -v

# 全量（含本文件）
python -m unittest discover -s tests -v
```

全量结果：**184 项，182 通过，0 失败，2 跳过**（本文件贡献 13 项：12 通过 + 1 跳过）。
