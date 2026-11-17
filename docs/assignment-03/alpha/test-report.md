# CodeMind-FZU Alpha 冲刺 · 测试报告（W2）

> 负责人：颜俊宇（测试与质量保障）
> 阶段：Alpha 冲刺第 2 周（11/17—11/23）
> 对应里程碑：M2（后端完成带引用的问答闭环，能处理资料不足和基础异常）
> 测试基线：`main` 分支接口规范 V1.0 + `backend/contracts/` 公共契约

---

## 1. 测试范围与目标

本周测试聚焦「接口规范符合性验证」，确认 FastAPI 骨架与 Mock Agent 是否真正符合已合并的
`docs/assignment-03/interface-contract-v1.md`。重点覆盖三件事：

1. **HTTP 层契约**：`GET /api/v1/health`、`POST /api/v1/ask` 的路径、字段、状态码、错误 envelope。
2. **问答状态机**：`answered` / `needs_clarification` / `insufficient_evidence` 三种状态及其字段约束。
3. **异常与降级**：空/超长/非法输入、Agent 未注入、Agent 异常时的统一错误处理。

**测试方式**：自动化单元/接口测试（`python -m unittest discover -s tests -v`），全部基于
`fastapi.testclient.TestClient`，无网络、无真实数据库、无真实模型调用，均为确定性测试。

---

## 2. 测试命令与执行结果

```bash
python -m unittest discover -s tests -v
```

执行结果汇总：

| 指标 | 数值 |
| --- | --- |
| 测试用例总数 | 117 |
| 通过 | 111 |
| 错误（error） | 4 |
| 失败（fail） | 0 |
| 跳过（skip） | 1 |

> 4 个 error 全部来自 `test_document_processing.py` 的 `RepositoryPackageTests`，
> 原因是本地测试环境缺少 `knowledge_base/` 与 `scripts/` 资料文件（`FileNotFoundError`），
> **属于环境未就绪，不是测试代码或被测代码的缺陷**。详见第 6 节。

---

## 3. 测试内容明细（按任务要求逐条对照）

### 3.1 健康检查

| 检查项 | 结果 | 对应用例 |
| --- | --- | --- |
| 返回 200 | ✅ 通过 | TC-001/002 |
| `status=ok` | ✅ 通过 | TC-003 |
| `service=codemind-fzu-api` | ✅ 通过 | TC-003 |
| `version=0.1.0` | ✅ 通过 | TC-003 |
| `timestamp` 为带时区 UTC ISO 8601 | ✅ 通过 | TC-003 |
| 无多余字段 | ✅ 通过 | TC-004 |
| `X-Request-ID` 为合法 UUID | ✅ 通过 | TC-005 |

### 3.2 正常问答

| 检查项 | 结果 | 对应用例 |
| --- | --- | --- |
| 提交正常问题返回 200 | ✅ 通过 | TC-006/007 |
| 返回 `status=answered` | ✅ 通过 | TC-006/007 |
| `answer` 有内容（含 Mock 标识） | ✅ 通过 | TC-006 |
| `request_id`/`conversation_id` 请求响应一致 | ✅ 通过 | TC-008 |

### 3.3 追问场景

| 检查项 | 结果 | 对应用例 |
| --- | --- | --- |
| `__mock_clarify__` 触发追问 | ✅ 通过 | TC-009 |
| 返回 `needs_clarification` | ✅ 通过 | TC-009 |
| `answer=null` | ✅ 通过 | TC-009 |
| `clarifying_question` 非空 | ✅ 通过 | TC-009 |

### 3.4 证据不足场景

| 检查项 | 结果 | 对应用例 |
| --- | --- | --- |
| `__mock_insufficient__` 触发证据不足 | ✅ 通过 | TC-010 |
| 返回 `insufficient_evidence` | ✅ 通过 | TC-010 |
| `answer_mode=insufficient_data` | ✅ 通过 | TC-010 |

### 3.5 异常输入

| 检查项 | 结果 | 对应用例 |
| --- | --- | --- |
| 空问题 → 422 `INVALID_REQUEST` | ✅ 通过 | TC-011 |
| 超长问题（>4000 字符）→ 422 | ✅ 通过 | TC-012 |
| 恰好 4000 字符 → 200（边界） | ✅ 通过 | TC-013 |
| 缺 `query` 字段 → 422 | ✅ 通过 | TC-014 |
| `query` 类型错误（数字）→ 422 | ✅ 通过 | TC-015 |
| 多余字段 → 422（extra=forbid） | ✅ 通过 | TC-016 |
| 非 JSON 请求体 → 422 | ✅ 通过 | TC-017 |
| Agent 未注入 → 503 `SERVICE_NOT_CONFIGURED` | ✅ 通过 | TC-018/019 |

---

## 4. 发现的规范符合性问题

### 问题 1（低）· Mock Agent 正常回答未设置 `answer_mode`

- **现象**：`backend/services/mock_agent.py` 的默认回答分支返回 `answer_mode=None`。
  规范 V1.0 第 4.2 节定义 `answer_mode` 表示回答用途，`answered` 状态下的回答应有明确的
  `answer_mode`（至少 `current_policy` / `historical` / `procedure_reference` 之一）。
  当前 `AskResponse` 的校验器对 `answered` 只强制 `answer` 非空，未强制 `answer_mode`。
- **影响**：前端若按 `answer_mode` 展示「当前政策 / 历史 / 流程参考」标签，会拿到 `null`，
  需要前端自行兜底。属于契约「软约束」，不影响状态机正确性。
- **建议**：Mock 演示回答标注 `answer_mode=procedure_reference`（或明确为演示用途），
  由吴诗莹（Agent）与罗宇泽（规范）确认后在真实 Agent 实现中补全。
- **状态**：待协调，暂不改动公共字段（遵守「不擅自修改公共字段」要求）。

### 问题 2（环境）· 文档处理资料文件未随仓库就绪

- **现象**：`RepositoryPackageTests` 依赖 `knowledge_base/processing/alpha-manifest.json`
  与 `scripts.parse_alpha_documents`，本地与测试环境缺这些文件，4 个用例 error。
- **归属**：丁晓炜（文档解析）、王智洋（资料入库）。
- **影响**：不影响本周「问答闭环」测试结论，但影响整体套件的「全绿」判定。
- **建议**：资料文件随对应模块分支一并入库，或为环境型用例加 `skipIf` 保护。

---

## 5. 尚未覆盖的内容（如实说明）

以下内容**本周尚未覆盖**，将在后续里程碑补齐：

| 未覆盖项 | 原因 | 计划 |
| --- | --- | --- |
| 真实 Agent 工作流（任务识别/追问/证据核验） | 真实 Agent（吴诗莹）尚未接入，当前仅 Mock | M2 后半段 Agent 落地后补集成测试 |
| 检索模块（Chroma/BM25/RRF） | 检索器（王智洋）未接入 | 检索联调后补 `Retriever` 集成测试 |
| 真实 Qwen 调用 | 仅测试了适配器的错误映射与脱敏，未真实联网 | 保留为集成测试，避免测试依赖外部模型 |
| 前端浏览器端测试（吴欣键/洪添军） | 前端尚未完成 | 前端完成后按任务清单二逐项验证 |
| 后台管理 API（林彦翔） | 管理端 API 尚未实现（契约已定义） | 后台开发阶段实现后补测 |
| 会话持久化 | 本阶段尚未实现，`conversation_id` 由后端临时生成 | 持久化落地后补测多轮会话 |
| 认证/授权 | 规范明确当前未接入 | 接入后补测鉴权边界 |

---

## 6. 交付物清单

| 交付物 | 路径 |
| --- | --- |
| 自动化测试代码（本周新增） | `tests/test_api_validation.py`（10 个用例） |
| 测试报告 | `docs/assignment-03/alpha/test-report.md` |
| 测试用例表格 | `docs/assignment-03/alpha/test-cases.csv`（34 条明细） |
| 测试结果汇总截图 | `docs/assignment-03/alpha/test-summary.png` |
| 终端运行截图 | `docs/assignment-03/alpha/test-terminal-run.png` |
| 完整测试输出 | `docs/assignment-03/alpha/test-run-output.txt` |

> 完整契约模型测试见 `tests/test_interface_contracts.py`（43 个用例，覆盖规范全部公共数据模型）。

---

## 7. 结论

1. **问答闭环骨架符合接口规范**：健康检查、正常问答、追问、证据不足、异常输入、Agent 未注入
   六大场景全部通过，`answered`/`needs_clarification`/`insufficient_evidence` 三状态机行为正确。
2. **错误处理统一且安全**：所有错误走统一 `ApiErrorResponse` envelope，且不泄露内部堆栈、密钥、
   数据库连接串或本地路径。
3. **无失败（fail）用例**，4 个 error 均为环境缺资料文件导致，非代码缺陷。
4. **待推进**：真实 Agent、检索、前端联调、后台管理、会话持久化、鉴权等内容将在后续里程碑补测。

---

*报告人：颜俊宇 · 2026-11-17*
