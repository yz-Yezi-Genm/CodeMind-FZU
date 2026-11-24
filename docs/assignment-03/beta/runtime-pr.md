# PR: Beta 后端运行稳定性与 Qwen 适配

## 修改目的

在 Beta 接口 V2.1-Final 下稳定 FastAPI 生命周期、Qwen 调用、会话和统一错误处理，为吴诗莹的 AgentWorkflow 受约束生成集成提供可靠运行环境。

## 修改文件

- `backend/app/alpha.py`
- `backend/app/main.py`
- `backend/services/alpha_runtime.py`
- `backend/services/errors.py`
- `backend/services/qwen_client.py`
- `scripts/check_qwen_live.py`
- `scripts/check_qwen_runtime_live.py`
- `scripts/run_alpha_agent.py`
- `scripts/verify_beta_upstream_integration.py`
- `tests/test_backend_runtime.py`
- `tests/test_qwen_client.py`
- `tests/test_beta_script_lifecycle.py`
- `tests/test_api_validation.py`
- `tests/test_agent_workflow_api.py`
- `tests/test_agent_workflow_qwen.py`
- `tests/test_mock_agent_api.py`
- `docs/assignment-03/beta/runtime-stability.md`
- `docs/assignment-03/beta/evidence/`

## 完成功能

- FastAPI lifespan 继续使用统一审核资料加载器、Agent 工厂和 Retriever 绑定业务规则。
- Qwen 自有 HTTP 连接首次创建后复用，应用关闭时释放。
- 调用方注入的 HTTP client 不因 FastAPI 重启而被适配器永久关闭。
- 三个独立诊断脚本在成功和异常路径均关闭自己创建的 Qwen 客户端。
- Qwen 返回的 JSON 内容、内部换行和 usage 信息完整交给 Agent。
- Qwen 适配器不解析 `answer` / `used_evidence_ids`，不创建 Citation。
- 完善超时、鉴权、限流、5xx、连接失败、非法/空响应处理。
- Settings 与 Client 共用构造阶段校验，拒绝非有限/布尔超时、非法重试次数、布尔/负数 usage 和缺失配置。
- Runtime 检查 Qwen 超时与重试预算，禁止超过 AgentWorkflow 单阶段超时。
- 明确 Qwen 预算属于理论配置值，实际阶段总时限由 `asyncio.wait_for()` 控制。
- 按 V2.1-Final 统一 `INVALID_REQUEST` 为 400、非法/空模型响应为 503。
- OpenAPI 声明 400、429、500、503、504，并移除旧版自动 422。
- 验证无模型 Key 时健康检查仍可用、问答返回统一 503。
- 验证会话隔离、历史限制、并发串行和后台清理。

## 上下游依赖

- #35 已审核资料加载器；
- #32 `create_alpha_workflow()`；
- #36 `build_from_retriever()`；
- #45 最新版 S1-S4 业务规则；
- #51 Retriever 元数据与片段查询契约；
- 吴诗莹 Beta Agent 分支负责 V2.1 JSON 解析、证据 ID 校验和 Citation 构造；
- 薛锦荣负责 Windows 环境文档和干净环境验证；
- 颜俊宇负责模型输出与端到端异常测试。

## 测试

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q -rs
```

Python 3.14.4：`449 passed, 28 skipped, 1 warning, 154 subtests passed`。

Python 3.10.11：`449 passed, 28 skipped, 1 warning, 154 subtests passed`。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest `
  tests/test_backend_runtime.py `
  tests/test_qwen_client.py `
  tests/test_agent_workflow_qwen.py `
  tests/test_beta_script_lifecycle.py `
  tests/test_api_validation.py `
  tests/test_mock_agent_api.py `
  tests/test_agent_workflow_api.py `
  tests/test_local_retrieval.py `
  tests/test_alpha_business_rules.py -q -rs
```

双版本结果：`306 passed, 26 skipped, 1 warning, 66 subtests passed`。

最新 main `5973eef` 上游专项：`Ran 25 tests, OK`。

前端兼容：`npm run build` 通过 TypeScript 检查及 Vite 生产构建。

## 阶段拆分

本 PR 为第一阶段，只包含 FastAPI、Runtime、QwenClient、异常处理和离线契约测试。真实 Qwen 调用及 Agent 受约束生成联调放在第二阶段 PR，合并条件为吴诗莹完成集成验证。

## 已知问题

- 当前 `main` AgentWorkflow 仍采用 Alpha 证据摘录协议，V2.1 受约束自然语言生成需在吴诗莹 Beta 分支合并后复跑。
- 正式 `approved/` 暂无人工签核资料包。
- 经组长批准，两项 V2.1-Final HTTP 状态已统一；其他错误码和响应结构未改变。
