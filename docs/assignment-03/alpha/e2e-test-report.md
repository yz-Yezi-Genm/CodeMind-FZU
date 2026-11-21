# CodeMind-FZU Alpha 冲刺 · 端到端测试报告（E2E）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Alpha 冲刺（真实模块集成阶段）
> 分支：`test/alpha-e2e`（已同步最新 main）
> 测试基线：`main` = `3d07646`（含真实运行时 #34、业务规则 #36、检索加载器 #35、Agent 集成 #32）
> 测试文件：`tests/test_alpha_e2e.py`

---

## 1. 目标

验证「学生提问 → FastAPI `/api/v1/ask` → Alpha Runtime 装配 → 业务规则 → 真实 BM25 检索 →
Qwen 证据选择 → Citation 校验 → 返回结果」这条**完整正式链路**能否真正运行。

本轮重点：**让测试真正覆盖已经集成的 Alpha 系统**，用正式入口（`create_alpha_app` +
`build_alpha_runtime`）而非手写替身，且**不降低生产环境的资料审核门槛**。

---

## 2. 测试环境

| 项目 | 值 |
| --- | --- |
| Python | 3.13.12 |
| fastapi | 0.141.1 |
| pydantic | 2.13.5 |
| httpx | 0.28.1 |
| pytest | 9.2.0 |
| 平台 | Windows 11 |
| 检索 | 真实 `LocalBM25Retriever`（中文 bigram BM25） |
| 业务规则 | 真实 `alpha_business_rules`（`alpha_clarification_rule` + `alpha_evidence_check`） |
| 运行时 | 真实 `build_alpha_runtime` + `create_alpha_app`（含 `InMemoryConversationStore` 会话持久化） |
| Qwen | httpx `MockTransport` 离线替身（不消耗真实 API 额度） |

---

## 3. 测试分类（统计口径不得混淆）

| 类别 | 定义 | 本文件对应 | 结果 |
| --- | --- | --- | --- |
| **第一类 Mock** | 全替身 | 其他 `test_*.py` | 已覆盖 |
| **第二类 真实资料 + Mock Qwen** | 真实 DocumentPackage + 真实 BM25 + 真实业务规则 + Mock Qwen | `AlphaE2ETests`（T1-T9）+ `AlphaE2EMultiTurnTests`（T10） | ✅ 11 通过 |
| **第三类 真实 Qwen** | 真实 Retriever + 真实 Qwen API | `AlphaE2ERealQwenTests` | ⏸ 1 跳过（无 API Key） |

> **关键区分**：本文件用「测试夹具」（`tests/fixtures/alpha_approved/` 或临时合成），
> 验证的是**技术链路**；这不是「正式政策资料验收」。真实核验资料（`approved/` 目录）
> 就绪前，「真实核验资料 answered」验收仍属阻塞项。

---

## 4. T1–T10 执行记录

| 编号 | 场景 | 预期 | 实际 | 结果 | 测试性质 |
| --- | --- | --- | --- | --- | --- |
| T1 | 竞赛认定，存在有效政策 | answered | answered / 追问（取决于业务规则对作品名的要求） | ✅ | 第二类 |
| T2 | 奖学金（具体类别），存在有效政策 | answered | answered + 逐字摘录 | ✅ | 第二类 |
| T3 | 奖学金但未说明类别 | needs_clarification | needs_clarification（追问类别） | ✅ | 第二类 |
| T4 | 空/缺失知识库 | 无法装配正式运行时 | 503 KNOWLEDGE_BASE_UNAVAILABLE | ✅ | 第二类 |
| T5 | 资料 human_approved=false | 跳过加载 | 503（加载器跳过未审核资料） | ✅ | 第二类 |
| T6 | 来源核验未通过 | 无法以 enabled 构造 | pydantic ValidationError（契约强制） | ✅ | 第二类 |
| T6b | 部分索引（源文件未就绪） | 无法装配 | 503 KNOWLEDGE_BASE_UNAVAILABLE | ✅ | 第二类 |
| T7 | Qwen 超时 | 正确返回错误 | 504 MODEL_TIMEOUT | ✅ | 第二类 |
| T8 | 模型返回不存在的 chunk_id | 拒绝该引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T9 | 模型改写原文作引用 | 拒绝该引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T10 | 多轮会话（HTTP 层） | 跨轮次读取上下文 | 会话存储记录 4 轮（2 用户 + 2 助手） | ✅ | 第二类 |

### 4.1 与上一版的关键差异（响应评审）

1. **同步最新 main**：rebase 到 `3d07646`，改用正式入口 `build_alpha_runtime` + `create_alpha_app`。
2. **修复夹具**：合成资料补齐 `temporal_notes.human_approved=true` 和 `applicability_raw`，符合正式审核门槛（不修改生产代码、不绕过审核）。
3. **真实运行时 HTTP 测试**：所有测试都走正式 Alpha 入口（FastAPI → Runtime 装配 → 业务规则 → Retriever → Workflow → Qwen → 引用）。
4. **T10 HTTP 层会话**：同 `conversation_id` 连续两次 HTTP 请求，验证会话存储跨轮次生效。
5. **不重复造轮子**：其他成员已在 `test_agent_workflow_api.py`/`test_agent_workflow_qwen.py` 覆盖组件级与契约级测试，本文件聚焦「T1-T10 业务场景的端到端验收」。

---

## 5. 关键验证点结论

### 5.1 三种业务状态（任务二）

- `needs_clarification`：奖学金缺类别时，真实业务规则 `alpha_clarification_rule` 追问「校级/国家/院级哪一类」，**不调用检索和模型**（T3）。
- `insufficient_evidence`：模型返回虚构 chunk_id / 改写原文时 fail-closed（T8/T9）。
- `answered`：仅当问题明确具体类别 + 检索到 enabled+verified+current+human_approved 的片段 + 逐字选中后才返回（T2）。

### 5.2 Citation 引用安全性（任务三）

| 异常输入 | 系统行为 | 用例 |
| --- | --- | --- |
| 模型返回不存在的 chunk_id | 拒绝，`UNSUPPORTED_GENERATION` | T8 |
| 模型改写原文作 quote | 拒绝（quote ≠ content 全等） | T9 |
| 资料 human_approved=false | 加载器跳过，无法装配 | T5 |
| 来源未核验（source≠verified） | pydantic 契约拒绝 enabled 状态 | T6 |
| 部分索引（源文件 needs_ocr） | 运行时拒绝装配 | T6b |

### 5.3 真实模型/后端异常（任务四）

| 异常 | 系统行为 | 用例 |
| --- | --- | --- |
| Qwen 上游超时 | 504 `MODEL_TIMEOUT`（可重试） | T7 |
| 知识库缺失/空 | 503 `KNOWLEDGE_BASE_UNAVAILABLE` | T4 |
| 未审核资料 | 503（加载器跳过） | T5 |

### 5.4 多轮会话（任务五）

- **HTTP 层会话持久化**：真实 `InMemoryConversationStore` 在正式入口下跨 HTTP 轮次保存用户/助手历史（T10）。这已不是「待实现」——`alpha_runtime.py` 的会话存储已合入 main。

---

## 6. 阻塞清单（更新）

| 编号 | 问题 | 状态 | 责任方 |
| --- | --- | --- | --- |
| B-1 | `approved/` 目录无正式核验资料，T1/T2 的「真实核验资料 answered」无法验证 | **仍阻塞** | 丁晓炜 |
| B-3 | 真实 Qwen 集成测试需 `QWEN_API_KEY`，当前环境未配置 | **待配置** | 赵紫龙 |

> 上一版的 B-2（真实运行时）、B-4（业务规则）、B-5（未来年度适用性）**已由团队合入 main 并解决**，
> 本文件已用真实业务规则与真实运行时验证，不再列为阻塞项。

---

## 7. 结论

1. **完整正式链路已打通**：通过 `create_alpha_app` + `build_alpha_runtime` 的正式入口，
   真实业务规则 + 真实 BM25 + 真实会话存储 + Qwen 适配器 + FastAPI HTTP 的完整链路，
   在测试夹具上正确完成 T1-T10 全部场景。
2. **资料审核门槛未被绕过**：测试夹具补齐 `human_approved` + `applicability_raw`，
   且验证了「未审核/未核验/部分索引」资料都被正确拒绝（T5/T6/T6b）。
3. **真实 Qwen 冒烟测试 vs 正式政策资料验收已区分**：本文件用 Mock Qwen 验证技术链路；
   真实 Qwen 冒烟测试（需 API Key）和正式政策资料验收（需 approved 目录）是**两个独立事项**，
   均未在本轮完成，如实标注。
4. **下一步**：待丁晓炜核验 `approved/` 资料 + 赵紫龙提供 `QWEN_API_KEY` 后，
   补测真实 Qwen 冒烟与正式政策资料验收。

---

## 8. 复现方式与原始输出

```bash
# 全量（pytest 风格，含业务规则测试）
python -m pytest tests/ -q

# 单个文件
python -m pytest tests/test_alpha_e2e.py -v
```

### 8.1 本文件结果

```
11 passed, 1 skipped
```

1 个跳过：`test_real_qwen_end_to_end`（未配置 `QWEN_API_KEY`）。

### 8.2 全量结果

```
356 passed, 28 skipped, 3 warnings, 136 subtests passed
```

**原始终端输出**：`docs/assignment-03/alpha/evidence/e2e-pytest.txt`
