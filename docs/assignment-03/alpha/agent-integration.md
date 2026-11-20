# Alpha Agent 最终审核前集成记录

更新：2026-11-21（Asia/Shanghai）。继续在 `feat/alpha-agent-integration` 更新原 PR #32，当前为非 Draft，待组长最终审核。本轮完成本地合并、兼容测试和证据更新；提交与推送由用户亲自执行。

## 上游版本与合并状态

| 内容 | 完整提交 SHA |
| --- | --- |
| 最新 main，#36 正式合并 | `474574eac35bda331ac9eea2a003eb332be0138c` |
| #36 最新规则提交 | `7f9c5154f2919d6a1d8828e9041b8a8c566943ca` |
| #35 最新修复 | `2b70386da880718430a9859c00e9cceef13c548a` |
| #35 main 合并提交 | `a87182c5dd6f805f316df0b75896b8f84fa4415f` |
| #31 main 合并提交 | `4282ea785195ab3fccfe07c52b7c0bf3d1b18a10` |
| 本轮执行前 Agent HEAD | `116b157ce81c626067104db422d00ad475f05724` |

已执行 `git merge --no-commit --no-ff origin/main`，无冲突。#31/#35/#36 均包含在本轮合并内容中。用户提交前，#36 位于待提交的 main 合并父提交；用户提交后用最终 HEAD 和只读检查确认包含性，不能把旧 HEAD 当成新修改的提交。

跨分支测试读取上述两个上游分支的不可变 Git blob，记录完整 SHA 与 SHA-256。还核对了正式合入工作区的业务规则与 Retriever 源码和快照一致，并实际使用工作区 loader、Retriever、正式规则和 Agent 工厂完成问答，不只验证临时替换模块。

## 本轮改动及重点结果

AgentWorkflow 生产代码、业务规则生产模块、Retriever 和 Qwen 客户端均未修改，人工审核及引用门禁保持不变。

跨分支联调由 21 项增加到 25 项，新增：

- 正式资格意图优先：大二学生问“提前准备推免推荐资格排名”时，准备措辞不能覆盖正式资格意图，返回 `insufficient_evidence`、空引用、不调用 Qwen；纯准备问题保留规则允许的参考处理。
- 外院缺失范围拒绝：资料没有学院字段时，数学与统计学院推免问题不能使用该资料，返回证据不足、不调用 Qwen；对照查询仍能检索并回答，避免将零命中误认为规则生效。
- 无作品不继承排名：本轮没有明确作品，不能复用历史同一竞赛的第二完成人排名，返回排名追问 `needs_clarification`，不检索、不调用模型。
- 正式合并模块验证：工作区正式业务规则与 #36 最新源码一致，使用真实合并模块、实际 loader/BM25 及工厂，保留真实来源和逐字引用。

已有年级判断、跨竞赛/作品隔离、章节缺失保守拒绝、人工审核标记、加载报告完整性、引用真实性、模型异常和资料撤回复查继续通过。历史政策仍受 Agent current-only 门槛限制，不会因规则允许历史适用性而放行。

全量执行改用 pytest，同时收集原 unittest 类和 #36 的 pytest 函数，并包含 #31 的政策处理及表单隐私测试。原 unittest discovery 无法执行 pytest 函数，不能继续用其计数代表合并后的全量。新增测试依赖文件 `scripts/requirements-alpha-verification.txt`。

完整收集后发现 #36 正向工作流用例的检索替身缺少 Agent 要求的人工审核查询。仅调整 `tests/test_alpha_business_rules.py` 的替身，增加可选元数据和返回深拷贝的查询；仅正向合成用例明确设置测试审核标记。未更改正式资料审核状态、生产规则或放宽门禁。补齐后规则测试 110 项及全量回归通过。

## 实际执行与结果

安装额外验证依赖：

```powershell
.venv\Scripts\python.exe -m pip install -r scripts/requirements-alpha-verification.txt
```

执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_upstream_integration
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration
```

- 跨分支组合：**25 项全部通过，0 失败**。
- 后端全量：**365 项，363 passed、2 skipped、0 failed**；另有 **164 subtests passed**，不重复计入 365 项。
- #36 业务规则文件单独验证：**110 passed**，已包含在全量计数内。
- 跳过：Windows 账户无法创建符号链接；真实付费 Qwen/审核政策验收未显式启用。正式规则直接导入检查已通过，不再因模块未交付而跳过。
- 现有 Starlette/httpx 兼容性弃用提示 1 项，不影响测试通过。
- 三个真实 blocked 资料包：23 片段完成文件及哈希检查，检索零命中、证据不足、空引用、Qwen 调用 0 次。

此前 248 passed、3 skipped 及 #36 e0ed6e9 的记录属于上一轮，不作为本轮验收依据。不能将合成资料、MockTransport 的通过写成真实审核政策与付费模型端到端验收通过。

## 记录与最终提交对应

已更新：

- `evidence/agent-integration/upstream-integration.json`：最新完整上游 SHA、文件哈希、被测源码指纹及 main/#31/#35/#36 包含性。
- `evidence/agent-integration/upstream-integration.txt`：25 项组合测试完整输出。
- `evidence/agent-integration/environment.json`：执行环境、pytest 版本、实际命令、退出码、源码指纹和上游版本。
- `evidence/agent-integration/unittest.txt`：沿用历史文件名，内容为本轮 pytest 全量真实输出，实际执行器以环境记录的 command 为准。
- `evidence/agent-integration/real-policy-check.json`：重新执行的真实 blocked 包隔离记录。

指纹覆盖 backend/tests/scripts/examples/knowledge_base/processing 下的 Python 与依赖清单，文本换行统一为 LF；不读取本地 .env。测试期间源码发生变化会终止验证。

用户提交后执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration --check-record
git rev-parse HEAD
```

只读检查要求最终 HEAD 源码与被测指纹一致，main/#31/#35/#36 历史包含正确，上游引用与记录一致。记录中的 base_commit 是执行前的 116b157；最终提交尚需用户创建，不预写不存在的 SHA。最终审核提交 SHA 使用上述命令实际输出。

## 保留的安全限制与后续验收

资料必须明确 `temporal_notes["human_approved"] is True`；enabled 不能替代审核。默认工厂使用正式 approved 加载器并验证报告，Agent 独立检查同一版本元数据，模型返回后复核撤回。

仅当轮合格片段可以交给 Qwen。未知、过滤、前轮、重复或改写引用仍整轮拒答，无合格证据不调用模型。三种业务状态及后端异常响应保持不变，历史模式继续保守处理。

本轮完成组长要求的合并后联调和记录更新，提交后请求原 PR #32 最终审核。正式审核政策放行和真实 Qwen 政策问答仍是后续联合验收项，本轮未自动批准资料或执行付费请求。
