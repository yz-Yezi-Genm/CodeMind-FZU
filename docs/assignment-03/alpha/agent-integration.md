# Alpha Agent 核心模块集成记录

> 2026-11-20模型交接更新：上游已报告qwen-flash/qwen-plus真实短片段探测通过；本Agent工作区尚未执行付费调用。联调环境示例已改为qwen-flash，新增 `scripts/check_qwen_live.py` 显式--live短片段复测命令及API Key本地加载说明。最新完整脚本216项，213通过、3跳过，包含13项正式规则/检索原始源码组合测试。短片段探测不代表正式政策链路验收通过。

更新日期：2026-11-20（Asia/Shanghai）。开发分支：`feat/alpha-agent-integration`，从远程 main `f5fcabce29fbbec1e02e29bb6c2eb28c92785bf3` 创建。首批修改已由用户提交；上游交接后的补充修改保留本地，由用户自行提交、推送到同一PR #32。

## 当前交付与依赖

完成真实检索器、Qwen适配器及正式业务规则闭包的组装与防护，13项原始上游代码组合测试通过。尚未完成上游合并后的正式运行入口部署、人工审核政策和真实Qwen的正向端到端验收。

| 模块 | main 上的现状 | 本轮处理 |
| --- | --- | --- |
| AgentWorkflow（#24） | 三状态、来源/时效门槛、逐字引用校验已存在 | 保留已有门槛，增加回调防护、元数据兼容及严格 JSON 校验 |
| LocalBM25Retriever（#26） | 异步索引/检索可用，无命中为 `[]` | 使用同一实例索引和检索，启用受控文件根目录及 SHA-256 检查 |
| 业务规则（#36） | 正式函数及build_from_retriever已在负责人分支交付，尚未合入本基线 | 默认按同一Retriever绑定闭包，避免裸函数无元数据；已实际执行跨分支原始代码测试 |
| QwenLLMClient（#20） | `generate(LLMGenerateRequest) -> LLMResult`、环境工厂及统一异常已存在 | 默认使用真实环境工厂；离线集成只替换 HTTP transport |
| 真实资料 | 三个包均 `blocked`；来源/时效未完成审核 | 原样索引、核验文件及哈希；验证安全拒答，不修改审核状态 |
| 适用范围元数据 | PR #35 提供按 version_id/chunk_id 读取元数据的只读查询方法，尚未合入本分支基线 | 优先通过同一 Retriever 查询，不扩展公共字段；组装函数已支持预加载实例，正式规则已通过工厂绑定，跨分支验证通过 |

不修改 `alpha_business_rules.py`、`qwen_client.py`、`retrieval/local.py`、公共契约及后端入口。

## 接口与调用顺序

1. 调用 `clarification_rule(request)`：非空问句返回 `needs_clarification`，不检索、不调用模型。异常或错误返回类型则安全拒答。回调只接收深拷贝，避免修改原始问题。
2. 保留既有历史模式和个人/期限请求保护。历史年度默认不回答为现行政策；本轮尚未实现历史模式返回。
3. 使用用户问题和用户历史构造 `RetrievalRequest`，调用真实 `retrieve()`；空结果安全拒答。
4. 重新验证检索契约和来源、时效、生效/发布日期、分数、重复身份与版本一致性。
5. 对通过基础门槛的片段调用 `evidence_check(request, chunk)`，只接受严格 `bool`；`False` 不采用，异常或非布尔值安全拒答。回调不能修改用于生成和引用的原始片段快照。
6. 只把合格片段交给 Qwen，要求返回 `{"evidence":[{"chunk_id":"...","quote":"完整原文"}]}`。没有合格片段时不调用 Qwen。
7. 校验 JSON 结构、重复键、当轮合格片段身份、重复引用和完整原文相等性。任一引用错误，整轮返回 `insufficient_evidence` 且不输出引用或政策结论。不采用过滤掉的片段、前轮片段或模型提供的来源。
8. Citation 从检索快照按公共字段白名单构建，避免内部元数据扩展触发 `extra=forbid` 或暴露内部字段。答案只展示已核对的原文。

模型适配器的 `ServiceError` 原样交给后端；工作流超时转为 `LLMTimeoutError`；未知模型异常转为脱敏 `LLMUnavailableError`，由现有 FastAPI 返回统一错误 envelope。模型服务故障不再伪装成正常的证据不足业务响应。

## 真实组装入口

```python
from pathlib import Path

from backend.app.main import create_app
from backend.contracts.models import DocumentPackage
from backend.services.agent_workflow import create_alpha_workflow


async def assemble(root: Path, approved_package_paths: list[Path]):
    packages = [
        DocumentPackage.model_validate_json(path.read_bytes())
        for path in approved_package_paths
    ]
    workflow = await create_alpha_workflow(packages, file_root=root)
    return create_app(agent_service=workflow, llm_client=workflow.llm_client)
```

负责人已在PR #36交付 `backend.services.alpha_business_rules`。默认加载 `alpha_clarification_rule` 并通过 `build_from_retriever(retriever, today=today)` 绑定证据闭包；模型默认调用既有 `create_qwen_client_from_env()`。任何一个业务回调需要替换时，必须显式提供两个回调，避免一半真实、一半旧默认。文件损坏、缺失或来源未就绪导致 `failed/partial` 索引时，组装拒绝启动，不使用部分资料演示正式链路。`blocked` 包可以索引但始终不可检索；索引不是审核。

本工作分支的基础 `create_app()`/main 和本地排查入口不保存/加载 history，HTTP 追问后需重发完整问题；直接调用工作流可通过 `AgentRequest.history` 提供用户历史。赵紫龙补充说明中的正式 `backend.app.alpha:app` 则由 ConversationAgentService 按 conversation_id 注入历史，支持第二轮补充信息；该运行分支尚未合入本基线。本轮没有擅自修改其会话实现或 HTTP 契约。

## 主动对接记录

已实际发送 GitHub PR 评论，不代表已收到确认或上游已交付：

- [王智洋：Retriever、元数据及审核资料](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/26#issuecomment-7008169139)：确认同实例传入、空结果、适用范围/年度/截止日期字段和已审核正向资料。
- [雷葭雨：业务函数及历史模式差异](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/29#issuecomment-7008171347)：请求两个正式函数及测试样例；说明当前布尔/问句回调无法表达文档中的历史模式、缺资料优先和多事项部分回答。
- [赵紫龙：Qwen 协议、异常与 API 注入](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/20#issuecomment-7008169406)：确认 JSON 证据选择、超时预算、真实模型联调方式和 HTTP 完整问题重发口径。

需要负责人协调的差异：规则文档允许已结束年度以 `historical` 回答，而现有 Agent 默认拒绝历史资料。本轮保持现行证据的保守门槛，不能仅靠 `evidence_check=True` 放开历史资料。`published_on/effective_on` 是发布/生效日期，不能当成适用政策年度。未来元数据字段名和类型以检索/规则负责人确认后的交付为准；测试里的 `policy_year/scope` 仅为兼容性替身，不是公共接口定稿。

## 实际验证

复跑命令（仓库根目录）：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.verify_alpha_agent_integration
```

接入PR #36闭包后，完整脚本实际执行216项，213项通过，3项跳过，0失败。其中13项使用PR #35/#36未经改写的代码快照，实际执行正式规则、loader和BM25；跳过项为Windows符号链接权限、本工作分支未合并规则文件的直接导入检查、真实付费验收未启用。正式规则已交付且已在快照集成中执行，不能再将该跳过写为负责人未交付。首批提交时为191项、188通过。

| 验证层次 | 使用真实实现 | 测试替身或局限 |
| --- | --- | --- |
| Agent 单测/API 回归 | 工作流及 FastAPI | Mock 或 demo Retriever/LLM |
| 原有 Qwen 组合测试 | 工作流、Qwen 适配器及 FastAPI | DemoRetriever、MockTransport |
| `LocalRetrieverQwenIntegrationTests` | BM25、索引、文件与哈希检查、工作流、Qwen 适配器及 FastAPI | 合成资料、规则替身、MockTransport；未调用付费模型 |
| 三个真实资料包检查 | 真实文件、登记哈希、BM25 索引、工作流与 Qwen 适配器代码 | 测试回调、MockTransport；资料原样 `blocked`，只验证安全拒答 |
| `DeliveredBusinessRulesTests` | 合并后直接导入的规则函数 | 本分支未合并模块，明确跳过 |
| `UpstreamRulesRetrieverIntegrationTests` | PR #35/#36原始Git快照：正式规则、BM25和approved loader | 合成资料、MockTransport；13项已运行通过 |
| `LiveAlphaAcceptanceTests` | 正式规则、已审核资料、真实 Qwen | 当前未执行；需环境变量显式启用 |

真实资料结果：竞赛 13、奖学金 4、推免 6 个片段，共 23 个片段索引通过；三个问题均零命中、`insufficient_evidence`、空引用，Qwen 调用为 0。不能把这份拒答验证写成正式政策正向验收通过。

完整证据：

- [原始测试输出](evidence/agent-integration/unittest.txt)
- [执行时间、依赖版本与测试层次](evidence/agent-integration/environment.json)
- [真实包路径、哈希、索引和三次 Agent 输出](evidence/agent-integration/real-policy-check.json)

上游正式函数和审核资料交付、配置本地 `QWEN_API_KEY` 后，可运行真实验收。不要把密钥放进命令参数、仓库或 PR。批准资料列表使用相对仓库根目录的 JSON 数组，资料文件本身必须已经正式审核开放：

```powershell
$env:ALPHA_LIVE_QWEN_TEST = '1'
$env:ALPHA_APPROVED_PACKAGES_JSON = '["path/to/approved-package.json"]'
$env:ALPHA_ACCEPTANCE_QUERY = '填写与已审核资料对应的完整问题'
.venv\Scripts\python.exe -X utf8 -m unittest tests.test_agent_workflow_qwen.DeliveredBusinessRulesTests tests.test_agent_workflow_qwen.LiveAlphaAcceptanceTests -v
```

## 尚未完成的最终验收

- PR #35/#36合并后的正式运行环境验收；原始代码快照的闭包绑定与13项跨分支集成已通过。
- 至少一份有审核记录的正式可检索政策包，以及完整正向引用结果。
- 真实 Qwen 端点的 JSON 选择结果、延迟与异常联调。
- 历史模式、资料缺失优先和多事项响应的接口口径协商。

本轮成果可供本地评审，尚不能宣称 Alpha 正式全链路已完成。提交 PR 时建议使用草稿并保留上述依赖。

## 后端/Qwen 交接后的补充

已按赵紫龙提供的说明核对客户端接口、异常和 API 注入方式。正式启动统一采用他维护的 `backend.app.alpha:app`；`scripts/run_alpha_agent.py` 保留为显式资料包的本地排查工具。新增测试验证排查脚本读取资料并注入相同客户端、401/403/408/429/5xx 和错误模型响应的 CORS/request ID、网络异常脱敏、工作流总等待取消、混合故障共享重试预算。真实付费验收入口也已覆盖基础 FastAPI 问答层，正式会话运行组装另需依赖就绪后联调。

启动命令、模型 JSON 选择协议、交接示例的路径修正，以及可直接转发给赵紫龙的待确认事项，见 [Agent 与后端/Qwen 接口对齐](agent-qwen-handoff.md)。本轮没有执行付费模型调用，正式规则已交付，审核资料和付费模型验收仍待就绪。

根据后端新发补充说明，提供 `examples/alpha-qwen.env.example` 非敏感联调配置片段：模型请求 28 秒、0 次重试，Agent 保留 30 秒外层等待；不修改客户端公共默认值或现有本地密钥文件。已验证配置传到真实适配器构造的网络客户端，模型HTTP失败/超时时只请求一次。正式环境通过 Uvicorn `--env-file backend/.env` 或平台 Secret 加载。

检索负责人已确认稳定retrieve契约、两个只读元数据查询和approved统一加载入口。组装函数可直接接收预加载实例，并通过正式规则工厂绑定同一索引，避免重建和全局查询串用。

2026-11-20已按PR #36最新head `8ec09b0`刷新13项跨分支实装测试，全部通过。追问异常测试兼容及章节敏感资料查询失败的两处差异已经解决；详见 [正式业务规则接入记录](agent-business-rules-handoff.md)。剩余工作为上游合并后的正式运行部署、历史模式和审核资料/真实模型验收。
