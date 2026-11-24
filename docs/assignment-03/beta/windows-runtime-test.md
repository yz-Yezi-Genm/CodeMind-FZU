# Beta 阶段 Windows 本机运行与干净环境验证记录

> 适用对象：未参与开发的验收人员、新加入的开发成员
> 适用阶段：Beta（本机运行、单进程、InMemoryConversationStore，不依赖数据库与云服务器）
> 维护人：薛锦荣（Windows 本机运行与工程交付）
> 代码基线：`origin/main` @ `a789f53`（本分支合并提交 `27f7c45`，已含 PR #43/#47）
> 验证时间：2026-11-23
> 验证结论：**后端三个入口、前端、前后端联调在本机全部跑通**；真实 Qwen 正向问答需「审核通过的正式资料包 **且** 有效 API Key」两者**同时具备**，当前**尚未验证**，见第六节。

---

## 一、本阶段运行方式说明

| 项目 | Beta 约定 |
|---|---|
| 运行形态 | 本机单进程运行，前后端各一个进程 |
| 会话存储 | `InMemoryConversationStore`（仅内存，重启即清空） |
| 数据库 | **不需要**（本轮不要求 PostgreSQL 持久化） |
| 部署 | **不需要**云服务器与域名 |
| 知识库 | 只加载 `knowledge_base/processed/alpha/approved/` 下**人工审核通过**且 `retrieval_status=enabled` 的资料包 |
| 真实模型 | 仅 `backend.app.alpha:app` 入口使用 Qwen；`backend.app.dev:app` 为 Mock，不需要密钥 |
| 学生端登录 | PR #47 起为**前端演示登录门禁**：输入任意账号/密码即可进入工作台，不做真实鉴权 |

> 验收演示可以先走 Mock 入口（无需任何密钥/资料）；真实问答另需满足第六节的两个条件。

---

## 二、环境要求与本机实测版本

| 项目 | 要求 | 本次实测 |
|---|---|---|
| 操作系统 | Windows 10/11（macOS、Linux 同理） | Windows 11 家庭中文版 10.0.26200 64 位 |
| Python | **3.10 及以上**（推荐 3.10/3.11） | Python 3.10.11（`py -3.10`） |
| 后端依赖 | `backend/requirements.txt` | fastapi 0.162.5、pydantic **2.14.4**、uvicorn 0.54.0、httpx 0.28.1 |
| 验证依赖（跑测试） | `scripts/requirements-alpha-verification.txt` | pytest 9.2.0、pytest-subtests 0.15.0 |
| Node.js | **≥ 18.18**（推荐 20/22 LTS） | Node v24.18.0 |
| npm | 随 Node 安装 | npm 11.16.0 |
| 浏览器 | Chrome / Edge | Microsoft Edge |
| 网络 | 首次安装依赖需要（可用国内镜像） | 清华 PyPI / npmmirror |

版本明细见 [`evidence/versions.txt`](evidence/versions.txt)。

---

## 三、干净环境验证步骤（可直接照做）

以下命令**除特别注明外均在仓库根目录执行**，并且**以 `main` 为基线**（不需要切换到开发分支）。

### 3.1 获取代码

```powershell
git clone https://github.com/yz-Yezi-Genm/CodeMind-FZU.git
cd CodeMind-FZU
git switch main
git log --oneline -1        # 记录验证用的提交号
```

### 3.2 后端：创建虚拟环境并安装依赖

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 仅运行：只需运行依赖
python -m pip install -r backend/requirements.txt

# 需要跑测试/验证脚本时，再装验证依赖
python -m pip install -r scripts/requirements-alpha-verification.txt
```

国内网络可加镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple`。
如果 PowerShell 禁止运行脚本：`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`。

### 3.3 后端：配置环境变量

```powershell
copy backend\.env.example backend\.env
# 用编辑器打开 backend\.env，填写真实的 QWEN_API_KEY（仅本地，禁止提交）
```

- `backend/.env` 已被 `.gitignore` 忽略，**不会提交**；
- `.env.example` 只放占位，不放真实 Key；
- 变量名称与代码一致（`QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`、`QWEN_TIMEOUT_SECONDS`、`QWEN_MAX_RETRIES`、`ALPHA_PACKAGE_DIR`、`CONVERSATION_*`、`CORS_ALLOW_ORIGINS`），已逐项与
  `backend/app/config.py`、`backend/services/qwen_client.py` 核对。

### 3.4 后端：启动（三个入口按需选一个）

| 入口 | 命令 | 说明 |
|---|---|---|
| Mock（联调/演示） | `python -m uvicorn backend.app.dev:app --reload --port 8000` | 固定模拟回答，无需密钥/资料 |
| 真实 Alpha | `python -m uvicorn backend.app.alpha:app --reload --port 8000 --env-file backend/.env` | 需要 Key + 审核资料 |
| 默认骨架 | `python -m uvicorn backend.app.main:app --reload --port 8000` | 问答固定 503，仅用于契约自检 |

> `--env-file` 是 uvicorn 的参数，**没有它不会自动读取 `backend/.env`**。

### 3.5 后端：健康检查

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

期望：`{"status":"ok","service":"codemind-fzu-api","version":"0.1.0",...}`，HTTP 200。
Swagger 文档：<http://127.0.0.1:8000/docs>

### 3.6 前端：安装与启动

```powershell
cd frontend
npm ci
npm run dev
```

| 页面 | 地址 |
|---|---|
| 学生端（演示登录页） | <http://127.0.0.1:5173/> |
| 学生端工作台 | 登录后自动进入 |
| 后台管理端 | <http://127.0.0.1:5173/admin/index.html> |

进入工作台后右上角显示「**后端已连接**」即联调成功（见
[`evidence/screenshots/student-workspace.png`](evidence/screenshots/student-workspace.png)）。

### 3.7 前端：构建

```powershell
npm run build      # tsc --noEmit && vite build
npm run preview    # 本地预览 dist，http://127.0.0.1:4173/
```

### 3.8 关闭服务

前后端终端均按 `Ctrl + C`；`--reload` 模式会提示 `Shutting down`。
端口被占用时：

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

---

## 四、验证结果

### 4.1 三个后端入口（干净 clone）

| 入口 | `GET /api/v1/health` | `POST /api/v1/ask` |
|---|---|---|
| `backend.app.dev:app`（Mock） | 200 | 200 `answered`（带 `MOCK_AGENT` 警告） |
| `backend.app.alpha:app`（真实入口，无审核语料） | 200 | 503 `KNOWLEDGE_BASE_UNAVAILABLE` |
| `backend.app.main:app`（默认骨架） | 200 | 503 `SERVICE_NOT_CONFIGURED` |

真实入口启动日志（无语料时）：

```text
Approved corpus rejected loaded=0 skipped=0 detail=
Alpha runtime startup unavailable code=KNOWLEDGE_BASE_UNAVAILABLE
```

服务仍可启动，问答按预期返回 503，不伪造回答。

### 4.2 四大业务场景（Mock 入口，仅验证接口链路）

| 场景编号 | 问句 | 结果 |
|---|---|---|
| S1 奖助学金 | 国家奖学金申请需要哪些条件？ | 200 `answered` |
| S2 奖学金（学院级） | 计算机学院院级奖学金怎么评定？ | 200 `answered` |
| S3 竞赛认定 | 学科竞赛项目级别怎么认定？ | 200 `answered` |
| S4 学院资源导航 | 学院有哪些实验室？ | 200 `answered` |

> 四句均返回 Mock 固定文案，**只能证明接口链路与四类入口可用，不能代表真实政策结论**；真实结论必须由审核语料 + Qwen 生成并附引用。

### 4.3 状态分支与错误码（Mock 入口）

| 请求 | 预期 | 实测 |
|---|---|---|
| `{"query":"__mock_clarify__"}` | `needs_clarification` | 200，`clarifying_question` 非空 |
| `{"query":"__mock_insufficient__"}` | `insufficient_evidence` | 200，`answer_mode=insufficient_data` |
| `{"query":""}` | 422 | 422 `INVALID_REQUEST` |
| `{"conversation_id":"not-a-uuid"}` | 422 | 422 `INVALID_REQUEST` |
| `GET /api/v1/not-exist` | 404 | 404 `RESOURCE_NOT_FOUND` |

完整请求/响应见 [`evidence/runtime-http-check.txt`](evidence/runtime-http-check.txt)。

### 4.4 上游集成验证（PR #35/#36）

仓库提供的独立验证脚本：

```powershell
git fetch origin feat/alpha-business-rules-runtime feat/alpha-retrieval-loader
python -m scripts.verify_alpha_upstream_integration
```

本次结果：**25 项集成用例全部通过（OK，退出码 0）**，与测试套件中被跳过的 25 项一一对应。
日志见 [`evidence/upstream-integration.txt`](evidence/upstream-integration.txt)。

### 4.5 前端与联调

| 检查项 | 结果 |
|---|---|
| 干净 clone `npm ci` | 成功（12 个包） |
| `npm run build`（含 `tsc --noEmit`） | 成功，dist 产物完整（学生端 + 管理端） |
| `npm run dev` 学生端 / 管理端 | 均 HTTP 200 |
| 演示登录门禁 → 工作台 | 输入任意账号密码可进入 |
| 工作台后端状态 | 显示「后端已连接」 |
| Vite 代理 `/api/v1/health` | 200 |
| Vite 代理 `/api/v1/ask`（S4 问句） | 200 `answered` |

构建日志见 [`evidence/frontend-ci-build.txt`](evidence/frontend-ci-build.txt)。

### 4.6 测试套件（干净 clone）

```powershell
python -m unittest discover -s tests -v
```

**结果：275 项执行，通过 247、跳过 28、失败 0。**

28 项跳过的构成（按 `unittest` 输出的 skip reason 统计）：

| 数量 | 原因 | 说明 |
|---|---|---|
| 25 | `Run scripts.verify_alpha_upstream_integration for PR #35/#36 integration` | 等待单独执行的上游集成脚本，已在 4.4 执行并通过 |
| 2 | 真实 Qwen 验收需显式开关（`RUN_LIVE_QWEN_TESTS=1`）且需审核语料 | 见第六节 |
| 1 | 当前 Windows 账户不允许创建符号链接 | 环境限制，非代码问题 |

完整日志见 [`evidence/tests-clean-env.txt`](evidence/tests-clean-env.txt)。

### 4.7 关闭与重启

`Ctrl + C` 停止 uvicorn 与 Vite，均正常退出、端口释放；重启后 `/api/v1/health` 仍为 200，内存会话按约定清空。

---

## 五、常见错误及解决方法

| # | 现象 | 原因 | 解决 |
|---|---|---|---|
| 1 | `ModuleNotFoundError: No module named 'backend'` | 不在仓库根目录 | `cd` 到仓库根目录再执行 `python -m uvicorn ...` |
| 2 | `No module named 'uvicorn'` / `'fastapi'` | 未激活虚拟环境或用错 Python | 激活 `.venv`，统一用 `python -m uvicorn` |
| 3 | 真实入口一直 503 `KNOWLEDGE_BASE_UNAVAILABLE` | `approved/` 没有审核通过且 `enabled` 的资料包 | 见第六节 |
| 4 | 真实入口返回鉴权/配置错误 | `QWEN_API_KEY` 未填或无效 | 在 `backend/.env` 填真实 Key，启动带 `--env-file backend/.env` |
| 5 | 改了 `.env` 不生效 | uvicorn 不自动读 `.env` | 启动命令必须加 `--env-file backend/.env` |
| 6 | PowerShell 禁止 `Activate.ps1` / `npm.ps1` | 执行策略限制 | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`，或用 `npm.cmd` |
| 7 | `curl.exe -d '{"query":"中文"}'` 返回 422 | PowerShell 5.1 改写引号并按 GBK 传参 | 把 JSON 存成 UTF-8 文件后 `--data-binary "@body.json"` |
| 8 | Vite 报端口占用 | `strictPort: true` | 结束占用 5173 的进程，或改端口并同步后端 CORS |
| 9 | 工作台显示「后端未连接」 | 后端未启动 | 先访问 8000 `/api/v1/health`，再在 `frontend/` 下 `npm run dev` |
| 10 | `npm ci` 提示 `esbuild postinstall` 未执行 | npm 11 的 allow-scripts 策略 | 警告不影响构建；异常时 `npm approve-scripts esbuild` 后重装 |
| 11 | 管理端提示后台接口不可用 | Beta 阶段管理端 API 尚未实现 | 属当前边界，见第七节 |
| 12 | 工作台问答只有 Mock 文案 | 用的 Mock 入口 | 换 `backend.app.alpha:app` 并配置审核语料 + Key |
| 13 | 杀毒软件报 `Trojan/Python.ShellLoader`（新环境首个 venv） | 命中 pip 自带 `pkg_resources` 的 `.pyc` 编译缓存，属误报 | 核对文件哈希与 Python 安装目录内 pip 源码一致即可；加白该目录或设 `PYTHONDONTWRITEBYTECODE=1` |

---

## 六、真实 Qwen 与四场景正向验收（当前阻塞）

必须**同时满足**以下两个条件，真实问答才能通过；缺任一条件都会以 503 失败：

1. **审核通过的正式资料包**：`knowledge_base/processed/alpha/approved/` 中至少有一份
   `human_approved=true` 且 `retrieval_status=enabled` 的 `DocumentPackage`
   （当前仅有 `README.md`；相邻 `pending-review/` 的 5 份为 `review_only`/`blocked`，按规则不得进入检索）；
2. **有效的 DashScope `QWEN_API_KEY`**（当前本机未配置）。

因此以下项目**未验证**：

- 真实 `POST /api/v1/ask` 返回 `answered` 且引用正确；
- S1–S4 四个场景的**真实政策问答**；
- 多轮追问在 `InMemoryConversationStore` 中的上下文效果（真实入口）。

解除条件的两步动作：把审核包放入 `approved/`，在 `backend/.env` 填 Key，重启真实入口后重跑本文 4.1–4.3 并补录证据。

---

## 七、未解决的环境问题清单

| # | 问题 | 影响 | 责任方 / 下一步 |
|---|---|---|---|
| 1 | 无正式审核资料包（`approved/` 为空） | 真实问答 503，四场景无法正向验证 | 王智洋：交付审核包；包到位后补测 |
| 2 | 无真实 `QWEN_API_KEY` | 无法验证真实模型调用 | 赵紫龙：确认 Key/模型；本地配置后补测 |
| 3 | 前端 API 地址写死相对路径 `/api/v1` | 仅能通过 Vite 代理访问后端，分离部署需改代码 | 吴欣键：评估 `VITE_API_BASE_URL`（需同步 CORS） |
| 4 | 学生端登录为前端演示门禁，无真实鉴权 | 可演示，但不能作为安全边界 | 按 Beta 约定保留，正式鉴权在后续里程碑 |
| 5 | 管理端业务 API 未实现 | 管理页降级提示 | 后端后续迭代 |
| 6 | 会话仅内存（重启丢失） | Beta 约定内，无法演示长会话恢复 | 保持约定，持久化在后续里程碑 |
| 7 | npm 11 `allow-scripts` 警告 | 不影响构建，新环境易困惑 | 已写入常见错误 #10 |
| 8 | 杀毒软件对新建 venv 中 pip 的 `.pyc` 误报 | 可能影响首次安装体验 | 已写入常见错误 #13 |

---

## 八、材料索引

| 材料 | 路径 |
|---|---|
| 版本记录 | [`evidence/versions.txt`](evidence/versions.txt) |
| 三入口 / 四场景 / 错误码记录 | [`evidence/runtime-http-check.txt`](evidence/runtime-http-check.txt) |
| 上游集成验证（25 项） | [`evidence/upstream-integration.txt`](evidence/upstream-integration.txt) |
| 测试日志（275 项，含跳过原因） | [`evidence/tests-clean-env.txt`](evidence/tests-clean-env.txt) |
| 前端构建日志 | [`evidence/frontend-ci-build.txt`](evidence/frontend-ci-build.txt) |
| 界面截图 | [`evidence/screenshots/student-login.png`](evidence/screenshots/student-login.png)、[`student-workspace.png`](evidence/screenshots/student-workspace.png)、[`admin.png`](evidence/screenshots/admin.png) |

---

## 九、变更记录

| 日期 | 变更 | 验证人 |
|---|---|---|
| 2026-11-23 | 初版：Windows 干净 clone 环境验证（Python 3.10.11 / Node 24.18.0），三入口、Mock 四场景、前端构建与代理、275 项测试 | 薛锦荣 |
| 2026-11-23 | 第二轮修正：同步 main @ `a789f53`；S4 问句改为「学院有哪些实验室？」；补充三入口与上游集成（25 项）证据；说明 28 项跳过构成；明确真实 Qwen 需两个条件同时满足；统一 pydantic 版本；日志去除本机用户目录 | 薛锦荣 |
