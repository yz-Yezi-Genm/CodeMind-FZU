# PR: Beta 后端运行稳定性与 Qwen 适配

## 修改目的

在 Beta 接口 V2.1-Final 下稳定 FastAPI 生命周期、Qwen 调用、会话和统一错误处理，为吴诗莹的 AgentWorkflow 受约束生成集成提供可靠运行环境。

## 修改文件

- `backend/app/alpha.py`
- `backend/services/alpha_runtime.py`
- `backend/services/qwen_client.py`
- `tests/test_backend_runtime.py`
- `tests/test_qwen_client.py`
- `docs/assignment-03/beta/runtime-stability.md`
- `docs/assignment-03/beta/evidence/`

## 完成功能

- FastAPI lifespan 继续使用统一审核资料加载器、Agent 工厂和 Retriever 绑定业务规则。
- Qwen 自有 HTTP 连接首次创建后复用，应用关闭时释放。
- 调用方注入的 HTTP client 不因 FastAPI 重启而被适配器永久关闭。
- Qwen 返回的 JSON 内容、内部换行和 usage 信息完整交给 Agent。
- Qwen 适配器不解析 `answer` / `used_evidence_ids`，不创建 Citation。
- 完善超时、鉴权、限流、5xx、连接失败、非法/空响应处理。
- 拒绝 `nan`/`inf` 超时、布尔/负数 usage 和缺失配置。
- 验证无模型 Key 时健康检查仍可用、问答返回统一 503。
- 验证会话隔离、历史限制、并发串行和后台清理。

## 上下游依赖

- #35 已审核资料加载器；
- #32 `create_alpha_workflow()`；
- #36 `build_from_retriever()`；
- 吴诗莹 Beta Agent 分支负责 V2.1 JSON 解析、证据 ID 校验和 Citation 构造；
- 薛锦荣负责 Windows 环境文档和干净环境验证；
- 颜俊宇负责模型输出与端到端异常测试。

## 测试

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q
```

结果：`367 passed, 28 skipped, 145 subtests passed`。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest `
  tests/test_backend_runtime.py `
  tests/test_qwen_client.py `
  tests/test_agent_workflow_qwen.py -q
```

结果：`72 passed, 26 skipped, 42 subtests passed`。

## 阶段拆分

本 PR 为第一阶段，只包含 FastAPI、Runtime、QwenClient、异常处理和离线契约测试。真实 Qwen 调用及 Agent 受约束生成联调放在第二阶段 PR，合并条件为吴诗莹完成集成验证。

## 已知问题

- 当前 `main` AgentWorkflow 仍采用 Alpha 证据摘录协议，V2.1 受约束自然语言生成需在吴诗莹 Beta 分支合并后复跑。
- 正式 `approved/` 暂无人工签核资料包。
- V2.1 错误表与现有 HTTP 兼容行为存在两处差异：参数校验当前为 422、非法模型响应当前为 502；本轮未擅自修改公共 API，待负责人统一确认。
