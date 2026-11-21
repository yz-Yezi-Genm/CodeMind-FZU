# Alpha 学生端后端联调交底

**后端负责人**：赵紫龙  
**日期**：2026-11-20  
**后端分支**：`feat/alpha-real-runtime`  
**前端分支**：`feat/alpha-student-real-api`

## 1. PR 状态

PR #34 当前仍为开放状态，尚未合入 `main`；GitHub 显示可合并，但仍在等待
审核。具体合入时间取决于审核人，当前无法确认固定时间。

前端可在自己的独立分支中按本文接口先行联调，不要自行修改公共字段、路径或
状态值。

## 2. 运行入口与端口

后端真实入口：

```text
backend.app.alpha:app
```

本机默认端口：

```text
http://127.0.0.1:8000
```

前端固定开发端口：

```text
http://127.0.0.1:5173
```

Vite 已将 `/api` 代理到 `http://127.0.0.1:8000`。前端代码继续使用相对路径：

```text
/api/v1/health
/api/v1/ask
```

后端 CORS 已允许 `localhost:5173` 和 `127.0.0.1:5173`。

## 3. 启动方式

Mock 入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn `
  backend.app.dev:app `
  --host 127.0.0.1 `
  --port 8000
```

真实入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn `
  backend.app.alpha:app `
  --host 127.0.0.1 `
  --port 8000 `
  --env-file backend\.env
```

## 4. Qwen 环境

本地 `backend/.env` 已配置团队密钥，文件被 Git 忽略，不会提交。

当前真实配置：

```env
QWEN_MODEL=qwen-flash
QWEN_TIMEOUT_SECONDS=28
QWEN_MAX_RETRIES=0
```

真实小样本结果：

- `qwen-flash`：成功，JSON 和完整原文匹配，103 tokens，3.587 秒；
- `qwen-plus`：成功，JSON 和完整原文匹配，103 tokens，3.902 秒；
- `qwen-turbo`：当前平台成功率 0，返回 429 `limit_requests`，不使用。

API Key 不通过聊天或仓库传递。需要真实联调的成员应通过受控私密渠道获取，
只填入自己的 `backend/.env`。

## 5. enabled 资料包状态

正式目录：

```text
knowledge_base/processed/alpha/approved/
```

当前不存在正式 `approved` 目录；现有三套资料均为 `blocked`，不能作为正式
政策回答证据。

用于前端最终联调的 enabled 测试包：

```text
tests/fixtures/alpha_approved/
```

该包标题明确包含“测试夹具”，来源为 `https://example.invalid/test-policy`，
只用于验证前端展示和 HTTP/Agent 链路，不是正式政策结论。

启动带合成 enabled 包的本地真实服务：

```powershell
$env:ALPHA_PACKAGE_DIR='tests/fixtures/alpha_approved'

.\.venv\Scripts\python.exe -m uvicorn `
  backend.app.alpha:app `
  --host 127.0.0.1 `
  --port 8000 `
  --env-file backend\.env
```

## 6. 三类真实服务响应

以下响应由 `backend.app.alpha:app`、本地 Qwen 和 enabled 测试包实际生成。

### 6.1 answered

请求：

```http
POST /api/v1/ask
Content-Type: application/json
Origin: http://127.0.0.1:5173
```

```json
{
  "query": "2026年奖学金申请需要提交什么材料？",
  "conversation_id": null
}
```

响应：

```json
{
  "request_id": "20cd067a-ce36-4e93-aed7-99998e5ad26a",
  "conversation_id": "0476f05d-a508-4522-b317-5673a3abb65f",
  "status": "answered",
  "answer": "已核验资料中与本问题相关的原文如下：\n[1] 2026年奖学金申请需提交申请表和成绩单。",
  "answer_mode": "current_policy",
  "clarifying_question": null,
  "citations": [
    {
      "document_id": "8d02cf63-8489-5ff2-865c-47b9afaa57cd",
      "version_id": "605ebbe0-ee72-5aaf-942a-9a82c2c54f5b",
      "chunk_id": "5c9318b1-ee71-5ea5-98fb-e79c5ef0b075",
      "title": "2026年本科生奖学金评定办法（测试夹具）",
      "publisher": "测试发布单位",
      "source_url": "https://example.invalid/test-policy",
      "published_on": "2026-01-01",
      "effective_on": "2026-01-01",
      "locator": "第1行",
      "original_locator": null,
      "excerpt": "2026年奖学金申请需提交申请表和成绩单。",
      "source_verification_status": "verified",
      "timeliness_verification_status": "current",
      "retrieval_status": "enabled"
    }
  ],
  "warnings": [
    {
      "code": "ALPHA_EXTRACTIVE_ANSWER",
      "message": "Alpha 版仅展示模型选取并逐字核对的证据原文；不据此推断个人资格、办理开放时间或未载明的条件。"
    }
  ],
  "created_at": "2026-11-20T08:05:56.139571Z"
}
```

**边界**：`citations` 指向合成测试资料，不是学校正式政策。

### 6.2 needs_clarification

请求：

```json
{
  "query": "奖学金有哪些类别？",
  "conversation_id": null
}
```

响应：

```json
{
  "request_id": "c6ab0c08-29e2-483e-8265-10cd2f534f2a",
  "conversation_id": "3d629e04-f1e4-4fa3-9a02-f72dd0239b56",
  "status": "needs_clarification",
  "answer": null,
  "answer_mode": null,
  "clarifying_question": "请问你咨询的是哪一学年的评定？",
  "citations": [],
  "warnings": [],
  "created_at": "2026-11-20T08:05:56.183195Z"
}
```

### 6.3 insufficient_evidence

请求：

```json
{
  "query": "选课有哪些步骤？",
  "conversation_id": null
}
```

响应：

```json
{
  "request_id": "8b20a56b-6b7a-4584-87dd-d1eb61a5e0d8",
  "conversation_id": "c12c70e8-0522-46a5-aca0-59a24a81c652",
  "status": "insufficient_evidence",
  "answer": "未找到检索已开放、来源已核验且时效为当前的有效证据，暂时不能给出确定结论。",
  "answer_mode": "insufficient_data",
  "clarifying_question": null,
  "citations": [],
  "warnings": [
    {
      "code": "NO_ELIGIBLE_EVIDENCE",
      "message": "未找到检索已开放、来源已核验且时效为当前的有效证据，暂时不能给出确定结论。"
    }
  ],
  "created_at": "2026-11-20T08:05:56.187349Z"
}
```

## 7. 前端处理要求

- 首次请求传 `conversation_id: null`；
- 后续轮次沿用响应中的 `conversation_id`；
- `needs_clarification` 时展示 `clarifying_question`，此时 `answer` 为 `null`；
- `insufficient_evidence` 时展示 `answer` 和 `warnings`，不得推断政策结论；
- `answered` 时展示 `answer`、`citations`、`answer_mode` 和 `warnings`；
- 404/422/429/500/502/503/504 使用统一 `error` envelope；
- 前端不得直接调用 Qwen，也不得持有 `QWEN_API_KEY`。
