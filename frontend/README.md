# CodeMind-FZU Frontend

> **Beta 阶段说明（2026-11-23）**：本机运行方式不变（`npm ci` → `npm run dev`），验收不要求云服务器与域名。
> Windows 干净环境验证、构建记录与常见错误见
> [`docs/assignment-03/beta/windows-runtime-test.md`](../docs/assignment-03/beta/windows-runtime-test.md)。

CodeMind-FZU 前端工程骨架：**Vite + 原生 TypeScript 多页面应用（HTML + CSS + TypeScript）**，不引入 React、Vue 等大型框架。

学生端首页提供四类校园问答入口，并通过公共 API 完成问答、追问和来源查看。两端共用请求封装与类型定义。

## 环境要求

| 项目 | 要求 | 验证环境 |
|---|---|---|
| Node.js | **18.18 及以上**（推荐 20 LTS / 22 LTS） | Node 24.18.0 |
| npm | 随 Node 安装（推荐 9+） | npm 11.x |
| 后端 | 按 `backend/README.md` 启动；真实入口 `backend.app.alpha:app`，Mock 联调 `backend.app.dev:app`，均监听 `http://127.0.0.1:8000` | — |

## 安装依赖

```bash
cd frontend
npm install
```

首次安装会生成/使用 `package-lock.json`，请**提交该文件**以保证团队成员版本一致；不要提交 `node_modules/`。

## 启动开发服务器

```bash
npm run dev
```

固定监听 **5173** 端口（`strictPort: true`，端口被占用会直接报错而不是自动换端口）。

| 页面 | 地址 |
|---|---|
| 学生端 | <http://127.0.0.1:5173/> |
| 后台管理端 | <http://127.0.0.1:5173/admin/index.html> |

## API 代理

开发服务器已配置 `/api` 代理到 `http://127.0.0.1:8000`：

```text
浏览器 /api/v1/health  →  Vite dev server  →  http://127.0.0.1:8000/api/v1/health
```

因此前端代码统一使用相对路径 `/api/v1/...`，不要写死后端地址，也不需要在前端处理跨域。后端 CORS 已覆盖 `http://localhost:5173` 与 `http://127.0.0.1:5173`。

### 后端入口说明

- **真实 Alpha 入口**：`python -m uvicorn backend.app.alpha:app --reload --port 8000 --env-file backend/.env`。需要本地 `QWEN_API_KEY` 与已审核资料（`ALPHA_PACKAGE_DIR`）；缺配置时服务可启动，但问答返回 503，不会伪造回答。
- **Mock 联调入口**：`python -m uvicorn backend.app.dev:app --reload --port 8000`，不需要密钥。
- 前端无需区分两种入口，统一走 `/api/v1` 契约。
- 后台管理端调用 `/api/v1/admin/...` 时，当前后端返回 404，管理页会显示“后台管理接口当前不可用”，属 Alpha 当前边界。

## 生产构建

```bash
npm run build
```

构建前会先执行 `tsc --noEmit` 做严格类型检查，然后由 Vite 输出到 `dist/`，包含：

- `dist/index.html`（学生端）
- `dist/admin/index.html`（后台管理端）

本地预览构建产物：

```bash
npm run preview
```

默认地址 <http://127.0.0.1:4173/>。

## 目录结构

```text
frontend/
├── index.html              # 学生端入口
├── admin/index.html        # 后台管理端入口
├── src/
│   ├── student/           # 学生端问答交互、页面样式与图标
│   ├── admin/main.ts       # 管理端脚本
│   └── shared/
│       ├── api.ts          # /api/v1 请求封装（health / ask）
│       ├── types.ts        # 与后端契约对齐的类型
│       ├── dom.ts          # DOM 小工具
│       └── styles.css      # 公共样式
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

## 约定

- 公共类型以 `docs/assignment-03/interface-contract-v1.md` 与 `backend/contracts/models.py` 为准，不要在前端复制或私改字段与状态值。
- 两个页面共用 `src/shared/api.ts`，新增接口请先确认后端契约，再在 `api.ts` 中集中封装。
- 学生端的启动方式、问答验收场景与截图见[学生端联调记录](../docs/assignment-03/student-integration/README.md)。

## 常见问题

**`npm` 在 PowerShell 中提示“禁止运行脚本”**

Windows PowerShell 默认执行策略会拦截 `npm.ps1`，可任选一种：

```powershell
# 仅当前窗口放开
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
npm install

# 或直接使用 npm.cmd
npm.cmd install
```

**5173 端口被占用**

`strictPort` 开启时会直接报错。结束占用进程，或临时修改 `vite.config.ts` 的 `server.port`；若改端口，请同步后端 `CORS_ALLOW_ORIGINS`。

**页面显示“后端未连接”**

先确认后端已启动：<http://127.0.0.1:8000/api/v1/health>，并检查是否在 `frontend/` 目录下执行 `npm run dev`（代理配置只在该目录生效）。

**依赖安装慢**

可临时使用国内镜像：

```bash
npm install --registry=https://registry.npmmirror.com
```
