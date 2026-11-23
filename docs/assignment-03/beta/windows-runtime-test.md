# Beta 阶段 Windows 本机运行与干净环境验证记录

> 适用对象：未参与开发的验收人员、新加入的开发成员
> 适用阶段：Beta（本机运行、单进程、InMemoryConversationStore，不依赖数据库与云服务器）
> 维护人：薛锦荣（Windows 本机运行与工程交付）
> 代码基线：`origin/main` @ `90df0f9`（本地分支 `docs/beta-windows-runtime`）
> 验证时间：2026-11-23
> 验证结论：**后端、前端、前后端联调在本机全部跑通**；真实 Qwen 正向问答因缺少「人工审核通过的正式资料包 + 真实 API Key」**尚未验证**，见第六节。

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

> 结论：**验收演示可以先走 Mock 入口**（无需任何密钥/资料），真实问答需要赵紫龙/王智洋提供审核语料与你本地的 `QWEN_API_KEY`。

---

## 二、环境要求与本机实测版本

| 项目 | 要求 | 本次实测 |
|---|---|---|
| 操作系统 | Windows 10/11（macOS、Linux 同理） | Windows 11 家庭中文版 10.0.26200 64 位 |
| Python | **3.10 及以上**（推荐 3.10/3.11） | Python 3.10.11（`py -3.10`） |
| 后端依赖 | `backend/requirements.txt` | fastapi 0.162.5、pydantic 2.14.4、uvicorn 0.54.0、httpx 0.28.1 |
| 验证依赖（跑测试） | `scripts/requirements-alpha-verification.txt` | pytest 9.2.0 |
| Node.js | **≥ 18.18**（推荐 20/22 LTS） | Node v24.18.0 |
| npm | 随 Node 安装 | npm 11.16.0 |
| 浏览器 | Chrome / Edge | Microsoft Edge |
| 网络 | 首次安装依赖需要（可用国内镜像） | 清华 PyPI / npmmirror |

版本明细见 [`evidence/versions.txt`](evidence/versions.txt)。

---

## 三、干净环境验证步骤（可直接照做）

以下命令**除特别注明外均在仓库根目录执行**。

### 3.1 获取代码

```powershell
git clone https://github.com/yz-Yezi-Genm/CodeMind-FZU.git
cd CodeMind-FZU
git switch docs/beta-windows-runtime   # Beta 文档分支；合并后改为 main
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
- 变量名称与代码一致（`QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`、`QWEN_TIMEOUT_SECONDS`、`QWEN_MAX_RETRIES`、`ALPHA_PACKAGE_DIR`、`CONVERSATION_*`、`CORS_ALLOW_ORIGINS`），已逐项与 `backend/app/config.py`、`backend/services/qwen_client.py` 核对。

### 3.4 后端：启动

**真实入口（需要密钥 + 审核语料）**

```powershell
python -m uvicorn backend.app.alpha:app --reload --port 8000 --env-file backend/.env
```

**Mock 入口（联调/演示，无需密钥）**

```powershell
python -m uvicorn backend.app.dev:app --reload --port 8000
```

> `--env-file` 是 uvicorn 的参数，**没有它不会自动读取 `backend/.env`**。这是本阶段最容易踩的坑之一。

### 3.5 后端：健康检查

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

期望：`{"status":"ok","service":"codemind-fzu-api","version":"0.1.0",...}`，HTTP 200。

Swagger 文档：<http://127.0.0.1:8000/docs>

### 3.6 前端：安装与启动

```powershell
cd frontend
npm ci                     # 按 package-lock.json 复现安装
npm run dev
```

| 页面 | 地址 |
|---|---|
| 学生端 | <http://127.0.0.1:5173/> |
| 后台管理端 | <http://127.0.0.1:5173/admin/index.html> |

学生端右上角显示「**后端已连接**」即联调成功（见 [`evidence/screenshots/student.png`](evidence/screenshots/student.png)）。

### 3.7 前端：构建

```powershell
npm run build      # tsc --noEmit && vite build
npm run preview    # 本地预览 dist，http://127.0.0.1:4173/
```

### 3.8 关闭服务

前后端终端均按 `Ctrl + C` 即可；`--reload` 模式会提示 `Shutting down`。
若端口被残留进程占用：

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

---

## 四、验证结果

### 4.1 后端接口（干净 clone，`backend.app.alpha:app` 与 `backend.app.dev:app`）

| 检查项 | 结果 |
|---|---|
| `GET /api/v1/health`（Mock） | 200，`status=ok` |
| `GET /api/v1/health`（真实入口，无语料） | 200，`status=ok`（服务可启动） |
| `POST /api/v1/ask`（Mock，四个业务场景） | 200，`status=answered`，带 `MOCK_AGENT` 警告 |
| `POST /api/v1/ask`（Mock，`__mock_clarify__`） | 200，`status=needs_clarification` |
| `POST /api/v1/ask`（Mock，`__mock_insufficient__`） | 200，`status=insufficient_evidence` |
| `POST /api/v1/ask`（空 query / 非法 `conversation_id`） | 422，`INVALID_REQUEST` |
| `GET /api/v1/not-exist` | 404，`RESOURCE_NOT_FOUND` |
| `POST /api/v1/ask`（真实入口，缺审核语料） | 503，`KNOWLEDGE_BASE_UNAVAILABLE`，`retryable=true` |
| 启动日志（真实入口无语料） | `Approved corpus rejected loaded=0 skipped=0` → `Alpha runtime startup unavailable code=KNOWLEDGE_BASE_UNAVAILABLE`，服务仍可启动 |

完整请求/响应见 [`evidence/runtime-http-check.txt`](evidence/runtime-http-check.txt)。

### 4.2 四大业务场景（Mock 入口）

以学生端四类入口对应的问句各发一次，均返回 200 `answered`（Mock 固定文案，明确声明非真实政策结论）：

| 场景 | 问句示例 | 结果 |
|---|---|---|
| 奖助学金 | 国家奖学金申请需要哪些条件？ | 200 `answered` |
| 竞赛认定 | 学科竞赛项目级别怎么认定？ | 200 `answered` |
| 推免/升学 | 推免资格需要满足什么条件？ | 200 `answered` |
| 学院资源 | 计算机学院院级奖学金怎么评定？ | 200 `answered` |

> Mock 只验证「链路通」，不代表政策结论正确；真实结论必须由审核语料 + Qwen 生成并附引用。

### 4.3 前端与联调

| 检查项 | 结果 |
|---|---|
| 干净 clone `npm ci` | 成功（12 个包，约 2s） |
| `npm run build`（含 `tsc --noEmit`） | 成功，dist 产物完整（学生端 + 管理端） |
| `npm run dev` 学生端 / 管理端 | 均 HTTP 200 |
| Vite 代理 `/api/v1/health` | 200，与后端一致 |
| Vite 代理 `/api/v1/ask`（UTF-8 请求体） | 200 `answered` |
| 学生端首屏 | 显示「后端已连接」 |

构建日志见 [`evidence/frontend-ci-build.txt`](evidence/frontend-ci-build.txt)。

### 4.4 测试套件（干净 clone）

```powershell
python -m unittest discover -s tests -v
```

**结果：275 项执行，通过 247、跳过 28、失败 0、错误 0。**

- 跳过项为 Windows 符号链接权限、真实 Qwen 验收开关、业务规则替身等环境相关项，不是失败；
- 完整日志见 [`evidence/tests-clean-env.txt`](evidence/tests-clean-env.txt)。

### 4.5 关闭与重启

- `Ctrl + C` 停止 uvicorn 与 Vite，均正常退出，端口释放；
- 重启后 `/api/v1/health` 仍为 200；内存会话按约定清空（会话不持久化）。

---

## 五、常见错误及解决方法

| # | 现象 | 原因 | 解决 |
|---|---|---|---|
| 1 | `ModuleNotFoundError: No module named 'backend'` | 不在仓库根目录 | `cd` 到仓库根目录再执行 `python -m uvicorn ...` |
| 2 | `No module named 'uvicorn'` / `No module named 'fastapi'` | 没激活虚拟环境，或用了系统 Python | 先激活 `.venv`，并统一用 `python -m uvicorn` |
| 3 | 真实入口一直 503 `KNOWLEDGE_BASE_UNAVAILABLE` | `approved/` 没有审核通过且 `enabled` 的资料包 | 见第六节；确认语料由王智洋交付并放入 `approved/` |
| 4 | 真实入口返回 401/配置错误 | `QWEN_API_KEY` 未填或无效 | 在 `backend/.env` 填真实 Key，且启动命令带 `--env-file backend/.env` |
| 5 | `.env` 改了不生效 | uvicorn 不会自动读取 `.env` | 启动命令必须加 `--env-file backend/.env` |
| 6 | PowerShell 禁止 `Activate.ps1` / `npm.ps1` | 执行策略限制 | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`，或直接用 `npm.cmd` |
| 7 | 用 `curl.exe -d '{"query":"中文"}'` 得到 422 | PowerShell 5.1 会改写引号并把中文按 GBK 传给 curl | 把 JSON 写进 UTF-8 文件后 `--data-binary "@body.json"`（本次验证即用此法） |
| 8 | Vite 启动报端口占用 | `strictPort: true` | 结束占用 5173 的进程，或改 `vite.config.ts` 端口并同步后端 CORS |
| 9 | 页面显示「后端未连接」 | 后端没起，或不在 `frontend/` 目录启动 | 先访问 8000 `/api/v1/health`，再在 `frontend/` 下 `npm run dev` |
| 10 | `npm ci` 提示 `esbuild postinstall` 未执行 | npm 11 的 allow-scripts 策略 | 警告不影响构建；如遇异常执行 `npm approve-scripts esbuild` 后重装 |
| 11 | 管理端提示后台接口不可用 | Beta 阶段管理端 API 尚未实现 | 属当前边界，见第七节 |
| 12 | 学生端提问无引用、只有 Mock 文案 | 用的是 Mock 入口 | 换 `backend.app.alpha:app` 并配置审核语料 + Key |

---

## 六、真实 Qwen 与四场景正向验收（当前阻塞）

现状：

1. `knowledge_base/processed/alpha/approved/` 只有 `README.md`，**没有正式审核通过的资料包**；
   相邻 `pending-review/` 的 5 份为 `review_only`/`blocked`（`human_approved=false`），按规则不得进入检索；
2. 本机没有可用的 DashScope `QWEN_API_KEY`。

因此下列项目**未验证**，已在第七节列为待办：

- 真实 `POST /api/v1/ask` 返回 `answered` 且引用正确；
- 四个业务场景的**真实政策问答**（奖学金、竞赛认定、推免、学院资源）；
- 多轮追问在 `InMemoryConversationStore` 中的上下文效果（真实入口）。

恢复条件（满足其一即可推进）：

- 王智洋/审核者交付审核通过、`retrieval_status=enabled`、`human_approved=true` 的资料包；
- 赵紫龙确认 Qwen Key 与模型名（默认 `qwen-flash`）可用。

验收动作：把审核包放入 `knowledge_base/processed/alpha/approved/`，在 `backend/.env` 填 Key，重启真实入口后执行本文 4.1、4.2 的检查项并补录证据。

---

## 七、未解决的环境问题清单

| # | 问题 | 影响 | 责任方 / 下一步 |
|---|---|---|---|
| 1 | 无正式审核资料包（`approved/` 为空） | 真实问答 503，四场景无法正向验证 | 王智洋：交付审核包；本人在包到位后补测 |
| 2 | 无真实 `QWEN_API_KEY` | 无法验证真实模型调用 | 赵紫龙：确认 Key/模型；本人本地配置后补测 |
| 3 | 前端 API 地址写死相对路径 `/api/v1`（无环境变量） | 只能通过 Vite 代理访问后端；将来分离部署需改代码 | 吴欣键：评估增加 `VITE_API_BASE_URL`（需同步 CORS） |
| 4 | 管理端业务 API 未实现 | 管理页降级提示 | 后端后续迭代 |
| 5 | 会话仅内存（重启丢失） | Beta 约定内，但无法演示长会话恢复 | 按 Beta 约定保留，持久化在后续里程碑 |
| 6 | npm 11 `allow-scripts` 警告 | 不影响构建，但新环境可能困惑 | 已写入常见错误 #10 |

---

## 八、材料索引

| 材料 | 路径 |
|---|---|
| 版本记录 | [`evidence/versions.txt`](evidence/versions.txt) |
| 接口检查记录 | [`evidence/runtime-http-check.txt`](evidence/runtime-http-check.txt) |
| 测试日志（275 项） | [`evidence/tests-clean-env.txt`](evidence/tests-clean-env.txt) |
| 前端构建日志 | [`evidence/frontend-ci-build.txt`](evidence/frontend-ci-build.txt) |
| 界面截图 | [`evidence/screenshots/student.png`](evidence/screenshots/student.png)、[`admin.png`](evidence/screenshots/admin.png) |

---

## 九、变更记录

| 日期 | 变更 | 验证人 |
|---|---|---|
| 2026-11-23 | 初版：Windows 干净 clone 环境验证（Python 3.10.11 / Node 24.18.0），后端三入口、四场景 Mock 联调、前端构建与代理、275 项测试、错误码清单与待办 | 薛锦荣 |
