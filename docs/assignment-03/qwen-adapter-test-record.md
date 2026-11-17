# Qwen LLMAdapter 独立测试记录

**负责人**：赵紫龙  
**日期**：2026-11-17  
**实现文件**：`backend/services/qwen_client.py`  
**公共协议**：`backend/contracts/protocols.py::LLMClient.generate()`

## 1. 适配范围

- 复用公共 `LLMGenerateRequest`、`LLMMessage`、`LLMResult`；
- 使用 Qwen OpenAI-compatible `POST /chat/completions`；
- 请求只从环境变量读取 `QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`；
- 不修改 Agent 提示词和证据组织逻辑；
- 不把模型输出视为引用或证据。

## 2. 环境变量

| 变量 | 必填 | 默认值 / 约束 |
| --- | --- | --- |
| `QWEN_API_KEY` | 真实调用必填 | 仅保存在本地环境，不提交 |
| `QWEN_BASE_URL` | 否 | DashScope OpenAI-compatible 地址 |
| `QWEN_MODEL` | 否 | `qwen-plus` |
| `QWEN_TIMEOUT_SECONDS` | 否 | `20`，必须大于 0 |
| `QWEN_MAX_RETRIES` | 否 | `1`，范围 0–3 |

Agent 可通过 `create_qwen_client_from_env()` 获取实现了 `LLMClient` 协议的实例。

## 3. 测试方式

本轮未使用真实付费 Qwen 调用。网络协议通过
`httpx.MockTransport` 进行确定性验证，不访问外部模型服务。

执行命令：

```bash
.venv\\Scripts\\python.exe -m unittest tests.test_qwen_client -v
```

## 4. 用例与结果

| 用例 | 预期 | 结果 |
| --- | --- | --- |
| 成功响应 | 提取 content、model、usage | PASS |
| 请求构造 | URL、Bearer 头、messages、temperature、max_tokens 正确 | PASS |
| 503 后重试 | 重试一次并返回成功 | PASS |
| 请求超时 | 转为 `LLMTimeoutError` | PASS |
| HTTP 429 | 转为 `LLMRateLimitedError` | PASS |
| HTTP 500 | 转为 `LLMUnavailableError` | PASS |
| 缺失 API Key | 发起网络前返回配置错误 | PASS |
| 密钥脱敏 | `repr(settings)` 不包含密钥 | PASS |

最近一次完整测试结果：

```text
Ran 27 tests in 0.559s
OK
```

## 5. 边界

- 本轮验证的是适配器契约、异常映射和重试，不代表真实 Qwen 输出质量；
- 真实调用需要团队在本地配置 API Key 后单独执行；
- 正式回答中的引用仍只能来自 Retriever 返回且经业务核验的证据。
