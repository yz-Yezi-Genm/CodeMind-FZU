# Agent 上传前对齐核查｜吴诗莹

> 本文档记录 PR #24 创建前的上传准备核查情况。其中测试数量及分支状态为当时的历史记录，不代表当前最新状态。最新测试结果以 [evidence/test-record.md](evidence/test-record.md) 为准，目前完整测试为 105 项，104 项通过、1 项跳过；[PR #24](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/24) 已创建并持续更新。

核查日期：2026-11-18（Asia/Shanghai）  
仓库：https://github.com/yz-Yezi-Genm/CodeMind-FZU  
本次获取的远程 main：`3baee665b1fded80b20e4926c0132e0fb7c086b9`

## 结论

可以在独立分支上传并提交待集成评审的 PR。工作流已与最新 main 和已合并的后端/Qwen 适配器完成代码及模拟调用对齐。真实检索器、正式追问规则和付费模型调用的联调仍需后续完成，不能标为已经全链路上线。

## 已看到的同学提交

通过 Git 获取远程分支及 PR head，并读取对应文件，而非仅依据旧本地代码。

| 负责人/模块 | 本次可见成果 | 对 Agent 的影响 |
| --- | --- | --- |
| 赵紫龙：后端与 Qwen | [PR #20](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/20)，main 合并提交 `140b12b`；`backend/services/qwen_client.py`、`errors.py` 和更新的 `create_app` | 已验证异步调用、公共请求/返回类型及 HTTP 包装；按现有 ServiceError 保留统一错误码 |
| 丁晓炜：文档处理 | [PR #19](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/19)，main 合并提交 `6aee40c`；文档解析及三个政策场景包 | 样例仍为 blocked，不能为了工作流演示当作有效政策证据 |
| 薛锦荣：运行环境 | [PR #21](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/21)，main 合并提交 `7d84b75`；运行指引、换行规则及前端工程 | 基于同一后端依赖复测；本地旧文件换行按新 .gitattributes 复核 |
| 学生端 | [PR #23](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/23)，main 合并提交 `3baee66` | 使用统一三状态和现有 AskResponse；本轮验证 HTTP 输出，不宣称真实页面端到端验收 |
| 颜俊宇：补充测试 | 可见 `test/alpha-w2-contract-tests` 分支，提交 `880134d` | 尚未出现在本次 main；不擅自合并同学开发分支 |
| 林世颖：架构 | 可见 `feature/linshiying-alpha-architecture` 分支及 11 月 18 日架构图/说明提交 | 不替代当前公共契约，也未擅自合并该分支 |
| 王智洋：Retriever | 可见数据库设计分支；未找到 Alpha 真实 Retriever 实现 | 继续按现有 `Retriever.retrieve(RetrievalRequest)` 注入测试替身，等待真实实现 |
| 雷葭雨：追问规则 | 可见分支、PR 和 Alpha 目录中未找到正式规则交付 | 默认关键词规则仍注明待确认；不能宣称已完成人工沟通 |

“未找到”仅表示本次可见仓库内容，不表示同学没有本地成果。接口签名未变化：`backend/contracts/models.py`、`protocols.py` 与原工作流开发基线一致。

## 本轮完成的对齐

1. 仅将本地 Agent 开发分支快进到最新远程 main；未修改本地 main、未推送、未创建线上 PR。
2. 保留现有后端 `create_app(agent_service=..., llm_client=...)` 注入方式，不编辑同学的主入口。
3. 原工作流把所有模型异常降级为证据不足；现改为让适配器已脱敏 ServiceError 交给后端，保留 429/503/504 等统一错误行为。业务无证据仍是正常 200 + insufficient_evidence。
4. 新增 `tests/test_agent_workflow_qwen.py`：真实适配器代码、模拟 HTTP 响应，验证成功摘录、自由文本拒绝、401/408/429/500 映射及 request ID 一致性。没有请求真实付费端点。
5. 本次新增交付文件与 `origin/main` 无同路径冲突，公共模型、主入口和其他同学文件均无提交差异。压缩包使用明确文件清单，只打包吴诗莹本次成果，不包含同步下来的其他成员成果。

## 实际回归

运行 `.venv\Scripts\python.exe scripts/verify_agent_workflow.py`：102 项测试，101 项通过、1 项跳过；三状态演示退出码 0。跳过的是原有符号链接安全测试，Windows 当前账户无法创建符号链接。

初次全仓测试出现一项资料哈希失败：新 .gitattributes 要求 LF，但旧工作区有两份未被重新检出的 CRLF 文件。已逐一比较工作区、去 CRLF 后的字节、Git 原始 blob 与期望 SHA256，确认只差换行后恢复成远程 main 的原始字节，并刷新索引状态；没有改变资料内容、审核状态或 Git blob。首次失败日志保留在 `evidence/unittest-before-lf-refresh.txt`，最终输出见 `evidence/unittest.txt`。

## PR 需保留的待办

- 雷葭雨确认追问的必要项和业务规则。
- 王智洋提供真实检索器与合格证据验收样例。
- 赵紫龙与组长确认组装入口、真实模型 JSON 输出表现、历史加载和总超时预算。

以上均可作为 PR 中的联调待办，不需要等所有模块开发结束才提交独立 Agent 工作流。
