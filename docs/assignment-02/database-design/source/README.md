# 数据库设计说明书与自动化工具源码

本目录包含 CodeMind-FZU 数据库详细设计的全套自动化构建、校验与文档生成脚本，旨在保障交付物的高可复现性与工程规范。

---

## 📂 源码与数据结构说明

- **`models.py`**：基于 SQLAlchemy 2.0 命令式映射规范编写的 23 张表 ORM 模型映射（采用 `registry.map_imperatively` 与类定义解耦）。包含完整主键、复合唯一约束、Check 约束与关系属性。UUID 主键由应用层调用端生成，`updated_at` 由业务服务显式维护，未在数据库配置自动更新触发器。
- **`build_deliverables.py`**：衍生交付物构建脚本。自动从数据字典与模型生成 PostgreSQL 16 候选技术基线下的 DDL（`sql/01_schema.sql`）、种子数据（`sql/02_review_seed_44.sql`）、数据字典 Markdown 以及业务方向覆盖清单。
  - **支持文件内容 SHA-256 严谨计算**：当政策资料物理文件存在时正常计算内容哈希；当文件不存在时严格置为 NULL (`None`)，绝不使用路径字符串生成伪哈希。
  - **支持多种数据根目录优先级检索**：
    1. CLI 参数 `--data-dir <path>`
    2. 环境变量 `CODEMIND_KB_ROOT`
    3. 外部资料目录 `audit_materials/knowledge/知识库/政策资料`
    4. 本目录内置完整44条索引夹具 `fixtures/`（干净克隆默认使用）
    5. 仓库内旧目录 `knowledge_base/政策资料`（仅作为无夹具时的后备来源）。
- **`generate_pdf.py`**：基于 `markdown-it-py` 和无头浏览器（Edge / Chrome / Chromium）的说明书 PDF 自动化编译脚本。
  - 支持 CLI 参数 `--browser <path>` 或环境变量 `CODEMIND_BROWSER_PATH`。
  - 支持 Windows / macOS / Linux 常见浏览器可执行文件跨平台自动检测。
- **`validate_deliverables.py`**：离线全项核验脚本。
  - 严格断言五大业务方向的代码、名称与 `sort_order`（1~5）顺序，防止生成回退。
  - 自动运行 SQLite 内存数据库完整建表与 44 条阶段数据入库。
  - 自动执行 `pglast` 对 PostgreSQL DDL 与 Seed 进行 AST 语法树解析。
  - 自动执行 21 项自动化单元测试。
- **`fixtures/`**：内置最小测试数据夹具（包含 44 条资料完整元数据 CSV），确保克隆仓库的队员开箱即可复现全套流程。
- **`test_models.py` & `test_import_rules.py`**：21 项单元测试用例，覆盖默认数据源选择、显式配置优先级、跨版本外键拦截、不可级联删除、Check 约束、时间精度解析以及文件真实 SHA-256 计算与缺失置空逻辑。
- **`requirements-review.txt`**：运行本目录工具链的完整 Python 依赖清单。

---

## 🛠️ 复现与运行指南

### 1. 安装依赖
```bash
pip install -r docs/assignment-02/database-design/source/requirements-review.txt
```

### 2. 重新构建交付物（生成 DDL、数据字典与种子数据）
```bash
# 默认使用自动检测（若无外部资料则自动使用 fixtures 夹具）
python docs/assignment-02/database-design/source/build_deliverables.py

# 或显式指定政策资料目录
python docs/assignment-02/database-design/source/build_deliverables.py --data-dir "path/to/data"
```

### 3. 执行全量验证与单元测试
```bash
python docs/assignment-02/database-design/source/validate_deliverables.py
```
运行完成后将输出验证报告并更新 `validation_report.json`。

### 4. 重新编译生成最终版 PDF 说明书
```bash
# 自动检测本地 Edge 或 Chrome 浏览器并编译
python docs/assignment-02/database-design/source/generate_pdf.py

# 或指定自定义浏览器路径
python docs/assignment-02/database-design/source/generate_pdf.py --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```
PDF 输出位置：`docs/assignment-02/database-design/CodeMind-FZU_数据库设计说明书.pdf`。

### 5. 更新当前审核稿、PDF、校验清单及压缩包
```bash
python docs/assignment-02/database-design/source/finalize_acceptance.py
```
该命令先在保留仓库旧索引的临时目录中验证默认选择fixture，再生成当前资料预览并执行21项测试，最后更新审核稿、PDF及逐文件校验的压缩包。需安装上述依赖并具备可用浏览器。

fixture仅含44条索引，不含149个物理文件。版本级`extraction_status`记录原索引的43条已提取、1条待OCR；文件级`processing_status`描述当前环境，缺失时为`failed`，`sha256`为空，备注保留原索引状态。原核查记录不代表Agent回答资格，检索仍为`blocked`。
