# Qwen 真实小样本验证记录

**负责人**：赵紫龙  
**日期**：2026-11-20  
**环境**：DashScope OpenAI-compatible API  
**密钥**：仅配置在本地 `backend/.env`，未提交或输出

## 1. 验证目标

验证真实模型是否能按 AgentWorkflow 约定返回证据选择 JSON：

```json
{
  "evidence": [
    {
      "chunk_id": "唯一候选 ID",
      "quote": "完整片段原文"
    }
  ]
}
```

本次使用最小测试片段、`temperature=0`、`max_tokens=128`，不使用正式政策资料，
不验证政策结论。

## 2. qwen-turbo

请求失败：

```text
HTTP 429
code: limit_requests
message: You have exceeded your current request limit.
```

平台显示该模型成功率为 0。等待后重试仍为 429，因此未采用。

## 3. qwen-plus

请求成功：

```text
status: 200
elapsed_seconds: 3.902
prompt_tokens: 81
completion_tokens: 22
total_tokens: 103
json_parse_ok: true
shape_and_quote_exact: true
```

脱敏响应：

```json
{
  "evidence": [
    {
      "chunk_id": "compare-probe-001",
      "quote": "测试原文。"
    }
  ]
}
```

## 4. qwen-flash

请求成功：

```text
status: 200
elapsed_seconds: 3.587
prompt_tokens: 81
completion_tokens: 22
total_tokens: 103
json_parse_ok: true
shape_and_quote_exact: true
```

脱敏响应：

```json
{
  "evidence": [
    {
      "chunk_id": "flash-probe-001",
      "quote": "测试原文。"
    }
  ]
}
```

## 5. 结论

- `qwen-turbo` 当前受 `limit_requests` 限制，成功率 0，不采用。
- `qwen-plus` 和 `qwen-flash` 均能返回合法 JSON 并逐字匹配输入原文。
- 本轮将 `qwen-flash` 作为默认低成本模型，`qwen-plus` 作为可用备选。
- 本次小样本两者 token 数相同，差异主要是模型价格与资源级别；最终成本需要按
  DashScope 实际账单确认。
- `max_tokens=128` 只用于本次格式验证。正式 AgentWorkflow 仍按公共实现使用
  `temperature=0`、`max_tokens=8192`，实际消耗取决于输出内容。
