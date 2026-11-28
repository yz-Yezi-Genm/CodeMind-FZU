# 学生端 Beta 第二阶段联调记录

2026-11-28 在 Windows 上用 Microsoft Edge 复测本地 `7-htj` 学生端，对接 `origin/main@4713117` 后端快照。下表、四张场景截图和六条请求记录来自此次离线模型联调。

## 浏览器直连 FastAPI、AgentWorkflow 和 BM25

Edge 通过 Vite 代理发送实际 HTTP 请求。后端加载 #50 的 `tests/fixtures/beta_live_synthetic` 奖学金样例，只在模型调用处注入仓库已有的 `FirstEvidenceLLM`。浏览器未拦截接口，业务判断、检索、引用校验和会话存储均使用后端实现。

| 场景 | 页面结果与人工检查点 | 截图 |
| --- | --- | --- |
| S1 竞赛认定 | 询问竞赛能否认定创新学分，Agent 追问作品名称。补上作品名后仍返回追问，第二次问的是具体政策或办理事项。请求沿用同一会话，尚不能据此确认竞赛认定结论。 | [竞赛追问](s1-offline.png) |
| S2 奖学金 | 问「2026年优秀学生综合奖学金申请需要提交什么材料？」后页面显示已回答。展开引用可核对摘录和定位，测试域名隐藏跳转。继续问「2026年优秀学生综合奖学金金额是多少？」后，页面显示证据不足，引用数为 0。 | [材料回答与展开的引用](s2-offline.png) |
| S3 推免条件 | 新建对话后发送首页示例，后端返回证据不足，页面展示原因，引用数为 0。 | [推免查询](s3-offline.png) |
| S4 学院资源 | 新建对话后发送首页实验室示例，这份合成库没有可用于该问题的资源名录，后端返回证据不足，引用数为 0。 | [资源查询](s4-offline.png) |

[六次请求的查询、会话编号和结果](workflow-requests.json)。各请求 HTTP 状态均为 200，浏览器逐次比对了请求体的会话编号和响应头 `X-Request-ID`。S2 两轮的响应会话编号相同，新建会话的首轮均传 `null`。

## 正式资料目录为空时的页面行为

11 月 27 日在 `bd23bfa` 上，第二个独立实例使用生产入口 `backend.app.alpha:app`，指向该快照的正式 `approved` 目录。健康检查通过，启动日志记录 `Approved corpus rejected loaded=0 skipped=0`。浏览器提问得到 HTTP 503、`KNOWLEDGE_BASE_UNAVAILABLE`，请求编号为 `88f643e5-6af0-4ba0-bce4-a01182ffee22`。页面显示「资料服务暂时不可用，请稍后重试」，保留原问题和可用的发送按钮。[正式资料未就绪截图](formal-corpus-503.png)

## 历史提示和页面回归

Playwright 契约样例模拟了历史回答正文和 `HISTORICAL_POLICY` 重复提示「对应学年报名已截止。」的情况。正文保留该句，警告区继续显示独立信息「当前联系方式尚未核实。」。保留回答模式、分段和来源定位。[历史回答展示样例](history-fixture.png)

接口单测 9 项通过，TypeScript 检查与 Vite 构建通过。既有 Edge 回归覆盖四类快捷入口、三种状态、引用、错误恢复、刷新和新会话。历史页面截图来自拦截响应的回归，四领域截图来自直连离线服务的另一组测试。

## 真实 Qwen 单题验证

11 月 27 日在 `bd23bfa` 的 FastAPI 测试实例中，使用同一份合成奖学金资料和真实 `qwen-flash`。向 `POST /api/v1/ask` 首轮提交「2026年优秀学生综合奖学金申请需要提交什么材料？」。模型 HTTP 200，问答 HTTP 200，业务状态为 `answered`，返回 1 条引用。回答为「根据已核验资料，2026年优秀学生综合奖学金申请需提交申请表和成绩单。」此次自动记录覆盖后端单题调用；上表的浏览器六次请求使用离线模型。

## 提交前回归

11 月 28 日执行 `npm.cmd run test:student --prefix frontend`，9 项通过；执行 `npm.cmd run build --prefix frontend`，TypeScript 和 Vite 构建通过。Edge 执行 `frontend/tests/student-browser.js`，验证了三种业务状态、多轮、接口异常恢复及刷新。1280 × 720 和 390 × 720 两种窗口下，长对话均在消息区内滚动，上划时输入框保持在原位，页面底部未出现额外滚动区域。

## 本地复现

在仓库根目录执行以下 PowerShell 命令，可在不切换分支的情况下取得本次测试的后端文件。

```powershell
$repo = (Get-Location).Path
$stage = Join-Path $env:TEMP ("codemind-stage2-" + [guid]::NewGuid())
New-Item -ItemType Directory $stage | Out-Null
git archive -o "$stage/backend.zip" 4713117 -- backend tests/fixtures/beta_live_synthetic knowledge_base/processed/alpha/approved scripts
Expand-Archive "$stage/backend.zip" "$stage/source"
Copy-Item frontend/tests/stage2_offline_app.py "$stage/source/"
Set-Location "$stage/source"
& "$repo/.venv/Scripts/python.exe" -m uvicorn stage2_offline_app:app --host 127.0.0.1 --port 8013
```

另开终端，进入仓库的 `frontend` 目录，为本次测试启动独立代理。

```powershell
node --input-type=module -e "import {createServer} from 'vite'; const s=await createServer({server:{host:'127.0.0.1',port:5183,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8013'}}}}); await s.listen(); s.printUrls()"
```

打开 `http://127.0.0.1:5183/?preview=1`，使用演示账号 `demo` 和密码 `123456` 手工检查。也可从另一个终端在仓库根目录运行下列命令；截图写入执行目录。

```powershell
npx.cmd --yes --package @playwright/cli playwright-cli -s=stage2 open "http://127.0.0.1:5183/?preview=1" --browser=msedge
npx.cmd --yes --package @playwright/cli playwright-cli -s=stage2 run-code --filename=frontend/tests/student-stage2-offline.js
npx.cmd --yes --package @playwright/cli playwright-cli -s=stage2 close
```

正式目录的失败路径可在以上后端快照目录用 `backend.app.alpha:app` 替代测试入口，采用默认正式资料路径复验。正式资料放行后的四领域正向回答，以及 S4 历史名录的真实引用仍待验证。
