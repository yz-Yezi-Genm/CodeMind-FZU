# 后台管理端（Alpha 冲刺）· 运行说明与实测记录

负责人：林彦翔
时间：2026 年 11 月 17 日（Windows 11 + Edge 1600×1000）
范围：管理概览、知识库资料列表、分页与状态筛选、资料详情、元数据编辑、导入入口、重建索引入口、加载/成功/失败/空数据状态。
接口基线：[`docs/assignment-03/interface-contract-v1.md`](../interface-contract-v1.md)（V1.0）

> **模拟数据声明**：本页 44 条资料是前端内置演示数据，**不是数据库读取结果，也不是真实核验结论**。后台管理 API 在本仓库尚未实现（见[证据](evidence/backend-admin-routes.txt)），页面会先请求真实接口、失败后降级到模拟数据并常驻提示。

---

## 一、启动

后台管理端与之前的学生端在**同一个 Vite 工程**里，不需要另装依赖、也不需要新建项目。

```powershell
cd frontend
npm ci          # 或 npm install
npm run dev
```

| 页面 | 地址 |
| --- | --- |
| 学生端 | <http://127.0.0.1:5173/> |
| **后台管理端** | <http://127.0.0.1:5173/admin/index.html> |

`/api` 已由 Vite 代理到 `http://127.0.0.1:8000`。后端起不起来也能进后台页：页面会显示「后台管理接口当前不可用（HTTP 500/404）」，并按模拟数据工作。

本机用 Anaconda 跑后端的实测命令（Python 3.14.6 + fastapi 0.163.2）：

```powershell
D:\anaconda\python.exe -m pip install -r backend/requirements.txt
D:\anaconda\python.exe -m uvicorn backend.app.dev:app --host 127.0.0.1 --port 8000
```

此时 `GET /api/v1/health` 返回 `ok`；`GET /api/v1/admin/documents` 由 FastAPI 返回统一错误 `RESOURCE_NOT_FOUND`（路由未注册），页面据此降级到模拟数据，见[证据](evidence/backend-404.txt)。

构建与类型检查：

```powershell
cd frontend
npm run typecheck
npm run build     # 产出 dist/index.html 与 dist/admin/index.html
```

> 本机沙箱限制说明：`npm ci` 需要 `--ignore-scripts`（esbuild 的 postinstall 子进程被沙箱拦截），`npm run build` 与无头截图需放宽沙箱权限。这是本机环境限制，团队同学的正常环境不需要这样处理。

## 二、页面与功能

| 任务要求 | 实现位置 | 说明 |
| --- | --- | --- |
| 后台管理首页 | `?view=dashboard` | 4 张统计卡（总数 44 / 来源待核验 28 / 已开放检索 3 / 正文提取异常 1）、4 条待办（点击跳列表并自动套用筛选）、四个维度的状态分布 |
| 知识库资料列表 | `?view=documents` | 9 列表格：资料名称、资料类别、发布单位或来源、来源核验、时效核验、正文提取、检索开放、更新、操作 |
| 资料分页 | 列表底部 | 按契约 `page` / `page_size` 语义，默认 20 条/页，共 3 页；页码越界自动钳制 |
| 状态筛选 | 列表工具栏 | 类别 + 4 个状态下拉，另有关键词搜索（名称/编号/发布单位/文号）与「清空筛选」 |
| 资料详情 | 行内「详情」 | 详情弹窗：四个状态（文字 + 契约原值）+ 编号/类别/类型/发布单位/文号/版本/日期/适用范围/登记政策状态/来源链接/核查说明 |
| 资料元数据编辑 | 行内「编辑」 | 可改名称、类别、发布单位、文号、资料类型、发布日期；**四个状态字段不提供直接修改**，避免绕过「开放检索」的前置条件 |
| 资料上传入口 | 工具栏「导入资料」 | 文件 + 元数据表单，校验文件必选、名称必填 |
| 重建索引入口 | 行内「重建索引」/ 详情弹窗 | 确认弹窗写明「重建索引不会自动开放检索」；`needs_ocr` 资料额外提示没有可用正文 |
| 加载 / 成功 / 失败 / 空数据 | 全页 | 加载时先渲染骨架视图；成功与失败用 Toast（`aria-live`）；空结果走空态并给「清空筛选」；接口不可用时用黄色横幅常驻说明 |

侧栏其余入口（资料审核、数据来源、运行与反馈、角色与权限、操作审计）按原型保留，但标注「后续迭代」，不可点击。

## 三、接口现状与降级策略

契约第 10 节定义了 5 个后台管理接口，本仓库**都还没有实现**（`backend/app/` 下没有任何 admin 路由）。前端已在 `frontend/src/shared/api.ts` 中按契约路径集中封装，并带有与 `ask` 一致的响应校验：

| 接口 | 前端函数 | 当前行为 |
| --- | --- | --- |
| `GET /api/v1/admin/documents` | `listAdminDocuments` | 启动时请求一次；失败即降级到模拟数据 |
| `GET /api/v1/admin/documents/{id}` | `getAdminDocument` | 详情优先用列表已有字段，不额外阻塞页面 |
| `POST /api/v1/admin/documents` | `uploadAdminDocument` | 真实提交 multipart；失败时如实报错；模拟数据模式下才在内存新增一条并标注「演示新增」 |
| `PATCH /api/v1/admin/documents/{id}` | `updateAdminDocumentMetadata` | 真实提交白名单字段；失败时如实报错；模拟数据模式下改动只留在内存 |
| `POST /api/v1/admin/documents/{id}/reindex` | `reindexAdminDocument` | 真实提交；**失败时绝不伪造 `chunk_count` / `indexed_count`** |

三条硬规则：

1. **不伪造成功**：任何写操作先发真实请求，失败就显示真实错误码与状态码。
2. **模拟模式可识别**：顶部「数据来源：前端模拟数据」徽标 + 黄色横幅 + 每次演示写入的 Toast 都写明「未写入数据库」。
3. **不放开检索**：编辑表单不提供状态字段，检索开放仍由核验流程决定。

## 四、实测记录

截图环境：`npm run build` 产物，由只读静态服务器托管，`/api/*` 返回 404，用来复现「管理接口未实现」时页面的真实降级行为。**注意：这批截图里的 404 来自该静态服务器，不是 FastAPI 后端。**

| 场景 | 操作 | 结果 | 截图 |
| --- | --- | --- | --- |
| 管理概览 | 打开 `/admin/index.html` | 统计卡 44 / 28 / 3 / 1，待办 4 条，状态分布覆盖四个维度全部枚举值 | [01](screenshots/01-dashboard.png) |
| 资料列表 | 切换到「资料管理」 | 9 列表格，44 条资料按 20 条/页分页，行内「详情 / 编辑 / 重建索引」 | [02](screenshots/02-documents.png) |
| 状态筛选 | 检索开放 = 已开放检索 | 命中 3 条，计数条同时显示关键词与筛选条件 | [03](screenshots/03-filter-enabled.png) |
| 资料详情 | 行内「详情」 | 弹窗展示四个状态（中文 + 契约原值）及全部元数据、来源链接 | [04](screenshots/04-detail.png) |
| 编辑元数据 | 行内「编辑」 | 表单含名称/类别/发布单位/文号/类型/发布日期；状态字段区给出不可直接修改的说明 | [05](screenshots/05-edit.png) |
| 导入资料 | 工具栏「导入资料」 | 文件 + 元数据表单，页面注明 `POST` 未实现、不会伪造上传成功 | [06](screenshots/06-upload.png) |
| 重建索引 | `needs_ocr` 资料的「重建索引」 | 弹窗显示当前正文「需 OCR」并提示重建也不会有可用正文 | [07](screenshots/07-reindex.png) |
| 空数据态 | 来源核验 = 核验失败 | 「共命中 0 条｜来源核验 核验失败｜数据集共 44 条」+ 空态说明 + 清空筛选 | [08](screenshots/08-empty.png) |
| 分页 | 第 2 页 | 第 2 / 3 页，上一页可点、下一页可点 | [09](screenshots/09-page2.png) |
| 交互后多条件筛选 | 真实点击下拉：检索开放 = 已开放检索，再叠加类别 = 综评与奖学金（CDP 驱动） | 由 3 条收敛到 2 条，计数条同时显示两个条件 | [10](screenshots/10-filter-combined.png) |
| 搜索无结果 | 输入「区块链」 | 进入空数据态 | [11](screenshots/11-search-empty.png) |
| 编辑保存 | 改名后提交 | `PATCH` 返回 404 后进入演示模式：行内标题更新、时间刷新，Toast 写明「只在当前页面内存，未写入数据库」 | [12](screenshots/12-edit-saved-demo.png) |
| 上传校验 | 不选文件直接提交 | 阻止提交并提示「请选择要导入的原始文件。」 | [13](screenshots/13-upload-validation.png) |
| 重建索引失败 | 确认重建 | 显示真实错误「HTTP 404：请求失败」，并说明不会伪造索引结果 | [14](screenshots/14-reindex-error.png) |
| **真后端下的降级** | 启动 `backend.app.dev:app`（8000）后打开资料列表 | 后端真实返回统一错误 `RESOURCE_NOT_FOUND`，页面据此降级为模拟数据并显示 44 条中的第 1 页 20 条；徽标仍标「前端模拟数据」 | [15](screenshots/15-real-backend.png)、[证据](evidence/backend-404.txt) |

## 五、测试记录

### 1. 纯逻辑单元测试（`node:test`，零依赖）

```powershell
cd frontend
node tests/admin-filters.test.ts
```

12 个用例，覆盖分页边界、搜索、状态筛选、契约外取值、空结果、状态映射与模拟数据合规性。原始输出见 [`evidence/tests.txt`](evidence/tests.txt)。

| 类型 | 用例 |
| --- | --- |
| 正常 | 44 条按 20 条/页切分成 3 页，末页 4 条 |
| 正常 | 检索开放 = `enabled` 命中 3 条，且每条都满足「来源 verified + 正文 extracted + 时效 ∈ 四值」 |
| 正常 | 关键词命中名称/发布单位/文号，大小写与首尾空格不敏感 |
| 正常 | 各状态计数之和等于 44，类别覆盖七类 |
| 异常 | 页码 99 / 0 / -5 / NaN 被钳制；每页 0 回落 20、5000 截到 100 |
| 异常 | 契约内但数据里没有的状态（`failed`）与搜不到的关键词返回 0 条 → 页面走空态 |
| 异常 | 契约外取值 `archived` 不匹配任何记录，标签显示「契约外取值」并按危险语气 |
| 异常 | 非法模拟数据（`extraction_status='done'`）在装载阶段抛错，不静默显示 |

### 2. 端到端交互验证（Edge headless + CDP 真实点击）

```powershell
# 构建产物 + 静态服务器（/api/* 返回 404）后执行
node <脚本> http://127.0.0.1:4180/admin/index.html <截图目录> <证据文件>
```

9 项全部通过：列表 20 条与分页、状态筛选命中 3 条、叠加类别筛选收敛到 2 条、搜索空态、详情弹窗四个状态、编辑保存走演示模式、上传缺文件校验、重建索引失败不伪造结果、Esc 关闭弹窗。原始输出见 [`evidence/interaction-tests.txt`](evidence/interaction-tests.txt)。

### 3. 类型检查与构建

见 [`evidence/typecheck.txt`](evidence/typecheck.txt) 与 [`evidence/build.txt`](evidence/build.txt)：`tsc --noEmit` 无错误；构建产出 `dist/admin/index.html`、`dist/assets/admin-*.js`（约 73 KB）与 `admin-*.css`（约 12 KB），学生端入口同时正常产出。

## 六、已知边界

1. **认证授权未实现**：按契约要求，后台管理端只用于本地开发与受控测试，**不部署到公网**；前端隐藏按钮不构成权限控制。
2. **5 个管理接口未实现**：接入需与赵紫龙（HTTP API）、丁晓炜（文档解析）、王智洋（索引）对齐，12 月初按 P1 推进。
3. **上传请求体格式待定**：契约只给了方法与路径，未细化 multipart 字段名，当前按 `file` + 元数据字段提交，需与赵紫龙确认。
4. **元数据更新 DTO 缺失**：契约无 `DocumentMetadataUpdate`，当前提交白名单字段；已在[数据口径文档](../admin/数据口径与契约缺口说明.md)中列为缺口。
5. **`publisher` / `source_url` 未在 `DocumentSummary` 暴露**：列表的「发布单位或来源」取自数据库字段，属契约缺口，建议 V1.1 补齐。
6. **列表筛选参数名未约定**：契约只写「可按状态筛选」，当前为前端本地筛选；接入服务端时建议使用与字段同名的 query 参数。
7. **分页当前为客户端分页**：接入真实接口后应改为服务端 `page` / `page_size` 分页。
8. **演示数据不含失败样本**：44 条登记里没有 `failed` / `uncertain`，筛选这两个值会得到空态，这是刻意的（不伪造核验失败记录）。

## 七、与 Figma 原型的对齐情况

后台样式不是照截图目测的近似值，而是用 Figma REST API 读取「26 后台 · 资料审核」（node `135:2106`）以及组件库中的 `V6 / Admin Sidebar`、`V8 / Admin Header` 节点数据后落成的，取值见下表。

| 项 | Figma 实际值（已落到 `admin.css`） |
| --- | --- |
| 文本主色 / 次要 / 动作 | `#17181B` / `#757B87` / `#303A4C` |
| 边框 / 浅底 / 激活底 | `#E3E6EB` / `#F7F8FA` / `#ECEEF1` |
| 警示红 / 深绿 / 粉色标签底 | `#E60022` / `#0F5A46` / `#FFF1F3` |
| 字体 | Noto Sans SC（**本机未安装，截图实际回落到微软雅黑**，字宽会有细微差异） |
| 侧栏 | 260px、底 `#F7F8FA`、导航行高 44 / 圆角 8、激活底 `#ECEEF1`、「管理工作台」标签 `#FFF1F3` + `#E60022` |
| 顶栏 | 72px、标题 17/700、头像 38 圆形 `#ECEEF1` |
| 页标题 / 副标题 | 30/700 行高 36 / 14/400 行高 16.8 |
| 统计卡 | 104 高、圆角 16、数字 36/700、标签 13/400 |
| 搜索框 / 主按钮 | 46 高 `#F7F8FA` 圆角 10 / 44 高圆角 10、15/500 |
| 列表容器 / 行 | 圆角 16 / 行标题 15/500、副行 12/400 行高 14.4 |
| 状态呈现 | **彩色文字而非胶囊**：正常 `#17181B`、中性 `#757B87`、中间态 `#303A4C`、异常 `#E60022` |
| 侧栏脚注 | 「仅管理员可维护公共资料与规则」+「返回学生工作台」（40 高、圆角 10、1px 墨色描边、14/700） |

仍属**有意偏离**的两处，其余均已对齐：

1. 列表用 9 列表格代替原型的卡片行——任务要求并排展示 4 个状态列，卡片流放不下（已确认）；
2. 筛选用下拉代替原型的 tab——状态维度有 4 个，tab 排不下。

## 八、代码位置

```text
frontend/
├── admin/index.html            # 后台管理端入口（薛锦荣搭的工程骨架）
├── src/admin/
│   ├── main.ts                 # 状态、事件、接口调用与演示降级
│   ├── render.ts               # 视图与弹窗的 HTML 构造
│   ├── filters.ts              # 搜索 / 筛选 / 分页 / 统计（纯函数）
│   ├── status.ts               # 契约枚举 → 中文与语气
│   ├── validate.ts             # 模拟数据枚举校验
│   ├── mock.ts                 # 模拟数据装载
│   ├── admin.css               # 后台样式（沿用第二次作业原型视觉）
│   └── data/documents.json     # 44 条模拟数据
├── src/shared/assets/fzu.png   # 福州大学校徽（与学生端同一张，后台侧栏使用）
├── src/shared/types.ts         # 追加后台管理契约类型
├── src/shared/api.ts           # 追加 5 个 admin 接口封装
└── tests/admin-filters.test.ts # 纯逻辑测试
```

> 视觉依据是 Figma「agent原型」后台画板（节点数据见第七节）与第二次团队作业导出的 24 张原型截图。校徽使用仓库内既有资源，不再用文字占位。状态已按原型改回**纯彩色文字**；仍属有意偏离的只有两处：列表用 9 列表格代替原型的卡片行（任务要求并排展示 4 个状态列）、筛选用下拉代替原型 tab（4 个状态维度 tab 排不下）。

数据来源与状态编排口径见 [`docs/assignment-03/admin/数据口径与契约缺口说明.md`](../admin/数据口径与契约缺口说明.md)。

## 九、接口就绪后的切换说明（交接清单）

**切换成本：0 行代码。** 页面启动时先请求 `GET /api/v1/admin/documents`（见 `bootstrap()`），成功即 `state.source = 'api'` 并渲染真数据；只有失败才降级到模拟数据。所以后端一上线，页面会自动切真数据、黄色说明条自动消失、右上徽标自动变成「数据来源：后端接口」。

**但真数据一上来会立刻暴露两个契约缺口**，需要组长在 V1.1 处理，否则这些列会是空的：

1. `DocumentSummary` 没有 `publisher` / `source_url` / `document_number` → 「发布单位或来源」列、详情里的文号与来源链接只能显示「—」。现在看起来有值，是因为模拟数据自带这些字段。
2. `PATCH /admin/documents/{id}` 没有定义更新 DTO，`DocumentAdminService` 也没有 update 方法 → 元数据编辑仍然只能停在前端。

**接口就绪后需要跟着调整的地方：**

- `bootstrap()` 目前一次取 `page_size=100` 再在前端分页；数据量上来后应改成按 `page` / `page_size` 请求服务端，并把 4 个状态筛选作为 query 参数下推（参数名契约未定，建议与字段同名）。
- `DocumentAdminService.list_documents()` 目前只有 `page` / `page_size`，同样需要补筛选参数。

**给后端的最小实现清单**（调用方已封装好，谁实现由组长定）：

| 方法 | 路径 | 响应模型 |
| --- | --- | --- |
| GET | `/api/v1/admin/documents?page&page_size` | `DocumentListResponse` |
| GET | `/api/v1/admin/documents/{document_id}` | `DocumentSummary` |
| POST | `/api/v1/admin/documents` | `DocumentUploadResponse` |
| PATCH | `/api/v1/admin/documents/{document_id}` | `DocumentSummary` |
| POST | `/api/v1/admin/documents/{document_id}/reindex` | `ReindexResponse` |

数据源建议先用 `docs/assignment-02/database-design/knowledge-base/入库预览_44条.json` 的 44 条（内存即可），与模拟数据同源，便于逐条比对。
