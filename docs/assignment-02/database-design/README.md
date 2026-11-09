# 数据库设计

负责人：丁晓炜（数据库概念设计/ER 图）；王智洋（数据库详细设计：关系模型、ORM 映射、数据字典及说明书）；罗宇泽（统筹整合审核）。

最终版 PDF 放在本目录，命名为 `CodeMind-FZU_数据库设计说明书.pdf`。可编辑源文件放 `source/`；ER 图、关系模型、ORM 映射和数据字典放入各自子目录。

---

## 目录索引与成果导航

### 1. 概念模型与 ER 图（丁晓炜）
详见 [er/README.md](er/README.md)：
- **知识库核心概念模型**：[知识库ER图.png](er/知识库ER图.png) / [知识库ER图.svg](er/知识库ER图.svg)
- **概念与实体关系说明**：[实体关系说明.md](er/实体关系说明.md)
- **23表全库扩展关系图**：[数据库关系图.mmd](er/数据库关系图.mmd)
- **概念与详细设计对接**：[详细设计对接说明.md](er/详细设计对接说明.md)

### 2. 关系数据模型与 DDL（王智洋）
- **关系数据模型**：[relational-model/关系数据模型_v1.2.md](relational-model/关系数据模型_v1.2.md)（含 23 张表规范化设计、主外键及复合外键清晰表达、业务语义）
- **Mermaid 关系图**：[relational-model/关系数据模型_v1.2.mmd](relational-model/关系数据模型_v1.2.mmd)
- **数据库 DDL 脚本**：[sql/01_schema.sql](sql/01_schema.sql)（PostgreSQL 16 候选技术基线下的 DDL 脚本；UUID 由应用层生成，`updated_at` 由业务服务显式维护，未配置自动更新触发器）
- **初始化种子数据**：[sql/02_review_seed_44.sql](sql/02_review_seed_44.sql)（44 条资料、149 个文件、五大业务方向种子数据）

### 3. 数据字典与约束索引（王智洋）
- **数据字典**：[data-dictionary/数据字典_v1.2.md](data-dictionary/数据字典_v1.2.md)（23 张表、233 个字段类型、非空性与说明）
- **约束与索引设计**：[data-dictionary/约束与索引设计_v1.2.md](data-dictionary/约束与索引设计_v1.2.md)（主键、唯一键、复合外键 `(组合) → 父表(组合)`、CHECK 约束与业务索引）

### 4. ORM 映射与技术基线（王智洋）
- **SQLAlchemy 2 模型**：[source/models.py](source/models.py)（23 张表的 SQLAlchemy 2.0 命令式 ORM 模型定义，采用 `registry.map_imperatively`）
- **ORM 映射说明**：[orm/ORM映射说明_v1.2.md](orm/ORM映射说明_v1.2.md)（技术候选基线、命令式映射规则与约束保障）

### 5. 知识库规划与业务规则（王智洋）
- **首版覆盖清单**：[knowledge-base/首版资料覆盖清单_v1.2.md](knowledge-base/首版资料覆盖清单_v1.2.md)
- **入库数据预览**：[knowledge-base/入库预览_44条.json](knowledge-base/入库预览_44条.json)
- **业务问答与反馈规则**：[业务回答与反馈规则_v1.2.md](业务回答与反馈规则_v1.2.md)

### 6. 协同确认与说明书完整稿（王智洋）
- **架构与概念设计确认**：[架构与概念设计确认说明_v1.2.md](架构与概念设计确认说明_v1.2.md)（含王智洋针对丁晓炜业务方向调序及同版本外键的正式书面回执；与赵紫龙确认 PostgreSQL 16 / SQLAlchemy 2 命令式候选基线及实施边界）
- **详细设计说明书完整稿**：[数据库详细设计说明书_v1.2.md](数据库详细设计说明书_v1.2.md)
- **最终审核稿**：[完整审核稿_v1.2.md](完整审核稿_v1.2.md)
- **自动化测试报告**：[验证报告_v1.2.md](验证报告_v1.2.md)（21 项单元测试、默认数据源选择、五大业务方向顺序断言与 SQLite 全表建表及核心资料导入验证：23 张表建表、8 张表插入 fixture）
- **交付校验清单**：[交付文件校验清单.json](交付文件校验清单.json)
