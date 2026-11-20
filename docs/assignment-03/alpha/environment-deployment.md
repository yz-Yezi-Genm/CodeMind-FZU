# Alpha 环境变量与部署配置

**负责人**：赵紫龙  
**部署协作**：薛锦荣  
**日期**：2026-11-20

## 1. 配置原则

- 本地开发通过 Uvicorn `--env-file backend/.env` 加载配置；
- 部署环境直接注入进程环境变量，不使用 `--env-file`；
- `backend/.env` 不提交 Git；
- `QWEN_API_KEY` 只通过本地环境或部署平台 Secret 注入；
- 环境变量在进程启动时读取，修改后需重启服务；
- 应用日志、错误 envelope 和 OpenAPI 文档不得输出密钥。

## 2. 变量清单

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `QWEN_API_KEY` | 真实问答必填 | 空 | 只放本地或 Secret |
| `QWEN_BASE_URL` | 否 | DashScope OpenAI-compatible URL | 模型服务端点 |
| `QWEN_MODEL` | 否 | `qwen-plus` | 本轮证据选择模型 |
| `QWEN_TIMEOUT_SECONDS` | 否 | `28` | 单次模型调用上限 |
| `QWEN_MAX_RETRIES` | 否 | `0` | 0–3 次有限重试 |
| `CORS_ALLOW_ORIGINS` | 否 | 显式本地来源列表 | 禁止 `*` |
| `ALPHA_PACKAGE_DIR` | 否 | `knowledge_base/processed/alpha/approved` | 只加载 enabled 正式包 |
| `CONVERSATION_MAX_MESSAGES` | 否 | `12` | 每会话最多消息数 |
| `CONVERSATION_HISTORY_CHAR_LIMIT` | 否 | `6000` | 每会话历史字符上限 |

本轮采用：

```env
QWEN_TIMEOUT_SECONDS=28
QWEN_MAX_RETRIES=0
```

`AgentWorkflow` 默认总等待上限为 30 秒，而模型需返回
`temperature=0`、`max_tokens=8192` 的完整证据 JSON。28 秒单次请求可避免
第二次请求在总预算边界被提前取消。

## 3. 本地配置

```powershell
Copy-Item backend\.env.example backend\.env
```

账号持有人仅在本机填写：

```env
QWEN_API_KEY=本地密钥
```

确认文件被忽略：

```powershell
git check-ignore -v backend\.env
```

启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn `
  backend.app.alpha:app `
  --host 127.0.0.1 `
  --port 8000 `
  --env-file backend\.env
```

未配置密钥时，服务仍能启动，但问答返回
`503 SERVICE_NOT_CONFIGURED`；没有正式开放资料时返回
`503 KNOWLEDGE_BASE_UNAVAILABLE`。

## 4. systemd

`/etc/codemind-fzu/backend.env`：

```env
QWEN_API_KEY=由部署平台写入
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
QWEN_TIMEOUT_SECONDS=28
QWEN_MAX_RETRIES=0
ALPHA_PACKAGE_DIR=/srv/codemind-fzu/knowledge_base/processed/alpha/approved
```

Service：

```ini
[Service]
EnvironmentFile=/etc/codemind-fzu/backend.env
ExecStart=/srv/codemind-fzu/.venv/bin/python -m uvicorn backend.app.alpha:app --host 0.0.0.0 --port 8000
```

权限：

```bash
chown root:codemind /etc/codemind-fzu/backend.env
chmod 640 /etc/codemind-fzu/backend.env
```

## 5. Kubernetes

Secret 只保存敏感值：

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: codemind-qwen
type: Opaque
stringData:
  api-key: replace-outside-git
```

容器环境：

```yaml
env:
  - name: QWEN_API_KEY
    valueFrom:
      secretKeyRef:
        name: codemind-qwen
        key: api-key
  - name: QWEN_BASE_URL
    value: https://dashscope.aliyuncs.com/compatible-mode/v1
  - name: QWEN_MODEL
    value: qwen-plus
  - name: QWEN_TIMEOUT_SECONDS
    value: "28"
  - name: QWEN_MAX_RETRIES
    value: "0"
```

启动命令不附加 `--env-file`。

## 6. 验收

1. `backend/.env` 不在 Git 跟踪列表；
2. 缺密钥时 `/api/v1/health` 为 200，`/api/v1/ask` 为脱敏 503；
3. 配置有效 Secret 后可完成一次真实 Qwen 调用；
4. 日志与响应无 API Key；
5. `CORS_ALLOW_ORIGINS=*` 被拒绝；
6. 非法超时或重试次数在启动配置阶段被拒绝；
7. 密钥更新后通过重启服务生效。

## 7. 责任边界

- 赵紫龙：本地 `.env`、Qwen 配置与真实联调
- 团队账号持有人：提供并在本地填写授权密钥
- 薛锦荣：部署平台 Secret / 环境变量注入
- 罗宇泽：确认团队账号归属与最终配置
