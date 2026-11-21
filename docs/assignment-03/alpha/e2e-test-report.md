# CodeMind-FZU Alpha 冲刺 · 端到端测试报告（E2E）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Alpha 冲刺（真实模块集成阶段）
> 分支：`test/alpha-e2e`（已同步最新 main）
> 测试基线：`main` = `37071ad`（含 #33 时序修复、真实运行时 #34、业务规则 #36、检索加载器 #35、Agent 集成 #32）
> 测试文件：`tests/test_alpha_e2e.py`
> 审核轮次：第 3 轮复审修正

---

## 1. 目标

验证「学生提问 → FastAPI `/api/v1/ask` → Alpha Runtime 装配 → 业务规则 → 真实 BM25 检索 →
Qwen 证据选择 → Citation 校验 → 返回结果」这条**完整正式链路**能否真正运行。

本轮（第 3 轮复审修正）重点：同步最新 main、补齐 3.10 兼容性证据、完善 T3/T4/T10 断言、
核实版本与阻塞清单。

---

## 2. 测试环境

| 项目 | 值 |
| --- | --- |
| Python | 3.10.11（评审要求）/ 3.13.14 / 3.12.7（兼容性验证） |
| fastapi | 0.141.1（3.12/3.13）/ 0.162.5（3.10） |
| pydantic | 2.13.5（3.12/3.13）/ 2.14.4（3.10） |
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
| **第二类 真实资料 + Mock Qwen** | 真实 DocumentPackage + 真实 BM25 + 真实业务规则 + Mock Qwen | `AlphaE2ETests`（T1/T2/T3/T4a/T4b/T5/T6b/T7/T8/T9）+ `AlphaE2EMultiTurnTests`（T10） | ✅ 11 通过 |
| **契约测试（非端到端）** | Pydantic 契约层，不计入端到端统计 | `AlphaContractGateTests`（T6） | ✅ 1 通过 |
| **第三类 真实 Qwen** | 真实 Qwen API，需 `QWEN_API_KEY` + `RUN_LIVE_QWEN_TESTS=1` 双开关 | `AlphaE2ERealQwenTests` | ⏸ 1 跳过 |

> **关键区分**：本文件用「测试夹具」验证技术链路，不是「正式政策资料验收」。
> 真实核验资料（`approved/` 目录）就绪前，「真实核验资料 answered」验收仍属阻塞项。

---

## 4. T1–T10 执行记录

| 编号 | 场景 | 预期 | 实际 | 结果 | 测试性质 |
| --- | --- | --- | --- | --- | --- |
| T1 | 竞赛认定，业务信息齐全 | answered | answered + 逐字引用 | ✅ | 第二类 |
| T2 | 奖学金（具体类别） | answered | answered + 逐字摘录 | ✅ | 第二类 |
| T3 | 奖学金未说明类别 | needs_clarification | 追问「校级/国家/院级哪一类」（精确断言） | ✅ | 第二类 |
| T4a | 知识库目录缺失 | 无法装配 | 503 KNOWLEDGE_BASE_UNAVAILABLE | ✅ | 第二类 |
| T4b | 知识库目录存在但为空 | 无法装配 | 503 KNOWLEDGE_BASE_UNAVAILABLE | ✅ | 第二类 |
| T5 | 资料 human_approved=false | 跳过加载 | 503（加载器跳过） | ✅ | 第二类 |
| T6 | 来源未核验 | 无法以 enabled 构造 | Pydantic ValidationError | ✅ | 契约测试 |
| T6b | 部分索引（源文件未就绪） | 无法装配 | 503 | ✅ | 第二类 |
| T7 | Qwen 超时 | 正确返回错误 | 504 MODEL_TIMEOUT | ✅ | 第二类 |
| T8 | 模型返回不存在 chunk_id | 拒绝引用 | insufficient_evidence | ✅ | 第二类 |
| T9 | 模型改写原文（ID 不变） | 拒绝引用 | insufficient_evidence（UNSUPPORTED_GENERATION） | ✅ | 第二类 |
| T10 | 多轮会话（HTTP 层） | 上下文跨轮次 + 第二轮正常问答 | 第二轮 answered + 引用，请求含第一轮上下文 | ✅ | 第二类 |

### 4.1 第 3 轮修正细节

- **T3**：明确断言追问内容为「你想问的是校级优秀学生综合奖学金、国家奖学金，还是学院层面的院级奖学金？」。
- **T4**：拆分为 T4a（目录缺失）与 T4b（目录存在但为空），两种情况均返回 503，语义明确区分。
- **T10**：增加第二轮响应状态（`answered`）与引用（`citations[0].excerpt == 原文`）断言，
  证明第二轮不仅读取上下文、还正常完成问答。

---

## 5. 关键验证点结论

### 5.1 三种业务状态（任务二）

- `needs_clarification`：奖学金缺类别时追问具体类别，不调用检索和模型（T3）。
- `insufficient_evidence`：模型虚构 chunk_id（T8）/ 改写原文（T9）时 fail-closed。
- `answered`：仅当问题明确具体类别 + 检索到 enabled+verified+current+human_approved 片段 + 逐字选中（T1/T2）。

### 5.2 Citation 引用安全性（任务三）

| 异常输入 | 系统行为 | 用例 |
| --- | --- | --- |
| 模型返回不存在 chunk_id | 拒绝，`UNSUPPORTED_GENERATION` | T8 |
| 模型改写原文（ID 不变） | 拒绝（quote ≠ content 全等） | T9 |
| 资料 human_approved=false | 加载器跳过 | T5 |
| 来源未核验 | Pydantic 契约拒绝 enabled | T6 |
| 部分索引 | 运行时拒绝装配 | T6b |

### 5.3 真实模型/后端异常（任务四）

| 异常 | 系统行为 | 用例 |
| --- | --- | --- |
| Qwen 超时 | 504 MODEL_TIMEOUT | T7 |
| 知识库缺失/空 | 503 KNOWLEDGE_BASE_UNAVAILABLE | T4a/T4b |

### 5.4 多轮会话（任务五）

- HTTP 层会话持久化 + 跨轮次上下文传递 + 第二轮正常完成问答（T10）。

---

## 6. 兼容性与已知问题（如实记录）

### 6.1 Python 版本（已核实）

- **Python 3.10.11**（winget 安装）、3.13.14、3.12.7 三版本均验证通过。
- 本文件在三版本下均为 **12 passed + 1 skipped**，全绿。
- 全量三版本均 **357 passed + 28 skipped + 136 subtests**，无失败。
- 版本核实方式：每个证据文件开头已输出 `python -VV` 与 `sys.executable`，
  见下方「原始终端输出」列表。

> **关于 3.13 的 venv 路径歧义**：本机 `fluxdemo` 虚拟环境由
> `versions/3.13.12/python.exe` 创建（`pyvenv.cfg` 的 base 解释器），但运行时
> `-VV` 与 `sys.executable` 均确认为 **3.13.14**。日志中出现的 `versions\3.13.12\Lib\...`
> 是 venv 复用 base 标准库的正常路径，**不是版本错误**。已在证据文件开头显式输出
> `-VV` 与 `sys.executable` 消除歧义。

### 6.2 UTF-8 解码警告（`PytestUnhandledThreadExceptionWarning`，B-6 仍存在）

- **根因**：`tests/test_alpha_corpus.py:311`（王智洋维护）的 `subprocess.run(["cmd", "/c", "mklink", ...], text=True)`
  未指定 `encoding`，Windows `cmd` 输出为 GBK（cp936），`text=True` 默认按 UTF-8 解码，
  字节 `0xb4`（GBK 中文）导致 `UnicodeDecodeError`。
- **状态**：**仍未修复**（同步 #33 后日志中依然存在），已定位根因，作为独立遗留问题记录。
- **影响**：仅产生线程异常警告，不影响测试通过。
- **修复建议**（未擅自修改他人文件）：`subprocess.run(..., encoding="utf-8", errors="replace")`
  或显式 `encoding="gbk"`。已反馈给王智洋，待其处理。

---

## 7. 测试结果汇总

| 环境 | 本文件 | 全量 |
| --- | --- | --- |
| Python 3.10.11 | 12 passed + 1 skipped | 357 passed + 28 skipped + 136 subtests |
| Python 3.13.14 | 12 passed + 1 skipped | 357 passed + 28 skipped + 136 subtests |
| Python 3.12.7 | 12 passed + 1 skipped | 357 passed + 28 skipped + 136 subtests |

**原始终端输出**（每份开头含 `python -VV` 与 `sys.executable`）：
- `docs/assignment-03/alpha/evidence/e2e-pytest-py310.txt`（3.10.11 全量）
- `docs/assignment-03/alpha/evidence/e2e-file-py310.txt`（3.10.11 本文件）
- `docs/assignment-03/alpha/evidence/e2e-pytest-py312.txt`（3.12.7 全量）
- `docs/assignment-03/alpha/evidence/e2e-file-py312.txt`（3.12.7 本文件）
- `docs/assignment-03/alpha/evidence/e2e-pytest-py313.txt`（3.13.14 全量）
- `docs/assignment-03/alpha/evidence/e2e-file-py313.txt`（3.13.14 本文件）

---

## 8. 阻塞清单（已核实）

| 编号 | 问题 | 状态 | 责任方 |
| --- | --- | --- | --- |
| B-1 | `approved/` 目录无正式核验资料，T1/T2 的「真实核验资料 answered」无法验证 | 仍阻塞 | 丁晓炜 |
| B-3 | 真实 Qwen 集成测试需 `QWEN_API_KEY` + `RUN_LIVE_QWEN_TESTS=1` | 待配置 | 赵紫龙 |
| B-6 | `test_alpha_corpus.py:311` subprocess 缺 encoding（UTF-8 警告，仍存在） | 待处理 | 王智洋 |

> **B-7（时序脆弱测试）已解决**：#33（`37071ad`）将 `idle_seconds=1e-9` 改为 `0.02` +
> `await asyncio.sleep(0.05)`，同步后 3.10/3.12/3.13 三版本全量均 357 passed，无失败。

---

## 9. 结论

1. 完整正式链路已打通，T1-T10 全部场景在真实入口 + 真实业务规则 + Mock Qwen 下正确工作。
2. 第 3 轮复审意见已全部落实：同步 main、3.10 兼容性验证、T3/T4/T10 断言完善、版本与清单核实。
3. B-7 已由 #33 解决；B-6 仍存在，已定位根因并作为独立遗留问题记录（待王智洋处理）。
4. 真实 Qwen 冒烟（B-3）与正式政策资料验收（B-1）仍待外部条件，如实标注。

---

## 10. 复现方式

```bash
# 本文件（3.10.11）
C:/Users/m1781/AppData/Local/Programs/Python/Python310/python.exe -m pytest tests/test_alpha_e2e.py -v

# 全量（3.10.11）
C:/Users/m1781/AppData/Local/Programs/Python/Python310/python.exe -m pytest tests/ -q

# 真实 Qwen（需双开关，谨慎使用，会消耗 API 额度）
QWEN_API_KEY=xxx RUN_LIVE_QWEN_TESTS=1 python -m pytest tests/test_alpha_e2e.py::AlphaE2ERealQwenTests -v
```
