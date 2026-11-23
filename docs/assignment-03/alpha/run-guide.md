# Alpha 阶段运行说明（工程环境与部署支持）

> **Beta 提示（2026-11-23）**：本轮验收以本机运行为准，不要求云服务器/域名，会话使用
> `InMemoryConversationStore`，不需要 PostgreSQL。Windows 本机运行与干净环境验证的最新说明见
> [`docs/assignment-03/beta/windows-runtime-test.md`](../beta/windows-runtime-test.md)；
> 本文保留 Alpha 阶段的环境与联调记录，作为历史参考。

> 适用对象：CodeMind-FZU 全体开发成员
> 适用阶段：Alpha（FastAPI 真实运行入口 + AgentWorkflow/检索 + Vite 前端）
> 维护人：薛锦荣（工程环境与部署支持）
> 最后验证：2026-11-21，Windows 11 + Python 3.10.11 + Node 24.18.0
> 验证方式：全新 Python 虚拟环境安装、按本文命令启动前后端、完成接口联调与构建

---

## 一、环境要求

| 项目 | 要求 | 本次验证环境 |
|---|---|---|
| 操作系统 | Windows / macOS / Linux | Windows 11 |
| Python | **3.10 及以上**（推荐 3.10 / 3.11） | Python 3.10.11 |
| Node.js | **18.18 及以上**（推荐 20 / 22 LTS） | Node 24.18.0 |
| npm | 随 Node 安装（推荐 9+） | npm 11.16.0 |
| 浏览器 | Chrome / Edge | Edge |
| 网络 | 首次安装依赖需要（可用国内镜像） | 清华 PyPI / npmmirror |
| 数据库 | 不需要（会话为内存存储） | — |
| Qwen 密钥 | **仅真实入口需要**；Mock 不需要 | 本轮未使用真实密钥 |

前端技术栈统一为 **Vite + 原生 TypeScript（HTML + CSS）**，不引入 React、Vue。

---

## 二、获取代码

```bash
git clone https://github.com/yz-Yezi-Genm/CodeMind-FZU.git
cd CodeMind-FZU
```

除前端安装命令外，后续命令均在**仓库根目录**执行。

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

PowerShell 禁止脚本时，仅对当前窗口放开：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 3.2 安装依赖

```powershell
python -m pip install -r backend/requirements.txt
```

国内镜像：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r backend/requirements.txt
```

跑完整测试/验证脚本时再安装：

```powershell
python -m pip install -r scripts/requirements-alpha-verification.txt
```

本次干净环境版本：fastapi 0.162.5、pydantic 2.14.3、uvicorn 0.54.0、httpx 0.28.1。

---

## 四、启动后端

### 4.1 真实 Alpha 入口（推荐）

```powershell
copy backend\.env.example backend\.env
# 编辑 backend\.env，填写 QWEN_API_KEY
python -m uvicorn backend.app.alpha:app --reload --port 8000 --env-file backend/.env
```

真实入口启动时会：

1. 读取 `ALPHA_PACKAGE_DIR`（默认 `knowledge_base/processed/alpha/approved/`）；
2. 只加载人工审核通过、`retrieval_status=enabled` 的资料包；
3. 初始化 Qwen 客户端并装配 `AgentWorkflow` 与会话历史。

**缺少密钥或已审核资料时**：服务仍可启动，但 `/api/v1/ask` 返回 503（如 `KNOWLEDGE_BASE_UNAVAILABLE`），不会伪造回答。

### 4.2 Mock Agent（前后端联调，无需密钥）

```powershell
python -m uvicorn backend.app.dev:app --reload --port 8000
```

### 4.3 默认骨架入口

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

未注入 Agent，`/api/v1/ask` 返回 `503 SERVICE_NOT_CONFIGURED`，属预期行为。

### 4.4 离线检查（不调用真实模型）

```powershell
python -m scripts.check_retrieval_agent
python -m scripts.check_document_processing
python -m examples.agent_workflow_demo
```

---

## 五、环境变量与 Qwen 配置

### 5.1 复制模板

```powershell
copy backend\.env.example backend\.env
```

`backend/.env` 已被 `.gitignore` 忽略，**不会提交**；模板不含真实密钥。

### 5.2 变量说明

| 变量 | 是否必填 | 默认/示例 | 说明 |
|---|---|---|---|
| `CORS_ALLOW_ORIGINS` | 可选 | 覆盖 5173/3000/5500 | 逗号分隔，禁止 `*` |
| `QWEN_API_KEY` | 真实调用必填 | 空 | 仅本地保存，禁止提交 |
| `QWEN_BASE_URL` | 可选 | DashScope compatible | 必须是 http(s) |
| `QWEN_MODEL` | 可选 | `qwen-flash` | 需账号有权限 |
| `QWEN_TIMEOUT_SECONDS` | 可选 | `28` | 必须 > 0 |
| `QWEN_MAX_RETRIES` | 可选 | `0` | 0–3 |
| `ALPHA_PACKAGE_DIR` | 可选 | `knowledge_base/processed/alpha/approved` | 已审核资料目录 |
| `CONVERSATION_MAX_MESSAGES` | 可选 | `12` | 2–50；奇数向下取整为完整轮次 |
| `CONVERSATION_HISTORY_CHAR_LIMIT` | 可选 | `6000` | 200–50000 |
| `CONVERSATION_MAX_COUNT` | 可选 | `1000` | 内存会话上限 |
| `CONVERSATION_IDLE_SECONDS` | 可选 | `3600` | 空闲回收 |
| `CONVERSATION_CLEANUP_INTERVAL_SECONDS` | 可选 | `300` | 清理间隔 |

### 5.3 加载方式与验证

```powershell
python -m uvicorn backend.app.alpha:app --port 8000 --env-file backend/.env
```

已验证：修改 `CORS_ALLOW_ORIGINS` 后，响应头只允许新配置来源。

### 5.4 Qwen 配置要点

1. 在阿里云 DashScope 控制台创建 API Key；
2. 仅写入本地 `backend/.env` 或系统环境变量；
3. 默认使用 DashScope 的 OpenAI-compatible 端点与 `qwen-flash`；
4. 未配置密钥时 Mock 不受影响，真实入口问答返回 503；
5. 密钥不得进入仓库、PR、命令历史或截图。

---

## 六、知识库加载与审核资料

1. 资料包为 `DocumentPackage` JSON，默认目录 `knowledge_base/processed/alpha/approved/`；
2. 只接受 `retrieval_status=enabled` 且 manifest/`temporal_notes` 人工审核标记为严格 `true` 的资料；
3. `LocalBM25Retriever` 建立内存索引，同一实例用于索引和检索；
4. 任一份资料索引失败、产生 warnings 或目录为空时，正式问答整体 503，不会部分开放；
5. 原始样例（`knowledge_base/processed/alpha/*.json`）仍为 `blocked`，不进入正式问答。

参考：`backend/retrieval/alpha_corpus.py`、`scripts/run_alpha_agent.py`。

---

## 七、后端接口验证

### 7.1 健康检查

<http://127.0.0.1:8000/api/v1/health>，预期 `status=ok`。

### 7.2 Swagger

<http://127.0.0.1:8000/docs>，应看到 `GET /api/v1/health`、`POST /api/v1/ask`。

### 7.3 问答接口

Mock 入口分支：

| `query` | 预期状态 |
|---|---|
| `__mock_clarify__` | `needs_clarification` |
| `__mock_insufficient__` | `insufficient_evidence` |
| 其他非空文本 | `answered` |
| 空 / 多余字段 | 422 `INVALID_REQUEST` |

真实入口在缺少密钥/审核资料时返回 503；配置齐全后返回 `answered` / `needs_clarification` / `insufficient_evidence` 与引用。

> PowerShell 5.1 可能把 JSON 中文按 Latin-1 解码显示乱码，接口本身是 UTF-8；可保存文件后 `Get-Content -Encoding UTF8` 查看。

---

## 八、前端环境

```text
frontend/
├── index.html              # 学生端
├── admin/index.html        # 后台管理端
├── src/student/            # 学生端问答页面
├── src/admin/              # 管理端页面
├── src/shared/             # api.ts / types.ts / dom.ts / styles.css
├── package.json / package-lock.json
├── tsconfig.json / vite.config.ts
└── README.md
```

### 8.1 安装

```bash
cd frontend
npm install
```

国内镜像：`npm install --registry=https://registry.npmmirror.com`。

### 8.2 启动

```bash
npm run dev
```

| 页面 | 地址 |
|---|---|
| 学生端 | <http://127.0.0.1:5173/> |
| 后台管理端 | <http://127.0.0.1:5173/admin/index.html> |

### 8.3 构建与预览

```bash
npm run build      # tsc 严格检查 + vite build
npm run preview    # http://127.0.0.1:4173/
```

---

## 九、前后端联调

### 9.1 代理

Vite 已把 `/api` 代理到 `http://127.0.0.1:8000`：

```text
浏览器 /api/v1/xxx → Vite(5173) → FastAPI(8000)
```

前端统一使用相对路径 `/api/v1/...`，不写死后端地址。

### 9.2 同时启动

```powershell
# 终端 1（仓库根目录）
python -m uvicorn backend.app.dev:app --reload --port 8000   # 或 alpha 真实入口

# 终端 2
cd frontend
npm run dev
```

访问 <http://127.0.0.1:5173/>，学生端状态条显示“后端已连接”即可联调。

### 9.3 入口选择

| 场景 | 入口 | 行为 |
|---|---|---|
| Mock 联调 | `backend.app.dev:app` | 固定模拟回答，无需密钥 |
| 真实 Alpha | `backend.app.alpha:app` | 审核资料 + Qwen，缺配置时 503 |
| 默认骨架 | `backend.app.main:app` | 问答固定 503 |

---

## 十、测试与检查

### 10.1 全仓库测试

```powershell
python -m unittest discover -s tests -v
```

本次干净环境结果：**262 项执行，235 通过、27 跳过、0 失败**。

跳过项主要来自环境限制与未启用的真实验收（Windows 符号链接权限、真实 Qwen 验收开关、业务规则替身等），不是失败。

### 10.2 专项检查

```powershell
python -m scripts.check_retrieval_agent
python -m scripts.check_document_processing
```

结果：`check_retrieval_agent` 的 4 个用例全部 PASS（三个真实样例按审核门槛安全拒答，合成测试资料在带 `temporal_notes.human_approved=true` 时正常回答），退出码 0；`check_document_processing` 为 `successful=true`。

### 10.3 前端

```bash
cd frontend
npm ci
npm run build
```

本次均成功，锁文件可复现安装。

---

## 十一、干净环境验证记录（2026-11-21）

| 检查项 | 结果 | 证据 |
|---|---|---|
| 全新 Python 3.10.11 venv + 运行依赖 | 通过 | `evidence/runtime/versions.txt` |
| 完整验证依赖（pytest 等） | 通过 | 同上 |
| 全仓库测试 | 262 项，235 通过、27 跳过、0 失败 | `evidence/runtime/tests.txt` |
| `scripts.check_document_processing` | successful=true | `evidence/runtime/check-document-processing.txt` |
| `scripts.check_retrieval_agent` | 4 个用例 PASS，退出码 0 | `evidence/runtime/check-retrieval-agent.txt` |
| 真实入口启动（无密钥/无审核包） | 可启动，问答 503 | `evidence/runtime/runtime-http-check.json` |
| Mock 入口 health/docs/ask | 200 | 同上 |
| `.env` 加载与 CORS 覆盖 | 生效 | `evidence/runtime/env-file-cors-check.json` |
| `npm ci` + `npm run build` | 通过 | `evidence/runtime/frontend-ci-build.txt` |
| 学生端 / 管理端 / Vite 代理 | 200，正常 | `screenshots/frontend-student.png`、`frontend-admin.png` |

> 真实 Qwen 正向验收未执行：本轮未使用真实密钥与正式审核资料。

---

## 十二、常见问题

### 1. `python` 不是 3.10
`py -3.10 -m venv .venv` 指定版本。

### 2. PowerShell 禁止 `Activate.ps1` / `npm.ps1`
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`，或用 `npm.cmd`。

### 3. pip 慢
使用清华镜像。

### 4. `ModuleNotFoundError: No module named 'backend'`
不在仓库根目录。

### 5. `uvicorn` 找不到
未激活 venv，使用 `python -m uvicorn ...`。

### 6. 端口占用（8000 / 5173）
`netstat -ano | findstr :8000` + `taskkill /PID <PID> /F`；Vite `strictPort` 会直接报错。

### 7. 真实入口 `/api/v1/ask` 返回 503
检查：`QWEN_API_KEY` 是否配置、`ALPHA_PACKAGE_DIR` 是否有审核通过且 `enabled` 的资料包、启动日志中的错误码。这是“缺配置”的预期行为，不是代码崩溃。

### 8. Mock 入口 503
使用了 `backend.app.main:app`；改用 `backend.app.dev:app`。

### 9. 前端显示“后端未连接”
确认 8000 已启动，且在 `frontend/` 下执行 `npm run dev`；访问 <http://127.0.0.1:5173/api/v1/health> 检查代理。

### 10. 管理端提示后台接口不可用（`RESOURCE_NOT_FOUND`）
管理端业务 API 尚未实现，属当前边界。

### 11. 系统代理导致脚本访问 127.0.0.1 出现 502
Python 脚本用 `httpx.Client(trust_env=False)`，或在代理软件中把 `127.0.0.1/localhost` 设为直连。

### 12. 测试出现 Starlette/httpx 弃用提示
不影响结果。

---

## 十三、已知限制

- 真实 Qwen 未使用真实密钥做正向验收；
- `approved/` 尚无正式审核包时，真实问答 503；
- 无持久化会话、无认证、无管理端 API；
- Chroma/RRF 未接入，当前为本地 BM25。

接口字段与状态值以 `docs/assignment-03/interface-contract-v1.md` 为准。

---

## 十四、变更记录

| 日期 | 变更 | 验证人 |
|---|---|---|
| 2026-11-17 | 初版：Mock、前端工程与联调 | 薛锦荣 |
| 2026-11-17 | 同步 #19 文档解析，69 项测试 | 薛锦荣 |
| 2026-11-19 | 同步 main，171 项测试，`.env` 与 CORS 验证，Python 3.10 超时修复 | 薛锦荣 |
| 2026-11-21 | 同步真实运行入口 #34/#35/#36/#39：262 项测试、`backend.app.alpha:app`、`ALPHA_PACKAGE_DIR`、会话参数、Windows 清理测试可移植性修复 | 薛锦荣 |
