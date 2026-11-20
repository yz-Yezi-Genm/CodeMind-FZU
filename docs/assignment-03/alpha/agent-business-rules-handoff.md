# PR #36 正式业务规则接入

2026-11-20更新。读取 `origin/feat/alpha-business-rules-runtime`（`8ec09b0`）与 `origin/feat/alpha-retrieval-loader`（`9201bb9`）后完成 Agent 侧验证。未合并他人分支，未改规则、检索或后端负责人文件。

## 已完成

默认 `create_alpha_workflow()` 先确定 Retriever 实例，再加载正式追问函数，并调用：

```python
clarification_rule = rules.alpha_clarification_rule
evidence_check = rules.build_from_retriever(retriever, today=today)
```

闭包绑定同一索引的元数据和片段查询，保留 `(request, chunk) -> bool`。不使用裸 `alpha_evidence_check`，也不调用模块级 bind 函数，避免多个应用/索引互相覆盖全局查询。业务与工作流的证据判断使用同一可注入日期。

已加载的 Retriever 可以传给组装工厂；以 packages 方式组装时也在绑定后向同一个实例索引。未有元数据查询方法的旧 Retriever 会由规则按未知处理，不能误报为正式正向链路成功。两个上游PR进入工作分支后，默认加载可直接使用这些接口；本轮不复制其生产文件。

## 实际跨分支验证

新增 `scripts/verify_alpha_upstream_integration.py`，从 Git 的上游提交提取未经改写的规则、BM25 和 approved 加载器到临时目录，读取模块快照完成集成测试。临时文件随测试结束移除，不合并或覆盖成员代码。记录包含提交、文件路径和 SHA-256。

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_upstream_integration
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration
```

验证脚本依赖本地已有这两个远程分支引用；缺引用时报错，不静默跳过。普通 `unittest discover` 未设置快照环境时会明确跳过这13项，因此完整跨分支报告以以上脚本为准。

13项实装测试全部通过：

- 奖学金缺类别先追问，不调用检索/模型。
- 正式规则、真实loader/BM25、Qwen适配器及引用校验完成合成资料正向链路。
- 用户历史补齐类别后继续执行。
- 元数据缺失或查询抛异常时拒答。
- 适用范围未知或政策种类不适用时拒答。
- 年度不匹配时剔除证据，不调用Qwen。
- 通过真实 parsed chunk 的 locator_note 剔除教师条款，Qwen只收到学生条款。
- 两个Retriever实例的闭包互不串用元数据。
- 已确认历史片段仍被当前工作流门禁挡住。
- review_only 包不被实际approved loader加载。
- 混合条款敏感资料在查询方法缺失、查询异常、返回None、缺备注、空备注时全部安全拒答，不调用Qwen。
- 非章节敏感资料缺章节信息时仍可按其他规则放行。
- Agent侧严格断言追问异常为insufficient_evidence/insufficient_data/CLARIFICATION_RULE_FAILED，不兼容异常上抛，也不调用后续依赖。

全仓脚本将这13项同时纳入：216项，213通过，3跳过。跳过项为Windows符号链接权限、当前工作分支未合并真实规则模块的直接导入测试、尚未启用的付费真实资料验收。第二项跳过不代表正式规则未交付：真实规则已经在上面的13项快照测试中执行。

证据见 `evidence/agent-integration/upstream-integration.txt`、`upstream-integration.json` 和最新全仓输出。测试使用合成资料与MockTransport，不代表人工审核政策或真实付费Qwen验收。

## 历史模式决定

本轮保持 `timeliness=current` 和既有历史请求保护，不直接放开 historical/expired。规则返回True只表达业务适用性，不能自行选择answer_mode或改变“当前可申请”的表达。

因此2027推免复试、2026院级奖学金的历史通知正向回答本轮仍是未完成项。后续单独协商历史模式：必须只用已审核、可检索、明确年度的资料，设置historical、清晰提示办理周期已结束并避免套用未来年度；同一问题混用现行与历史证据的行为也需定义。不能只改_eligible的一行枚举就宣称支持历史政策。无需修改公共状态枚举，但需要工作流与业务负责人明确输出策略。

## 2026-11-20 对齐结论与可转发回复

已核对PR #36 head 8ec09b0，两处差异均已解决。上游异常测试暂时兼容旧main和新Agent，合理覆盖其未合并的基线；本Agent侧已保留严格的CLARIFICATION_RULE_FAILED断言，后续规则分支合入本Agent兜底后再删除兼容分支。

章节敏感名单仅覆盖确知需要区分教师/学生条款的资料。新增验证覆盖查询方法缺失、查询异常、返回None、缺备注、空备注，所有片段被剔除后返回NO_ELIGIBLE_EVIDENCE；教师条款拒绝、学生条款放行，非敏感资料不受缺备注影响。无需再要求负责人重复修改。

可回复雷葭雨：收到，我已按8ec09b0重新验证。两个查询继续通过build_from_retriever绑定同一索引，13项跨分支集成全部通过，全仓216项、213通过、3跳过。追问异常我这边保留严格安全拒答断言，你的旧main兼容写法可以等合并后再收紧。章节敏感资料查询失败的处理也已验证通过。历史模式继续按双方确认保守拒答，这两点目前没有新的修改要求。

上述文字供用户转发，本轮没有代发新消息。后端组装仍需同步使用该闭包，并取消正式规则不可用时静默回退旧默认规则。
