# Alpha 阶段运行说明（工程环境与部署支持）

> 适用对象：CodeMind-FZU 全体开发成员
> 适用阶段：Alpha（后端接口骨架 + Mock Agent）
> 维护人：薛锦荣（工程环境与部署支持）
> 最后验证：2026-11-17，Windows 11 + Python 3.10.11
> 验证方式：从零创建虚拟环境、安装依赖、按本文命令启动并通过接口与测试验证

本文说明如何在**本地**把 CodeMind-FZU 的 Alpha 后端跑起来。当前阶段只包含 FastAPI 接口骨架与 Mock Agent，**不需要数据库、不需要 Qwen/Tavily 密钥、不需要联网**即可完成全部验证。

---

## 一、环境要求

| 项目 | 要求 | 本次验证环境 |
|---|---|---|
| 操作系统 | Windows / macOS / Linux | Windows 11 |
| Python | **3.10 及以上**（推荐 3.10 / 3.11） | Python 3.10.11 |
| 包管理 | pip（随 Python 安装） | pip 25.x |
| 浏览器 | Chrome / Edge（用于打开 `/docs`） | Edge |
| 网络 | 仅首次安装依赖时需要（可用国内镜像） | 清华镜像 |
| 数据库 / 密钥 | **不需要** | — |

> 说明：仓库的 Python 依赖在 `backend/requirements.txt`（运行依赖）和 `backend/requirements-dev.txt`（运行 + 测试依赖）。后者额外包含 `httpx`，是 `fastapi.testclient` 的必需依赖。

---

## 二、获取代码

```bash
git clone https://github.com/yz-Yezi-Genm/CodeMind-FZU.git
cd CodeMind-FZU
```

后续所有命令都**在仓库根目录**（即包含 `backend/` 的目录）执行。不在根目录会出现 `ModuleNotFoundError: No module named 'backend'`。

---

## 三、创建虚拟环境

### Windows（PowerShell）

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 `py -3.10` 不存在，请先安装 Python 3.10，或改用已安装的版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 不想激活时

也可以不激活，直接用虚拟环境里的解释器（推荐在脚本/IDE 中使用）：

```powershell
# Windows
.\.venv\Scripts\python.exe -m uvicorn backend.app.dev:app --reload
```

```bash
# macOS / Linux
.venv/bin/python -m uvicorn backend.app.dev:app --reload
```

> `.venv/` 已在 `.gitignore` 中，不要提交。

---

## 四、安装依赖

### 仅运行后端（最小依赖）

```powershell
python -m pip install -r backend/requirements.txt
```

### 需要跑测试（推荐，包含 httpx）

```powershell
python -m pip install -r backend/requirements-dev.txt
```

国内网络建议加镜像：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r backend/requirements-dev.txt
```

安装完成后可自查：

```powershell
python -m pip list
```

应能看到 `fastapi`、`pydantic`、`uvicorn`、`httpx`。本次验证安装到的版本：

```text
fastapi   0.162.5
pydantic  2.14.3
uvicorn   0.54.0
httpx     0.28.1
```

> `requirements.txt` 使用范围约束（如 `fastapi>=0.115,<1.0`），因此不同时间安装到的具体版本可能不同，属正常现象。

---

## 五、启动后端

### 5.1 启动 Mock Agent（本阶段推荐）

在仓库根目录、已激活虚拟环境（或使用 `.venv` 解释器）的前提下执行：

```powershell
python -m uvicorn backend.app.dev:app --reload
```

成功标志：

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

说明：

- `backend.app.dev:app` 在创建 FastAPI 应用时注入了 `MockAgentService`，因此 `/api/v1/ask` 能返回模拟回答。
- `--reload` 会在代码变更后自动重载，适合开发；只做验证时也可以去掉。
- 如需换端口：`--port 8010`；如需局域网访问：`--host 0.0.0.0`。

### 5.2 默认应用（未注入 Agent，用于对照）

```powershell
python -m uvicorn backend.app.main:app --reload
```

该入口**没有**注入 Agent，`POST /api/v1/ask` 会返回 `503 SERVICE_NOT_CONFIGURED`，这是**预期行为**，不是环境故障。日常联调请用 5.1 的 `dev:app`。

---

## 六、验证接口

服务启动后，另开一个终端执行以下验证。

### 6.1 健康检查

浏览器打开：<http://127.0.0.1:8000/api/v1/health>

或用命令：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

预期返回：

```json
{
  "status": "ok",
  "service": "codemind-fzu-api",
  "version": "0.1.0",
  "timestamp": "2026-11-17T11:05:49.528697Z"
}
```

### 6.2 Swagger 文档

浏览器打开：<http://127.0.0.1:8000/docs>

应能看到 `GET /api/v1/health` 与 `POST /api/v1/ask` 两个接口，以及 `AskRequest`、`AskResponse` 等模型。

### 6.3 问答接口（Mock）

正常回答：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"大二申请院级奖学金需要什么条件？\"}"
```

PowerShell 里更推荐：

```powershell
$body = @{ query = "大二申请院级奖学金需要什么条件？" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/ask -Method Post `
  -ContentType "application/json; charset=utf-8" -Body $body
```

预期 `status = answered`，`answer` 以 `[Mock 演示]` 开头，并带 `warnings` 说明“未调用真实模型和知识库”。

Mock Agent 还内置两个分支，便于前端联调异常态：

| 请求 `query` | 预期 `status` | 说明 |
|---|---|---|
| `__mock_clarify__` | `needs_clarification` | 返回 `clarifying_question`，`answer` 为 null |
| `__mock_insufficient__` | `insufficient_evidence` | `answer_mode = insufficient_data` |
| 其他非空文本 | `answered` | 返回 `[Mock 演示]` 回答 |
| 空字符串或多余字段 | HTTP 422 | `error.code = INVALID_REQUEST` |

> 注意：`AskRequest` 配置了 `extra="forbid"`，请求体里出现未定义字段会直接 422；`query` 长度必须在 1～4000 之间。

### 6.4 PowerShell 中文乱码说明

`Invoke-WebRequest` / `Invoke-RestMethod` 在部分 Windows PowerShell 5.1 环境下会按 Latin-1 解码 JSON，终端里中文显示为乱码，但**接口返回本身是正确的 UTF-8**。可改用：

```powershell
curl.exe ... -o response.json
Get-Content response.json -Encoding UTF8
```

或在浏览器打开 `/docs` 用 “Try it out” 验证。

---

## 七、前端启动方法

前端代码尚未在当前仓库合入，**本节待前端成员完成后补充**。

预计约定（以实际合并代码为准）：

```powershell
# 前端目录与命令待定
npm install
npm run dev
```

前端启动后需要把后端地址配置为 `http://127.0.0.1:8000`，并注意跨域（CORS）配置。

---

## 八、运行测试

在仓库根目录执行：

```powershell
python -m unittest discover -s tests -v
```

预期结果：

```text
Ran 11 tests in 0.2s
OK
```

覆盖内容：

- `tests/test_interface_contracts.py`：公共契约模型、检索状态前置约束；
- `tests/test_mock_agent_api.py`：健康检查、正常回答、追问、证据不足、参数校验、默认应用 503。

> 若提示 `ModuleNotFoundError: No module named 'httpx'`，说明安装的是 `requirements.txt` 而非 `requirements-dev.txt`，补装即可：
> `python -m pip install -r backend/requirements-dev.txt`。

> 测试时可能出现 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`。这是依赖库的弃用提示，**不影响当前测试结果**；后续升级 Starlette 时再统一处理。

---

## 九、本次干净环境验证记录

| 检查项 | 结果 | 证据 |
|---|---|---|
| 从零创建 venv（Python 3.10.11） | 通过 | `evidence/versions.txt` |
| 依赖安装（requirements-dev） | 通过 | `evidence/versions.txt` |
| 启动 `backend.app.dev:app --reload` | 通过 | `screenshots/docs-swagger.png` |
| `GET /api/v1/health` | 200，`status=ok` | `screenshots/health.png`、`evidence/health.json` |
| `POST /api/v1/ask` 正常回答 | 200，`answered` | `evidence/normal.json` |
| `POST /api/v1/ask` 追问分支 | 200，`needs_clarification` | `evidence/clarify.json` |
| `POST /api/v1/ask` 证据不足分支 | 200，`insufficient_evidence` | `evidence/insufficient.json` |
| 空 query | 422，`INVALID_REQUEST` | `evidence/invalid.json` |
| `/docs` | 200，可打开 | `screenshots/docs-swagger.png` |
| 自动化测试 | 11 项全部通过 | `evidence/tests.txt` |

综合截图：`screenshots/api-demo.png`（环境、接口返回与测试结果汇总）。

---

## 十、常见问题与解决办法

### 1. `python` 不是 3.10，或 `py -3.10` 不存在

先确认版本：

```powershell
python --version
py -0p
```

若默认是 3.13 且依赖安装失败，请显式用 3.10 创建 venv：`py -3.10 -m venv .venv`，或安装 Python 3.10 后重试。

### 2. PowerShell 禁止运行 `Activate.ps1`

报错类似“无法加载文件……因为在此系统上禁止运行脚本”。只对当前窗口放开即可（无需改系统策略）：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

或干脆不激活，直接用 `.\.venv\Scripts\python.exe`。

### 3. `pip install` 很慢或超时

使用国内镜像：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r backend/requirements-dev.txt
```

### 4. `ModuleNotFoundError: No module named 'backend'`

原因：不在仓库根目录执行。请 `cd` 到包含 `backend/` 的目录后再启动/测试。

### 5. `uvicorn` 不是内部或外部命令

原因：虚拟环境未激活。用模块方式启动即可：

```powershell
python -m uvicorn backend.app.dev:app --reload
```

### 6. 端口 8000 被占用

报错 `[Errno 10048] error while attempting to bind on address ...`。查看并结束占用进程，或换端口：

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F

python -m uvicorn backend.app.dev:app --reload --port 8010
```

### 7. `/api/v1/ask` 返回 503 `SERVICE_NOT_CONFIGURED`

原因：启动的是 `backend.app.main:app`（未注入 Agent）。改用：

```powershell
python -m uvicorn backend.app.dev:app --reload
```

### 8. `/api/v1/ask` 返回 422 `INVALID_REQUEST`

常见原因：`query` 为空或超长（1～4000 字符）；请求体包含未定义字段（`extra="forbid"`）；`Content-Type` 不是 `application/json`。

### 9. 终端中文乱码

见 6.4。接口本身是 UTF-8，浏览器与 `curl -o` 保存后读取均正常。

### 10. 测试出现 Starlette/httpx 弃用警告

见第八节，当前不影响结果。

### 11. 已知代码问题：`backend/app/main.py` 使用 CR 换行

该文件在仓库中为 **CR（`\r`）单换行**，Git 视为非文本，`git diff` 与部分编辑器会把整份文件显示为一行。**Python 3.10 可正常导入和运行**（本次验证通过），因此不阻塞 Alpha；建议后端负责人在后续 PR 中统一为 LF/CRLF 并做一次格式化，避免多人协作时产生无意义的大 diff。

### 12. 前端启动失败

前端尚未合入，待前端成员提交后补充；若自行拉取前端分支，请确认 Node 版本与 `package.json` 要求一致，并检查后端 CORS 配置。

---

## 十一、Alpha 阶段已知限制

- Mock Agent 是确定性模拟实现，**不调用真实模型、不查知识库**，回答仅用于接口联调；
- 不保存会话历史，`conversation_id` 仅用于响应字段完整性；
- 无认证、无权限控制；
- 数据库、Chroma/BM25、Qwen、Tavily 均未接入；
- 后台管理 API 未实现。

这些限制与 `backend/README.md`、`docs/assignment-03/interface-contract-v1.md` 保持一致；接入真实模块时，接口字段与状态值不得擅自修改，需先与罗宇泽确认。

---

## 十二、变更记录

| 日期 | 变更 | 验证人 |
|---|---|---|
| 2026-11-17 | 初版：完成干净环境安装、Mock Agent 启动、健康检查/问答/docs/测试验证，补充常见问题 | 薛锦荣 |
