# Alpha Agent 核心模块集成与复审核验

更新：2026-11-20（Asia/Shanghai）。分支 `feat/alpha-agent-integration`，继续更新原 PR #32。已只读确认 PR 为 OPEN、`draft=false`，即非 Draft、可评审状态；当前修复等待用户提交后由组长复审。正式政策端到端验收尚未完成，与 GitHub 是否 Draft 是两回事。本次未修改线上 PR 状态。

## 复审要求与修复

### 人工审核门禁

`retrieval_status=enabled` 不能替代人工审核。所有用于回答的文档必须满足：

```python
isinstance(metadata.temporal_notes, dict)
and metadata.temporal_notes.get("human_approved") is True
```

缺失、False、None、字符串和数字标记都不通过，也不自动修改候选资料状态。

- 默认 `create_alpha_workflow(file_root=...)` 使用 PR #35 的 `load_approved_alpha_retriever()`，`allow_missing=False`。也可显式指定 `corpus_dir`。
- 验证加载报告：目录存在、实际加载包非空、索引结果非空、所有结果为完整 `indexed` 且无警告、总可用片段大于0。`partial/failed`、空目录、缺目录、零片段均返回脱敏配置错误；不能仅凭 loaded_packages 判定就绪。
- 显式 `create_alpha_workflow(packages=...)` 对全部包重新校验，并在创建索引或模型客户端前检查严格人工审核标记；任一包未通过即拒绝组装。
- Agent `_eligible()` 独立读取本轮 version_id 对应的 DocumentMetadata，校验审核标记、公共契约及与片段的来源/日期/核验状态一致性。无查询方法、未知元数据、查询异常、未审核版本均不进入 Qwen；业务回调返回True也不能绕过。
- Qwen返回后重新检查实际选中证据的审核和开放状态；等待模型期间撤回的证据不输出引用，返回 `EVIDENCE_APPROVAL_CHANGED`。
- 当前基线的旧 LocalBM25Retriever 尚无元数据查询。仅对工厂自行索引、审核通过的显式包提供私有只读快照适配；不暴露重索引接口，不允许缓存审核状态与可变旧索引并存。默认正式目录路径仍要求使用PR #35最新实现。可更新索引使用上游原生查询。
- `LiveAlphaAcceptanceTests` 在联网前断言每个包均 enabled、human_approved严格为True、路径位于approved目录，并使用统一加载器再次验证报告。

### 最新上游与测试溯源

本次先fetch，再使用以下原始Git源码，不复制上游生产代码到本PR：

| 上游 | 最新提交 |
| --- | --- |
| PR #35 `feat/alpha-retrieval-loader` | `1cc7ce14864e6deaebf8c157b95985403c38ff9e` |
| PR #36 `feat/alpha-business-rules-runtime` | `bc97a93dc60db076e1d1e64494dd3a96aa0895ac` |

最新规则增加了作品名称等必要项，集成问题已补齐这些信息，不用旧问题绕过新的追问要求。

原13项跨分支集成已全部重新运行，新增3项审核/报告边界检查，共16项通过。全仓224项，221通过、3跳过、0失败。三个跳过项为Windows符号链接权限、本工作分支未合并规则文件的直接导入检查、未启用的真实付费政策验收；正式规则已经在源码快照测试中执行。

## 工作流与组装

1. 必要信息检查，缺信息返回needs_clarification；规则异常返回CLARIFICATION_RULE_FAILED，不检索或调用模型。
2. 用户问题与用户历史构造检索请求；保留既有历史请求限制，不采信助手历史作为政策依据。
3. 片段通过公共契约、人工审核、来源、时效、日期、重复身份及版本一致性检查。
4. `build_from_retriever(retriever, today=...)` 绑定同一索引的文档/章节查询。仅合格片段进入Qwen。
5. Qwen仅输出evidence数组中的chunk_id与完整quote。未知、过滤、前轮、重复或改写引用使整轮拒答。
6. 二次审核状态检查通过后，从原始片段按公共字段白名单构建Citation，答案只展示逐字核验原文。

三种状态保持answered、needs_clarification、insufficient_evidence。无合格证据不调用模型。模型适配器ServiceError原样交给FastAPI；外层等待超时转LLMTimeoutError，未知模型调用异常转脱敏LLMUnavailableError。历史模式本轮仍保守拒答，不把历史通知当作当前政策。

默认正式组装示意（需上游模块在运行环境就绪）：

```python
workflow = await create_alpha_workflow(file_root=repository_root)
app = create_app(agent_service=workflow, llm_client=workflow.llm_client)
```

后端维护的正式入口为 `backend.app.alpha:app`。本地排查脚本支持默认approved目录、`--corpus-dir`或显式`--package`，同样执行审核门禁；它没有正式入口的ConversationAgentService会话包装。正式后端运行组装需同步这些门禁，不修改其他成员负责文件。

## 测试、记录与最终提交对应

在仓库根目录运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_upstream_integration
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration
```

第一条输出16项跨分支结果；第二条全仓包含相同16项。脚本从远程分支引用提取原始代码，记录完整提交与文件SHA-256；缺少引用时显式失败，需先fetch。

记录还包含本Agent所有相关Python源码的LF规范化SHA-256。`base_commit`是执行时的HEAD，不伪称尚未提交的修复已经属于该提交。用户亲自提交后，以如下只读命令将最终HEAD与已执行的源码指纹、上游提交对应：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration --check-record
```

必须输出PASS；若源码或上游引用变了，应重新验证。该检查不重跑测试、不修改记录、不进行付费调用。测试期间源码变化也会导致验证脚本失败。

证据文件：`evidence/agent-integration/environment.json`、`unittest.txt`、`upstream-integration.json`、`upstream-integration.txt`、`real-policy-check.json`。216项/9201bb9/8ec09b0是上一轮历史结果，不再作为本次验收依据。

测试层次明确区分：Mock回归；正式规则/loader/BM25与合成审核输入、MockTransport的跨模块测试；真实blocked包的安全拒答；未执行的正式政策和真实模型端到端验收。合成资料的human_approved=True是测试输入，不是人工签核真实政策。

现有三个真实包保持原始状态：23个片段通过文件与哈希检查并索引，检索均零命中，Agent安全拒答、空引用、模型调用0次。直接交给正式包工厂时则因未审核被拒绝组装，不能为演示将它们改为已审核。

## 剩余验收与协作

- 组长复审本次门禁修复及最新测试证据。
- 上游PR进入正式运行环境后，后端统一使用带报告的approved加载器和规则闭包，规则不可用时保持未就绪。
- 团队指定审核者放行至少一个正式enabled、human_approved=True政策包。
- 与账号持有人完成真实政策的检索→规则→Qwen→Citation及会话端到端验收。qwen-flash、28秒、0重试；密钥仅本地环境加载。

上游已提供qwen-flash/qwen-plus真实短片段格式探测记录，但本工作区未执行付费调用，不将其写成本Agent端到端通过。其余交接历史见同目录agent-business-rules-handoff.md、agent-retrieval-handoff.md、agent-qwen-handoff.md，以本页最新复审结果为准。
