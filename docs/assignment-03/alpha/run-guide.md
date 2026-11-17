# Alpha 阶段运行说明（工程环境与部署支持）

> 适用对象：CodeMind-FZU 全体开发成员
> 适用阶段：Alpha（后端接口骨架 + Mock Agent + 前端工程骨架）
> 维护人：薛锦荣（工程环境与部署支持）
> 最后验证：2026-11-17，Windows 11 + Python 3.10.11 + Node 24.18.0
> 验证方式：从零创建 Python/Node 环境，按本文命令启动前后端、完成接口联调与构建

本文说明如何在**本地**把 CodeMind-FZU 的 Alpha 环境跑起来：

- 后端：FastAPI 接口骨架 + Mock Agent（无需数据库、无需 Qwen/Tavily 密钥）
- 前端：Vite + 原生 TypeScript 多页面应用（学生端 / 后台管理端）

---

## 一、环境要求

| 项目 | 要求 | 本次验证环境 |
|---|---|---|
| 操作系统 | Windows / macOS / Linux | Windows 11 |
| Python | **3.10 及以上**（推荐 3.10 / 3.11） | Python 3.10.11 |
| Node.js | **18.18 及以上**（推荐 20 LTS / 22 LTS） | Node 24.18.0 |
| npm | 随 Node 安装（推荐 9+） | npm 11.16.0 |
| 浏览器 | Chrome / Edge（访问 `/docs` 与前端页面） | Edge |
| 网络 | 仅首次安装依赖时需要（可用国内镜像） | 清华 PyPI 镜像 / npmmirror |
| 数据库 / 密钥 | **不需要**（Mock 阶段） | — |

> 前端技术栈已统一为 **Vite + 原生 TypeScript（HTML + CSS）**，不引入 React、Vue 等框架。具体业务页面由吴欣键、洪添军、林彦翔等负责人基于该工程开发。

---

## 二、获取代码

```bash
git clone https://github.com/yz-Yezi-Genm/CodeMind-FZU.git
cd CodeMind-FZU
```

后续命令（除前端安装外）都在**仓库根目录**执行；不在根目录会出现 `ModuleNotFoundError: No module named 'backend'`。

---

## 三、后端环境

### 3.1 创建虚拟环境

Windows（PowerShell）：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

若 PowerShell 禁止运行脚本，仅对当前窗口放开：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

也可以不激活，直接用 `.\.venv\Scripts\python.exe`。

### 3.2 安装依赖

```powershell
python -m pip install -r backend/requirements.txt
```

国内网络建议加镜像：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r backend/requirements.txt
```

说明：

- `backend/requirements.txt` 已包含 `fastapi`、`pydantic`、`uvicorn[standard]`、`httpx`；
- `backend/requirements-dev.txt` 目前等价于 `-r requirements.txt`（预留后续测试工具），跑测试**不需要额外安装**；
- 本次安装到的版本：fastapi 0.162.5、pydantic 2.14.3、uvicorn 0.54.0、httpx 0.28.1。

---

## 四、启动后端

### 4.1 Mock Agent（前后端联调推荐）

```powershell
python -m uvicorn backend.app.dev:app --reload --port 8000
```

成功标志：

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### 4.2 默认入口（未注入 Agent）

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

该入口没有注入 Agent，`POST /api/v1/ask` 会返回 `503 SERVICE_NOT_CONFIGURED`，属**预期行为**。日常联调请用 4.1 的 `dev:app`。

### 4.3 可选：读取本地环境变量

Qwen 适配器与 CORS 支持从本地 `.env` 读取配置（**不要提交密钥**）：

```powershell
copy backend\.env.example backend\.env
python -m uvicorn backend.app.dev:app --reload --port 8000 --env-file backend/.env
```

---

## 五、后端接口验证

### 5.1 健康检查

浏览器打开 <http://127.0.0.1:8000/api/v1/health>，或用命令：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

预期：

```json
{
  "status": "ok",
  "service": "codemind-fzu-api",
  "version": "0.1.0",
  "timestamp": "2026-11-17T13:47:38.875682Z"
}
```

### 5.2 Swagger 文档

浏览器打开 <http://127.0.0.1:8000/docs>，可看到 `GET /api/v1/health`、`POST /api/v1/ask` 及公共模型。

### 5.3 问答接口（Mock）

```powershell
$body = @{ query = "大二申请院级奖学金需要什么条件？" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/ask -Method Post `
  -ContentType "application/json; charset=utf-8" -Body $body
```

Mock Agent 内置分支：

| 请求 `query` | 预期 `status` | 说明 |
|---|---|---|
| `__mock_clarify__` | `needs_clarification` | 返回 `clarifying_question`，`answer` 为 null |
| `__mock_insufficient__` | `insufficient_evidence` | `answer_mode = insufficient_data` |
| 其他非空文本 | `answered` | 返回 `[Mock 演示]` 回答 |
| 空字符串 / 多余字段 | HTTP 422 | `error.code = INVALID_REQUEST` |

> `AskRequest` 为 `extra="forbid"`，请求体出现未定义字段会直接 422；`query` 长度为 1–4000。

### 5.4 PowerShell 中文乱码

Windows PowerShell 5.1 的 `Invoke-WebRequest` 可能按 Latin-1 解码 JSON，终端显示乱码，但**接口返回本身是 UTF-8**。可改用：

```powershell
curl.exe ... -o response.json
Get-Content response.json -Encoding UTF8
```

或在浏览器 `/docs` 中用 “Try it out” 验证。

---

## 六、前端环境

代码位于仓库根目录 `frontend/`，结构：

```text
frontend/
├── index.html              # 学生端入口
├── admin/index.html        # 后台管理端入口
├── src/
│   ├── student/main.ts
│   ├── admin/main.ts
│   └── shared/             # api.ts / types.ts / dom.ts / styles.css
├── package.json
├── package-lock.json
├── tsconfig.json           # 严格模式
├── vite.config.ts          # 5173 端口 + /api 代理
└── README.md
```

### 6.1 安装依赖

```bash
cd frontend
npm install
```

- 请**提交 `package-lock.json`**，不要提交 `node_modules/`；
- 国内网络较慢时：`npm install --registry=https://registry.npmmirror.com`。

### 6.2 启动开发服务器

```bash
npm run dev
```

固定监听 **5173** 端口（`strictPort`）：

| 页面 | 地址 |
|---|---|
| 学生端 | <http://127.0.0.1:5173/> |
| 后台管理端 | <http://127.0.0.1:5173/admin/index.html> |

页面顶部的状态条会请求 `/api/v1/health`，显示“后端已连接”即表示前后端链路正常。

### 6.3 生产构建

```bash
npm run build      # 先 tsc 严格类型检查，再 vite build
npm run preview    # 本地预览 dist，默认 http://127.0.0.1:4173/
```

构建产物：`dist/index.html`、`dist/admin/index.html` 及 `dist/assets/`。`dist/` 已在 `.gitignore` 中。

---

## 七、前后端联调

### 7.1 API 代理

Vite 开发服务器已配置：

```text
前端请求 /api/v1/xxx  →  Vite dev server（5173）  →  http://127.0.0.1:8000/api/v1/xxx
```

因此前端统一使用相对路径 `/api/v1/...`，不写死后端地址，也不需要在开发期处理跨域。

### 7.2 同时启动前后端

开两个终端：

```powershell
# 终端 1：后端（仓库根目录，已激活 venv）
python -m uvicorn backend.app.dev:app --reload --port 8000

# 终端 2：前端
cd frontend
npm run dev
```

然后访问 <http://127.0.0.1:5173/>，在学生端输入问题即可看到 Mock 回答。

### 7.3 当前 Mock 与未来真实 Agent 的区别

| 场景 | 启动方式 | 行为 |
|---|---|---|
| 当前 Mock 联调 | `backend.app.dev:app` | 注入 `MockAgentService`，返回固定的模拟回答/追问/证据不足，不调用模型与知识库 |
| 默认骨架 | `backend.app.main:app` | 未注入 Agent，`/api/v1/ask` 返回 503 |
| 未来真实 Agent | 由后端把真实 `AgentService` 注入 `create_app()`（预计替换 `dev.py` 的 Mock 注入） | 同一套 `/api/v1` 契约，前端代码**无需改动** |

真实 Qwen 调用需要本地配置 `QWEN_API_KEY` 等环境变量；密钥只放在本地 `.env`，禁止提交。

---

## 八、运行测试

在仓库根目录执行：

```powershell
python -m unittest discover -s tests -v
```

本次结果：**Ran 30 tests，OK**（约 1.5 秒）。

覆盖：

- `test_interface_contracts.py`：公共契约、检索状态约束；
- `test_mock_agent_api.py`：健康检查、正常回答、追问、证据不足、参数校验、默认入口 503；
- `test_backend_runtime.py`：CORS、错误 envelope、Agent 适配、request_id 传递；
- `test_qwen_client.py`：Qwen 适配器的成功、超时、限流、重试、缺失密钥等。

> 测试中可能出现 `StarletteDeprecationWarning`（httpx TestClient 弃用提示），不影响结果；后续升级 Starlette 时统一处理。

---

## 九、本次验证记录

| 检查项 | 结果 | 证据 |
|---|---|---|
| Python 3.10.11 全新 venv + 依赖安装 | 通过 | `evidence/versions.txt` |
| 后端 `backend.app.dev:app --reload` | 启动成功 | `screenshots/docs-swagger.png` |
| `GET /api/v1/health` | 200 `status=ok` | `screenshots/health.png`、`evidence/health.json` |
| `POST /api/v1/ask` 正常/追问/证据不足 | 200，状态正确 | `evidence/normal.json`、`clarify.json`、`insufficient.json` |
| 空 query | 422 `INVALID_REQUEST` | `evidence/invalid.json` |
| `/docs` | 200 | `screenshots/docs-swagger.png` |
| 前端 `npm install` + `npm run dev` | 启动成功（5173） | `screenshots/frontend-student.png`、`frontend-admin.png` |
| 前端经代理调用后端 | 200，返回 Mock 回答 | `evidence/vite-proxy-ask.json`、`vite-proxy-health.json` |
| `npm run build` | 成功，产出两个页面 | `evidence/frontend-build.txt` |
| Python 测试 | 30 项全部通过 | `evidence/tests.txt` |
| 汇总截图 | — | `screenshots/api-demo.png` |

---

## 十、常见问题

### 1. `python` 不是 3.10

```powershell
python --version
py -0p
```

用 `py -3.10 -m venv .venv` 显式指定版本。

### 2. PowerShell 禁止运行 `Activate.ps1` 或 `npm.ps1`

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

npm 也可直接用 `npm.cmd install` / `npm.cmd run dev`。

### 3. `pip install` 慢或超时

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r backend/requirements.txt
```

### 4. `ModuleNotFoundError: No module named 'backend'`

不在仓库根目录执行。`cd` 到包含 `backend/` 的目录后再启动或测试。

### 5. `uvicorn` 不是内部或外部命令

虚拟环境未激活，用模块方式：`python -m uvicorn backend.app.dev:app --reload --port 8000`。

### 6. 端口被占用（8000 / 5173）

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

Vite 使用 `strictPort`，5173 被占用会直接报错而不是自动换端口；如改端口，请同步后端 `CORS_ALLOW_ORIGINS`。

### 7. `/api/v1/ask` 返回 503 `SERVICE_NOT_CONFIGURED`

使用了 `backend.app.main:app`。改用 `backend.app.dev:app`。

### 8. `/api/v1/ask` 返回 422 `INVALID_REQUEST`

`query` 为空/超长，或请求体包含未定义字段，或 `Content-Type` 不是 `application/json`。

### 9. 前端页面显示“后端未连接”

- 确认后端已在 8000 端口启动；
- 确认在 `frontend/` 目录执行 `npm run dev`（代理配置只在该目录生效）；
- 打开 <http://127.0.0.1:5173/api/v1/health> 检查代理是否正常。

### 10. `npm install` 报 esbuild / 安装脚本警告

npm 新版本可能提示 `allow-scripts`；当前 Vite 5 + esbuild 在本次环境（npm 11）可直接完成安装与构建。若构建时报 esbuild 二进制缺失，执行：

```bash
npm rebuild esbuild
```

### 11. 访问 `localhost:5173` 打不开，但 `127.0.0.1:5173` 可以

Vite 已固定 `host: '127.0.0.1'`，请使用文档中的 `127.0.0.1` 地址；`localhost` 在部分环境解析到 IPv6 会失败。

### 12. 本机开了系统代理，脚本访问 127.0.0.1 出现 502

部分 HTTP 客户端会读取 Windows 系统代理，把 localhost 也转发出去。浏览器访问不受影响；脚本可显式绕过（例如 Python `httpx.Client(trust_env=False)`），或在代理软件中把 `127.0.0.1/localhost` 加入直连。

### 13. 测试出现 Starlette/httpx 弃用警告

见第八节，不影响当前结果。

---

## 十一、Alpha 阶段已知限制

- Mock Agent 为确定性模拟实现，不调用真实模型与知识库；
- 不保存会话历史，`conversation_id` 仅保证响应字段完整；
- 无认证与权限控制；
- 数据库、Chroma/BM25、真实 Qwen 调用、Tavily 尚未接入；
- 前端只提供工程入口与问答联调示例，业务页面由对应负责人继续开发。

接口字段与状态值以 `docs/assignment-03/interface-contract-v1.md` 为准，不得擅自修改。

---

## 十二、变更记录

| 日期 | 变更 | 验证人 |
|---|---|---|
| 2026-11-17 | 初版：后端干净环境、Mock 启动、接口与测试验证 | 薛锦荣 |
| 2026-11-17 | 增加 Vite + TypeScript 前端工程、代理联调、构建与双端启动说明；测试更新为 30 项 | 薛锦荣 |
