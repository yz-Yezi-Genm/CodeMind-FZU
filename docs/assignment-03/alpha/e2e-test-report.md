# CodeMind-FZU Alpha 冲刺 · 端到端测试报告（E2E）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Alpha 冲刺（真实模块集成阶段）
> 分支：`test/alpha-e2e`（已同步最新 main）
> 测试基线：`main` = `3d07646`（含真实运行时 #34、业务规则 #36、检索加载器 #35、Agent 集成 #32）
> 测试文件：`tests/test_alpha_e2e.py`
> 审核轮次：第 2 轮复审修正

---

## 1. 目标

验证「学生提问 → FastAPI `/api/v1/ask` → Alpha Runtime 装配 → 业务规则 → 真实 BM25 检索 →
Qwen 证据选择 → Citation 校验 → 返回结果」这条**完整正式链路**能否真正运行。

本轮（第 2 轮复审修正）重点：**让每项测试真正验证自己声称的内容**，针对性修正
判定过宽、引用拦截不严谨、会话验证不充分、分类不清、资源未释放等问题。

---

## 2. 测试环境

| 项目 | 值 |
| --- | --- |
| Python | 3.13.12（主）/ 3.12（兼容性验证，本机无 3.10） |
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
| **第二类 真实资料 + Mock Qwen** | 真实 DocumentPackage + 真实 BM25 + 真实业务规则 + Mock Qwen | `AlphaE2ETests`（T1/T2/T3/T4/T5/T6b/T7/T8/T9）+ `AlphaE2EMultiTurnTests`（T10） | ✅ 10 通过 |
| **契约测试（非端到端）** | Pydantic 契约层，不计入端到端统计 | `AlphaContractGateTests`（T6） | ✅ 1 通过 |
| **第三类 真实 Qwen** | 真实 Qwen API，需 `QWEN_API_KEY` + `RUN_LIVE_QWEN_TESTS=1` 双开关 | `AlphaE2ERealQwenTests` | ⏸ 1 跳过 |

> **关键区分**：本文件用「测试夹具」验证技术链路，不是「正式政策资料验收」。
> 真实核验资料（`approved/` 目录）就绪前，「真实核验资料 answered」验收仍属阻塞项。

---

## 4. 第 2 轮复审修正清单（9 项）

| # | 复审意见 | 修正结果 |
| --- | --- | --- |
| 1 | T1 判定过宽（三状态全通过） | 补齐业务所需信息（「学科竞赛级别认定 + 蓝桥杯」），严格断言 `answered` + 有效引用 |
| 2 | T9 同时伪造 chunk_id 和 quote | 改为先取真实 chunk_id，保持 ID 不变只改 quote，验证真正拦截改写 |
| 3 | T10 未证明上下文传给 Qwen | 增加断言：第二次模型请求的 messages 含第一轮用户问题 |
| 4 | T6 是契约层不是 E2E | 移入独立 `AlphaContractGateTests` 类，不计入端到端统计 |
| 5 | 真实 Qwen 缺显式开关 | 增加 `RUN_LIVE_QWEN_TESTS=1`，与 `QWEN_API_KEY` 双开关才运行 |
| 6 | Mock Qwen 资源未释放 | `aclose()` 改 async，通过 `addCleanup` 统一 await 关闭 upstream |
| 7 | Python 3.10 兼容性 | 本机无 3.10，用 3.12 验证（详见第 7 节） |
| 8 | UTF-8 解码警告 | 查明根因（`test_alpha_corpus.py` 的 subprocess 编码问题，非本文件），详见第 7 节 |
| 9 | 同步 main、更新报告与 PR | 已同步（见第 8 节） |

---

## 5. T1–T10 执行记录

| 编号 | 场景 | 预期 | 实际 | 结果 | 测试性质 |
| --- | --- | --- | --- | --- | --- |
| T1 | 竞赛认定，业务信息齐全 | answered | answered + 逐字引用 | ✅ | 第二类 |
| T2 | 奖学金（具体类别） | answered | answered + 逐字摘录 | ✅ | 第二类 |
| T3 | 奖学金未说明类别 | needs_clarification | needs_clarification（追问类别） | ✅ | 第二类 |
| T4 | 空/缺失知识库 | 无法装配 | 503 KNOWLEDGE_BASE_UNAVAILABLE | ✅ | 第二类 |
| T5 | 资料 human_approved=false | 跳过加载 | 503（加载器跳过） | ✅ | 第二类 |
| T6 | 来源未核验 | 无法以 enabled 构造 | Pydantic ValidationError | ✅ | 契约测试 |
| T6b | 部分索引（源文件未就绪） | 无法装配 | 503 | ✅ | 第二类 |
| T7 | Qwen 超时 | 正确返回错误 | 504 MODEL_TIMEOUT | ✅ | 第二类 |
| T8 | 模型返回不存在 chunk_id | 拒绝引用 | insufficient_evidence | ✅ | 第二类 |
| T9 | 模型改写原文（ID 不变） | 拒绝引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T10 | 多轮会话（HTTP 层） | 上下文跨轮次传给 Qwen | 第二轮请求含第一轮问题 | ✅ | 第二类 |

### 5.1 关键修正细节

- **T1**：竞赛场景业务规则要求「学科竞赛级别认定」+ 具体竞赛名（如「蓝桥杯」），
  且不能带「创新学分/综测/推免」等歧义词（否则追问用途）。已用精确问法
  「学科竞赛级别认定，蓝桥杯是什么级别？」严格断言 `answered`。
- **T9**：先正常回答拿到真实 `chunk_id`，再保持该 ID 不变、只改 `quote` 为改写文本，
  验证 `_verify_selection` 的逐字校验确实拦截「quote ≠ content」。
- **T10**：检查 `qwen.observed[-1]`（第二轮模型请求）的 `question_and_user_context`
  包含第一轮用户问题「优秀学生综合奖学金申请需要提交什么材料？」。

---

## 6. 关键验证点结论

### 6.1 三种业务状态（任务二）

- `needs_clarification`：奖学金缺类别时追问「校级/国家/院级哪一类」，不调用检索和模型（T3）。
- `insufficient_evidence`：模型虚构 chunk_id（T8）/ 改写原文（T9）时 fail-closed。
- `answered`：仅当问题明确具体类别 + 检索到 enabled+verified+current+human_approved 片段 + 逐字选中（T1/T2）。

### 6.2 Citation 引用安全性（任务三）

| 异常输入 | 系统行为 | 用例 |
| --- | --- | --- |
| 模型返回不存在 chunk_id | 拒绝，`UNSUPPORTED_GENERATION` | T8 |
| 模型改写原文（ID 不变） | 拒绝（quote ≠ content 全等） | T9 |
| 资料 human_approved=false | 加载器跳过 | T5 |
| 来源未核验 | Pydantic 契约拒绝 enabled | T6 |
| 部分索引 | 运行时拒绝装配 | T6b |

### 6.3 真实模型/后端异常（任务四）

| 异常 | 系统行为 | 用例 |
| --- | --- | --- |
| Qwen 超时 | 504 MODEL_TIMEOUT | T7 |
| 知识库缺失 | 503 KNOWLEDGE_BASE_UNAVAILABLE | T4 |

### 6.4 多轮会话（任务五）

- HTTP 层会话持久化 + 跨轮次上下文传递（T10，已证明第二轮请求含第一轮上下文）。

---

## 7. 兼容性与已知问题（如实记录）

### 7.1 Python 版本

- 本机无 Python 3.10（评审要求的 3.10.11 不可用），仅有 3.12 与 3.13。
- 用 **3.12**（最接近且官方支持范围内）验证：本文件 11 passed + 1 skipped，全绿。
- 全量 3.12 下出现 **2 个时序脆弱失败**（见 7.3），非本文件引入。

### 7.2 UTF-8 解码警告（`PytestUnhandledThreadExceptionWarning`）

- **根因**：`tests/test_alpha_corpus.py:311`（王智洋维护）的 `subprocess.run(["cmd", "/c", "mklink", ...], text=True)`
  未指定 `encoding`，Windows `cmd` 输出为 GBK（cp936），`text=True` 默认按 UTF-8 解码，
  字节 `0xb4`（GBK 中文）导致 `UnicodeDecodeError`。
- **影响**：仅产生线程异常警告，不影响测试通过（356 passed）。
- **修复建议**（未擅自修改他人文件）：`subprocess.run(..., encoding="utf-8", errors="replace")`
  或显式 `encoding="gbk"`。已反馈给王智洋。

### 7.3 时序脆弱测试（Python 3.12 偶发失败）

- **现象**：`tests/test_backend_runtime.py::ConversationRuntimeTests` 的 2 个用例
  （`test_global_cleanup_drops_inactive_sessions`、`test_global_cleanup_removes_idle_and_protects_active_state`）
  在 3.12 下偶发失败（`prune_idle(idle_seconds=1e-9)` 断言 0 != 1）。
- **根因**：`InMemoryConversationStore` 用 `monotonic()` 时间戳比较，`idle_seconds=1e-9`
  接近 `monotonic()` 分辨率下限，3.12 的时钟分辨率不足以区分，属**时序脆弱测试**（赵紫龙维护）。
- **影响**：3.13 下稳定通过；3.12 下偶发。非本文件代码缺陷。已反馈给赵紫龙。

---

## 8. 测试结果汇总

| 环境 | 本文件 | 全量 |
| --- | --- | --- |
| Python 3.13.12 | 11 passed + 1 skipped | 356 passed + 28 skipped + 136 subtests |
| Python 3.12 | 11 passed + 1 skipped | 354 passed + 2 时序失败 + 28 skipped + 136 subtests |

**原始终端输出**：
- `docs/assignment-03/alpha/evidence/e2e-pytest.txt`（3.13 全量）
- `docs/assignment-03/alpha/evidence/e2e-file.txt`（3.13 本文件）
- `docs/assignment-03/alpha/evidence/e2e-pytest-py312.txt`（3.12 全量）
- `docs/assignment-03/alpha/evidence/e2e-file-py312.txt`（3.12 本文件）

---

## 9. 阻塞清单

| 编号 | 问题 | 状态 | 责任方 |
| --- | --- | --- | --- |
| B-1 | `approved/` 目录无正式核验资料，T1/T2 的「真实核验资料 answered」无法验证 | 仍阻塞 | 丁晓炜 |
| B-3 | 真实 Qwen 集成测试需 `QWEN_API_KEY` + `RUN_LIVE_QWEN_TESTS=1` | 待配置 | 赵紫龙 |
| B-6 | `test_alpha_corpus.py:311` subprocess 缺 encoding（UTF-8 警告） | 待修复 | 王智洋 |
| B-7 | `test_backend_runtime.py` 2 个时序脆弱测试（3.12 偶发失败） | 待修复 | 赵紫龙 |

---

## 10. 结论

1. 完整正式链路已打通，T1-T10 全部场景在真实入口 + 真实业务规则 + Mock Qwen 下正确工作。
2. 第 2 轮复审 9 项意见已全部落实，每项测试真正验证其声称的内容。
3. B-6、B-7 为其他成员文件中的问题，已如实记录并反馈，未擅自修改。
4. 真实 Qwen 冒烟（B-3）与正式政策资料验收（B-1）仍待外部条件，如实标注。

---

## 11. 复现方式

```bash
# 本文件
python -m pytest tests/test_alpha_e2e.py -v

# 全量
python -m pytest tests/ -q

# 真实 Qwen（需双开关，谨慎使用，会消耗 API 额度）
QWEN_API_KEY=xxx RUN_LIVE_QWEN_TESTS=1 python -m pytest tests/test_alpha_e2e.py::AlphaE2ERealQwenTests -v
```
