# Alpha Agent 实际测试记录

负责人：吴诗莹  
执行日期：2026-11-18（Asia/Shanghai）  
开始：15:22:33 +08:00；结束：15:22:40 +08:00

代码基线：`323e8c2b94e852461aa5b2b5bfd6a1f031a0a2c1`，加本轮福大校历边界修正的工作区改动

分支：`feat/alpha-agent-workflow-wushiying`（现有 PR #24 的修订，待本次提交与推送）

## 环境

- Windows 11，Python 3.13.5。
- 本仓库 `.venv`，按现有 `backend/requirements-dev.txt` 安装依赖。
- Pydantic 2.14.3、FastAPI 0.163.1、Starlette 1.10.0、httpx 0.28.1。
- 完整环境与实际命令见 [environment.json](environment.json)，安装版本清单见 [requirements-tested.txt](requirements-tested.txt)。

## 执行命令与结果

仓库根目录：

```powershell
.venv\Scripts\python.exe scripts/verify_agent_workflow.py
```

脚本实际执行两个子命令，均退出码 0：

```text
python -m unittest discover -s tests -v
Ran 105 tests in 6.109s
OK (skipped=1)

python -m examples.agent_workflow_demo
needs_clarification / insufficient_evidence / answered
```

完整原始输出：[unittest.txt](unittest.txt)、[demo.txt](demo.txt)。记录由脚本捕获真实子进程输出，没有手工拼造测试成功日志。

## 覆盖范围

| 测试组 | 数量 | 实际验证 |
| --- | ---: | --- |
| Agent 工作流单元测试（新增） | 30 | 三状态、必要项追问、用户历史与助手历史隔离、引用元数据、真实片段选择、非法模型输出、数据门禁、去重、冲突、超时、取消、上下文与证据预算、扩展核验；历史/当前跨年度学年及福大校历切换边界 |
| Agent 与现有 HTTP 入口（新增） | 3 | 注入后返回三状态、AskResponse 格式、会话 ID 沿用、非法请求错误结构 |
| 已合并 Qwen 适配器组合测试（新增） | 3 | 通过实际适配器代码及模拟 HTTP 验证摘录、自由文本拒绝和 401/408/429/500 错误行为 |
| PR 开发基线已有回归测试 | 69 | 公共接口、Mock API、后端运行时、Qwen 客户端、文档处理；其中 1 项符号链接测试跳过 |
| 合计 | 105 | 104 项通过，1 项跳过，无失败 |

`subTest` 内还验证多个异常输入，105 为 unittest 测试方法数，不把这些子场景额外累计。36 个新增测试方法全部通过；跳过的是其他模块原有测试，原因是当前 Windows 账户不允许创建符号链接。

## 本轮学年边界回归

依据组长在 PR #24 复核时提供的福州大学实际校历，2026-2027 学年于 2026-08-31 开始。因此本版将 2025-2026 学年的最后一天设为 2026-08-30；这是福大校历对应的 Alpha 路由规则，不是通用学年结束规则，也不表示已核验具体政策办理截止时间。代码与测试注释同步注明这一依据。

| 场景 | 预期及实际结果 |
| --- | --- |
| 2026-08-30 查询 2025-2026 学年 | 不判历史；合成有效证据可进入生成 |
| 2026-08-31 查询 2025-2026 学年 | insufficient_evidence / UNSUPPORTED_POLICY_MODE，不调用检索和模型 |
| 2026-09-01 查询 2025-2026 学年 | insufficient_evidence / UNSUPPORTED_POLICY_MODE，不调用检索和模型 |
| 2026 年 11 月查询 2025-2026 学年，含不同连接符及空格 | insufficient_evidence / UNSUPPORTED_POLICY_MODE |
| 2026 年 11 月查询 2026-2027 学年，含不同连接符及空格 | 不误判历史，合成有效证据可进入生成 |

## 三状态演示

| 输入/条件 | 实际状态 | 关键结果 |
| --- | --- | --- |
| “奖学金怎么申请？” | `needs_clarification` | 追问学年，answer=null，无引用 |
| “选课有哪些步骤？”；检索器返回 [] | `insufficient_evidence` | answer_mode=insufficient_data，NO_ELIGIBLE_EVIDENCE，无引用 |
| “选课有哪些步骤？”；检索器返回合成有效片段 | `answered` | 调用模拟模型，原文摘录与合成片段完全一致，引用 ID 和网址来自该片段 |

异常测试还确认：blocked/review_only 不进入生成；伪造 ID、改写或局部引用、额外模型政策结论被拒绝；未核验或非当前资料被过滤；个人适用性未核验时不推断资格；同文档多当前版本停止生成；检索及未分类模型错误保守降级，Qwen 已脱敏的服务错误交给后端保留统一 HTTP 错误格式，异常私密细节不进入业务结果。

## 记录解释与边界

- Agent 检索及模型返回内容为测试替身。新增组合测试使用实际已合并的 Qwen 适配器代码、模拟 HTTP；没有真实付费 Qwen、联网检索、Chroma/BM25/RRF 或真实政策人工核验。此记录证明工作流与接口逻辑，不证明完整产品上线或真实政策问答质量。
- 原始测试输出中的 `Retriever failed`、`LLM failed`、`Evidence validation failed` 来自故意模拟的异常场景；对应测试均为 `ok`。
- 当前上游 Starlette 对现有 httpx 测试客户端给出弃用提示，不影响本轮通过；没有为此擅自修改团队依赖规范。
- 本轮仅修正工作流、对应边界测试及测试证据，公共接口、后端主入口和资料状态未改动；已有 PR #24，待用户将本次修改推送到原分支。
- 业务追问规则、真实检索器和模型注入方式的人工协作确认待完成，见主交付文档中的对接清单。
- 初次同步后回归曾因本地旧 CRLF 换行导致资料哈希失败；对照远程 Git blob 修复本地检出字节后复测通过，无资料内容或 Git blob 变更。初次输出完整保留于 [unittest-before-lf-refresh.txt](unittest-before-lf-refresh.txt)。完整核查见 [上传前对齐核查](../agent-workflow-alignment.md)。
