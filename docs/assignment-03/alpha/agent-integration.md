# Alpha Agent 最新集成与第二轮复审记录

更新：2026-11-20（Asia/Shanghai）。分支 `feat/alpha-agent-integration`，继续更新原PR #32，不新建PR。当前PR为非Draft、待组长第二轮审核；正式政策端到端验收仍未完成。本轮由用户亲自提交和推送。

## 同步与提交状态

已fetch最新上游，并执行 `git merge --no-commit --no-ff origin/main`，无冲突。当前处于等待用户提交的合并状态：

| 内容 | 对应提交 |
| --- | --- |
| 最新main、#35合并提交 | `a87182c5dd6f805f316df0b75896b8f84fa4415f` |
| #31合并提交（已包含在上述main） | `4282ea785195ab3fccfe07c52b7c0bf3d1b18a10` |
| #35最新修复 | `2b70386da880718430a9859c00e9cceef13c548a` |
| #36最新修复 | `e0ed6e9d11a540068e86bd642e75ec21a3736a76` |
| 本轮执行前Agent HEAD | `8ce01317f0b95441525c54c144af2eb1fb69c4a9` |

#31政策交付、#35统一加载器和元数据查询已实际进入工作区及待提交的main合并内容。未擅自合并#36生产文件，测试使用其未经修改的原始Git源码。用户提交后，新merge commit会正式包含#31/#35历史；本轮不提前编造尚未创建的最终提交SHA。

## 代码调整与兼容性

保留第一轮通过的人工审核、引用及撤回复查逻辑。本轮生产代码只补充一处接口适配：用 `partial(rules.alpha_clarification_rule, today=today)` 绑定#36新增的可选时间源，使追问和证据判断使用同一日期；对外仍是单参数追问回调。证据回调继续由 `build_from_retriever(retriever, today=...)` 绑定同一索引。

合并#35后，工厂实际使用原生元数据查询。旧Retriever适配测试显式构造不带元数据方法的替身，验证旧适配路径，不再错误断言真实新Retriever不可重索引。生产安全规则未因此放宽。

新增组合回归：

- 推免：大一/大二/大三及不匹配入学年级不能把“仅升学准备参考”用作正式推荐资格；符合年级可按规则使用。准备问题与资格判断分开验证，合成资料结果不代表判定学生真实资格。
- 跨竞赛/作品：上一场竞赛或旧作品的完成人排名不能带到新作品；缺排名先追问，不检索、不调用模型；同竞赛同作品可复用历史排名。
- 历史政策：规则可认可已结束通知的历史查询，但不能回答当前申请窗口。Agent仍为current-only，历史/expired片段统一安全拒答、不调用Qwen。
- 日期：追问与证据共同使用注入日期，固定测试时间不依赖执行当天。
- 合并实装：使用工作区中main的真实loader/BM25与#36工厂完成组合验证，并核对工作区检索源码与#35最新源码一致。

## 最新实际测试

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_upstream_integration
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration
```

- 跨分支：**21项全部通过**，保留原16项并新增上述5项兼容性检查。
- 后端全量：**251项，248通过、3跳过、0失败**。包括tests目录全量、新合入#35检索测试，以及#31位于knowledge_base/processing下的政策交付与表单隐私回归。
- 跳过原因：Windows符号链接权限、本分支尚未合并#36模块的直接导入检查、未启用的真实付费政策验收。正式规则已在21项源码组合测试中实际执行。
- 三个真实旧blocked包仍保持原始状态：23片段通过文件/哈希检查，零命中、空引用、证据不足，Qwen调用0次。未运行付费模型请求，未自动批准候选资料。

第一轮224项、#35 1cc7ce1/#36 bc97a93属于历史记录，不作为本轮验证依据。首轮合并后的排查曾发现旧测试对新Retriever能力的假设失效；已显式隔离旧适配测试后完成全量重跑。没有为通过测试关闭门禁。

## 最终提交与记录对应

环境与跨分支JSON记录：执行时Agent HEAD、待合并main父提交、#31/#35历史包含性、两个上游完整SHA与文件哈希，以及backend/tests/scripts/examples/knowledge_base/processing相关Python源码的LF规范化SHA-256。执行期间源码变化会失败。

用户亲自提交后执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration --check-record
git rev-parse HEAD
```

`--check-record`只读验证：已执行的源码指纹与当前及最终HEAD中的Git blob一致；#31/#35已在HEAD历史内；上游引用与本次记录一致。若任何一项不符，停止上传并重跑验证。提交本身会改变SHA而不会改变已测源码，因此不需要为了把SHA写进自身提交而反复制造新提交。

提交前HEAD仍显示8ce0131不代表新代码已属于8ce0131；记录显式标注待提交合并与工作区源码，最终审核使用用户提交后终端输出的完整SHA和PASS对应。

## 保留的安全约束

1. 包内 `temporal_notes["human_approved"] is True`；enabled不能替代审核，缺失/false/字符串/数字均拒绝。
2. 默认正式工厂用#35带报告的approved loader，严格目录/非空/完整indexed/warnings/总片段检查；直接传包也在索引前审核，候选状态不被修改。
3. Agent按本轮version元数据独立复核审核、来源、时效和日期；规则True不能绕过，模型返回后再次检查撤回。
4. 模型仅选择当轮合格chunk_id和完整原文；未知、过滤、前轮、重复或改写引用使整轮拒答。引用从真实片段字段白名单构建。
5. 无合格证据不调用模型，三种业务状态不变。模型异常统一交后端，历史模式继续保守拒答。

## 剩余验收

更新原PR #32请求组长第二轮审核。正式后端运行组装、审核资料放行及真实政策/模型端到端验收仍需联合完成，相关限制保留但不自动将PR改回Draft。qwen-flash/28秒/0重试的联调配置不变，密钥只在本地环境读取。

证据：`evidence/agent-integration/environment.json`、`unittest.txt`、`upstream-integration.json`、`upstream-integration.txt`、`real-policy-check.json`。其他交接说明保留历史上下文，以本页为当前复审结论。
