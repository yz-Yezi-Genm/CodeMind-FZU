# Beta 第一阶段学生端验证记录

验证时间为 2026-11-25 19:18（北京时间）。测试基于契约修复提交 `1b07869`，环境为 Windows、Microsoft Edge、Node.js 24.15.0 和 Python 3.13.3。

## 前端接口模拟回归

按前端 README 运行 `frontend/tests/student-browser.js`。脚本使用 Playwright 的 `page.route()` 为 `/api/v1/health` 和 `/api/v1/ask` 提供测试响应。结果为「学生端浏览器回归通过（三种状态、四场景入口、多轮、引用、错误恢复、刷新与新建会话）」。

[历史引用截图](historical-citation.png)截取自当前浏览器回归的历史回答场景。两条引用的 `source_url` 分别是 `https://www.fzu.edu.cn/` 和 `https://example.invalid/policy`。前者展示原始来源入口，后者是联调测试占位地址，页面展示资料和定位并隐藏跳转入口。这两条引用均为测试样例。脚本另有一项失败用例，覆盖 `source_url: null` 时的格式错误提示和输入保留。

## Edge 直连本地 FastAPI Mock

在仓库根目录启动 FastAPI Mock。在另一终端启动 Vite。

```powershell
& ./.venv/Scripts/python.exe -m uvicorn backend.app.dev:app --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd run dev --prefix frontend -- --strictPort
```

本次复测复用了按上述方式启动的 FastAPI 进程。启动日志如下。

```text
INFO:     Started server process [32264]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

打开 Edge 的新会话，访问 `http://127.0.0.1:5173/?preview=1`，登录前在开发者工具的「网络」面板开始记录。进入工作台后，先用按钮发送「申请校级奖学金需要什么条件？」，再用 Enter 发送「我想继续咨询申请材料。」。本次独立浏览器会话的请求经 Vite 代理到 FastAPI，未注册 Playwright 路由拦截。

| 浏览器请求 | 响应时间（UTC） | HTTP | 请求会话 ID | 响应 |
| --- | --- | --- | --- | --- |
| `GET /api/v1/health` | `11:18:04.966597Z` | 200 | — | `status: ok` |
| 首轮 `POST /api/v1/ask` | `11:18:05.248861Z` | 200 | `null` | `answered`、`current_policy`、`MOCK_AGENT`，返回会话 A |
| 次轮 `POST /api/v1/ask` | `11:18:05.300685Z` | 200 | 会话 A | `answered`、`current_policy`、`MOCK_AGENT`，返回同一个会话 A |

会话 A 为 `5930f362-6d50-4621-9ee8-4fadd2b40b98`。两次问答的 `request_id` 分别为 `79369489-9875-46cb-bae8-a57e9eed7bf4` 和 `23fc9c26-9919-4cb3-972c-610a6160a80b`。

同次验证的 Uvicorn 访问日志如下。

```text
INFO:     127.0.0.1:1725 - "GET /api/v1/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:1727 - "POST /api/v1/ask HTTP/1.1" 200 OK
INFO:     127.0.0.1:1728 - "POST /api/v1/ask HTTP/1.1" 200 OK
```

[本地 Mock 多轮问答截图](alpha-mock-multi-turn.png)展示两轮回复的「模拟回答」标记。前端隐藏了模拟回复的政策依据标签。真实 Qwen 和审核资料联调属于第二阶段。
