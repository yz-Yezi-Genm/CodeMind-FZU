# Alpha Agent 核心模块集成记录

日期：2026-11-19（Asia/Shanghai）。开发分支：`feat/alpha-agent-integration`，从最新远程 main `f5fcabce29fbbec1e02e29bb6c2eb28c92785bf3` 创建。修改保留在本地，由用户自行提交、推送和创建 PR。

## 当前交付与依赖

完成真实本地检索器、Qwen 适配器及两个业务回调的组装入口与工作流防护；尚未完成正式业务规则、人工审核政策和真实 Qwen 的正向端到端验收。

| 模块 | main 上的现状 | 本轮处理 |
| --- | --- | --- |
| AgentWorkflow（#24） | 三状态、来源/时效门槛、逐字引用校验已存在 | 保留已有门槛，增加回调防护、元数据兼容及严格 JSON 校验 |
| LocalBM25Retriever（#26） | 异步索引/检索可用，无命中为 `[]` | 使用同一实例索引和检索，启用受控文件根目录及 SHA-256 检查 |
| 业务规则（#29） | 只有 `business-rules.md`，无 `alpha_business_rules.py` 或两个可调用函数 | 默认组装时加载负责人模块；缺失时报 `SERVICE_NOT_CONFIGURED`，不静默采用旧默认规则。提前测试使用明确标记的替身 |
| QwenLLMClient（#20） | `generate(LLMGenerateRequest) -> LLMResult`、环境工厂及统一异常已存在 | 默认使用真实环境工厂；离线集成只替换 HTTP transport |
| 真实资料 | 三个包均 `blocked`；来源/时效未完成审核 | 原样索引、核验文件及哈希；验证安全拒答，不修改审核状态 |
| 适用范围元数据 | `DocumentMetadata` 有 `applicability_raw`、`deadline_on`，当前 `RetrievedChunk` 尚未带出 | 兼容类型化片段扩展，将其完整交给规则和模型；不自行发明公共字段 |

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

负责人交付 `backend.services.alpha_business_rules` 后，默认加载 `alpha_clarification_rule` 和 `alpha_evidence_check`；模型默认调用既有 `create_qwen_client_from_env()`。任何一个业务回调需要替换时，必须显式提供两个回调，避免一半真实、一半旧默认。文件损坏、缺失或来源未就绪导致 `failed/partial` 索引时，组装拒绝启动，不使用部分资料演示正式链路。`blocked` 包可以索引但始终不可检索；索引不是审核。

后端 `AskRequest` 目前只有 `query` 和 `conversation_id`，不保存/加载 history。HTTP 追问后应重发包含全部信息的完整问题；直接调用工作流可通过 `AgentRequest.history` 提供用户历史。本轮没有擅自加入会话存储或修改 HTTP 契约。

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

实际执行 191 项，188 项通过，3 项跳过，0 失败。跳过原因分别是 Windows 符号链接权限、上游正式业务规则未交付，以及真实 Qwen 验收未显式启用。

| 验证层次 | 使用真实实现 | 测试替身或局限 |
| --- | --- | --- |
| Agent 单测/API 回归 | 工作流及 FastAPI | Mock 或 demo Retriever/LLM |
| 原有 Qwen 组合测试 | 工作流、Qwen 适配器及 FastAPI | DemoRetriever、MockTransport |
| `LocalRetrieverQwenIntegrationTests` | BM25、索引、文件与哈希检查、工作流、Qwen 适配器及 FastAPI | 合成资料、规则替身、MockTransport；未调用付费模型 |
| 三个真实资料包检查 | 真实文件、登记哈希、BM25 索引、工作流与 Qwen 适配器代码 | 测试回调、MockTransport；资料原样 `blocked`，只验证安全拒答 |
| `DeliveredBusinessRulesTests` | 交付后的真实规则函数 | 当前缺模块，明确跳过 |
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

- 真实 `alpha_clarification_rule` / `alpha_evidence_check` 及完整业务案例接入验收。
- 检索/规则负责人确认并带出适用范围、适用年度、截止日期等元数据。
- 至少一份有审核记录的正式可检索政策包，以及完整正向引用结果。
- 真实 Qwen 端点的 JSON 选择结果、延迟与异常联调。
- 历史模式、资料缺失优先和多事项响应的接口口径协商。

本轮成果可供本地评审，尚不能宣称 Alpha 正式全链路已完成。提交 PR 时建议使用草稿并保留上述依赖。
