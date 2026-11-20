# Agent 与 PR #35 检索接口对齐

> 2026-11-20复审更新：当前测试使用PR #35的1cc7ce1和PR #36的bc97a93。默认正式组装已改为load_approved_alpha_retriever并检查报告，不再仅用丢弃报告的build入口判定就绪；显式传包和Agent本身均增加严格human_approved检查。以下9201bb9及“待确认”为历史上下文，以 [复审核验](agent-integration.md) 为准。

> 更新：PR #36已确认build_from_retriever工厂。Agent已绑定，并实际使用PR #35/#36原始源码完成10项跨分支集成；以下“待确认”保留前次交接上下文，最新结论见 [正式业务规则接入](agent-business-rules-handoff.md)。

2026-11-19。根据王智洋回复及远程 `feat/alpha-retrieval-loader`（`9201bb9`）实际代码核对。PR #35 为前置依赖，目前尚未出现在本工作分支的 main 基线；未擅自合并，也未复制或修改负责人文件。

## 已确认

- `await retrieve(RetrievalRequest) -> list[RetrievedChunk]`，无命中返回 `[]`。
- `get_document_metadata(version_id) -> DocumentMetadata | None` 是同步查询，返回 enabled 版本的深拷贝，包含 record_code、applicability_raw、deadline_on、temporal_notes 等。
- `get_parsed_chunk(chunk_id) -> ParsedChunk | None` 是同步查询，返回 enabled 片段的深拷贝，包含 locator_note 等。两种查询对未知或未开放对象返回 None。
- `await build_approved_alpha_retriever(corpus_dir=..., file_root=..., allow_missing=...)` 返回已加载的 LocalBM25Retriever。
- 如需检查跳过原因及索引状态，可用同模块的 `load_approved_alpha_retriever()` 返回 `(retriever, report)`；报告有 loaded_packages、skipped_packages、index_results。

无需扩展公共 RetrievedChunk；不能把发布年推断为适用年度，也不能因为拿到元数据就视为适用性已通过。

## Agent 侧已准备

AgentWorkflow 构造函数原本就支持传入已创建的 Retriever。本轮让 `create_alpha_workflow()` 也支持 `retriever=已加载实例`，与 packages 参数二选一；这样统一加载器和规则查询使用同一索引，避免重建另一个索引导致元数据或身份不一致。

待 PR #35 在集成环境就绪后，以下是组装关系。正式证据规则如何绑定查询函数仍需雷葭雨确认；下面的 `bound_evidence_check` 指双方确认后生成的两参数回调，不是已交付函数名：

```python
from backend.retrieval import build_approved_alpha_retriever
from backend.services.agent_workflow import create_alpha_workflow

retriever = await build_approved_alpha_retriever(
    corpus_dir=approved_dir,
    file_root=repository_root,
    allow_missing=False,
)

# 将下面两个同步查询函数绑定到规则实现的方式，由规则负责人确认：
metadata_lookup = retriever.get_document_metadata
parsed_chunk_lookup = retriever.get_parsed_chunk

workflow = await create_alpha_workflow(
    file_root=repository_root,
    retriever=retriever,
    clarification_rule=alpha_clarification_rule,
    evidence_check=bound_evidence_check,
)
```

查询缺失或无法确认适用性时，规则应返回严格 False。规则不能通过 True 绕过 Agent 来源/时效基础门槛。只有基础门槛和业务规则都通过的片段进入 Qwen；空结果或全部被过滤仍返回 insufficient_evidence 且不调用 Qwen。

元数据查询返回副本，且可能因版本撤回而返回 None；规则不能依赖旧缓存继续放行。元数据与局部章节定位的实际判断逻辑由业务负责人实现。

## 仍需协作

1. 雷葭雨确认两参数 evidence_check 如何获取上述查询方法。可采用工厂或闭包，保持 `evidence_check(request, chunk) -> bool` 不变；在确认前不自行发明新的规则函数签名。
2. 上游 loader 能报告跳过或部分索引，本 Agent 自有 package 组装仍要求完整索引。使用预加载实例时，正式运行组装方应检查加载报告并确认可否启动；注入本身不代表审核/完整性验收。
3. 正式人工审核放行仍未完成：5 份候选包、371 片段仍在 pending-review，不自动改为 enabled。
4. 后端出现 `feat/alpha-real-runtime` 分支，另有正式启动和会话组装；最终由后端负责人统一使用 approved loader、同一 Retriever 和已确认的业务绑定。不要并行维护多个正式加载规则，也不要在缺规则时把旧默认规则当成已交付的正式规则。

## 验证边界

已增加本地测试，验证注入预加载的真实 LocalBM25Retriever 后保留实例和 chunk/version 身份、可继续证据选择及引用校验，并拒绝同时提供 packages 与 retriever 的歧义配置。

此测试使用合成资料、业务替身和 MockTransport；不能称为 PR #35 的完整实装联调。PR #35 实装、正式业务绑定及已审核资料的正向验收仍需依赖就绪后执行。最新全仓结果见 evidence/agent-integration/。
