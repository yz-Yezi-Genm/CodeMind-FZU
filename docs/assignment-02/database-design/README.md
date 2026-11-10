# AgentX 数据库设计说明书

项目：CodeMind-FZU。正式文档版本：V1.3，编制日期：2026年11月10日。数据库技术基线沿用v1.2，包含23张表、233个字段及40组外键。

## 正式提交文件

- [AgentX_数据库设计说明书.pdf](AgentX_数据库设计说明书.pdf)：正式阅读与提交版本
- [可编辑Word稿](source/AgentX_数据库设计说明书.docx)：封面、自动目录、标题样式、图表及页码
- [完整Markdown源稿](AgentX_数据库设计说明书.md)：正文与自动整理的技术附录
- [文档检查结果](source/document_verification.json)：目录页码、技术完整性与输入校验记录

正文按引言、数据库概述、概念结构、逻辑结构、物理结构、ORM映射、数据管理、验证与参考资料组织。附录保留完整数据字典、外键与约束索引、ORM映射、既有验证记录、44条资料范围及技术文件定位。全库总览和资料治理子图使用A3横向折页，其余页面采用A4。

## 重新生成

在Windows电脑安装Microsoft Word后，从仓库根目录运行：

```powershell
python -m pip install -r docs/assignment-02/database-design/source/requirements-document.txt
python docs/assignment-02/database-design/source/generate_pdf.py
```

程序生成Word稿，调用独立Word实例更新目录和页码，再导出同名PDF。已渲染的图形随仓库提交，常规重生成无需联网下载Mermaid。

```powershell
# 文档核对与完整交付打包，不重跑数据库实验
python docs/assignment-02/database-design/source/finalize_acceptance.py
```

打包结果为仓库根目录的`AgentX_数据库设计说明书_v1.3.zip`，包含正式PDF、Word源稿、图形资源和技术成果。独立解压后可在包目录运行`python source/finalize_acceptance.py`。

## 技术成果与历史材料

`relational-model/`、`data-dictionary/`、`orm/`、`sql/`、`knowledge-base/`和`source/models.py`保留已确认的技术成果。`er/`保留丁晓炜的概念设计。v1.2审核稿和旧命名PDF作为历史文件保留，正式提交以本目录的AgentX命名文件为准。

既有数据库验证为21项单元测试，以及SQLite全表建表和8张核心资料表导入验证。本轮整理文档并复用既有报告。尚未实际连接PostgreSQL，政策联网复核与OCR尚未完成，Agent和数据库服务尚未集成。
