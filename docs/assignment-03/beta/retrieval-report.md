# Beta 本地知识检索（BM25）阶段性测试与验证报告

2026-11-23 · 知识库检索与资料入库（王智洋）

> **数据边界说明**：本报告当前记录的是 **Beta 合成测试资料（`example.invalid`）** 上的四领域基线验收与加载门禁验证结果，**不代表正式审核政策资料已完成放行**。仓库 `knowledge_base/processed/alpha/approved/` 目前尚未合入经人工签核的正式资料包；待丁晓炜交付正式整理包并经罗宇泽最终审核放行后，将使用同一套评测脚本补充正式资料的检索验收记录。

## 一、数据库五大业务方向字典核对

经核对仓库正式数据库初始化脚本（`docs/assignment-02/database-design/sql/02_review_seed_44.sql`）与 `CodeMind-FZU_Beta_Interface_Spec_V2.1-Final.md` §4.1–4.2，五大业务方向正式 `code` 与 Beta 业务场景对应关系如下（检索实现与测试均严格沿用，未自行创造或改名）：

| 序号 | 数据库业务方向 `code` | 中文名称 | 对应 Beta 场景 | Beta 范围 |
|---|---|---|---|---|
| 1 | `POLICY_AFFAIRS` | 政策与事务办理 | S2 奖学金申请 | 纳入 |
| 2 | `EDUCATION_CAREER` | 升学与就业发展 | S3 推免条件咨询 | 纳入 |
| 3 | `COMPETITION_RESEARCH` | 竞赛与科研信息 | S1 竞赛认定（创新学分、综测加分） | 纳入 |
| 4 | `COLLEGE_RESOURCES` | 学院资源导航 | S4 学院资源导航 | Beta 新增 |
| 5 | `GROWTH_PLANNING` | 个人成长档案与长期规划 | — | 后续迭代 |

多业务方向约定：保留 `RetrievalRequest.business_direction_code` 为单值可选字段；当问题跨业务方向或 Agent 无法唯一确定方向时，不传该字段，由 `LocalBM25Retriever` 执行全库检索，避免因单一分类过滤漏检必要证据。

## 二、本阶段检索模块改进

1. **标题 + 正文联合 BM25 索引**（`backend/retrieval/local.py`）：
   - 在 `index_document()` 中将 `metadata.title` 的词项与 `chunk.content` 的词项联合纳入 BM25 索引，同时保留“仅正文无可检索词时跳过并报告 `TOKENLESS_CHUNKS_SKIPPED`”的既有约束，避免纯标点片段借标题混入索引。
   - 标题词与正文词共同参与排序后，查询“文档标题关键词 + 具体条款正文关键词”可准确命中并置顶对应条款片段。
2. **双实例并发索引与单边撤回隔离**（`tests/test_local_retrieval.py`）：
   - 响应 PR #51 审核建议，新增 `test_two_retriever_instances_isolate_independent_withdrawal`：两个 `LocalBM25Retriever` 实例分别索引同一份资料，其中一个实例将资料撤回为 `blocked` 后，该实例的 `retrieve` / `get_document_metadata` / `get_parsed_chunk` 立即清空，而另一个实例不受任何影响。
3. **公共接口一致性**（已在 PR #51 合入 `main`）：
   - `Retriever` Protocol 正式声明 `retrieve`、`get_document_metadata(version_id: UUID) -> DocumentMetadata | None`、`get_parsed_chunk(chunk_id: UUID) -> ParsedChunk | None`；三方法共用同一 `LocalBM25Retriever` 实例，返回深拷贝，未开放资料返回 `None`。

## 三、正式加载与过滤验证

通过 `load_approved_alpha_retriever(..., allow_missing=False)` 在含 5 份合规合成包（S1、S2、S3 及按 PR #45 正式分类拆分的 S4 R3/R2）与 2 份未开放/未签核诱饵包的目录中实测：

- **成功加载（5 份，8 个片段）**：`s1-competition-synthetic.json`、`s2-scholarship-synthetic.json`、`s3-recommendation-synthetic.json`、`s4-lab-synthetic.json`（`category_name=实验室与科研团队`）、`s4-study-synthetic.json`（`category_name=培养方案与课程`），均满足 `retrieval_status=enabled`、`temporal_notes["human_approved"] is True`、中文五键 `applicability_raw`（`适用年级`/`适用专业`/`适用对象`/`学院`/`适用届别`）且文件 SHA-256 校验通过，`IndexingStatus.INDEXED` 无 warnings。
- **门禁跳过（2 份，0 片段入库）**：
  - `decoy-blocked.json`：`retrieval_status=blocked，仅允许加载 enabled 资料`
  - `decoy-unapproved.json`：`temporal_notes 未标记 human_approved=true，未通过人工审核`
- **负向查询验证**：无匹配词（`量子纠缠核聚变`）、`blocked` 诱饵专属词（`暗号X999`）、未签核诱饵专属词（`暗号Y888`）检索结果均为 `[]`。

## 四、S1–S4 四大场景检索测试集与评测结果

复现命令：

```powershell
python -X utf8 -m scripts.eval_beta_retrieval
python -X utf8 -m unittest discover -s tests -p test_beta_retrieval_scenarios.py -v
# 待正式审核包放行至 approved/ 后，可直接探查正式目录：
python -X utf8 -m scripts.eval_beta_retrieval --corpus-dir knowledge_base/processed/alpha/approved
```

### 汇总指标（合成基线，9 条查询）

- **Hit@1**：`1.0`（9/9）
- **Hit@3**：`1.0`（9/9）
- **MRR**：`1.0`

### 逐条查询、原文定位追溯与人工核查

| 编号 | 场景 | 查询语句 | 过滤方向 | 期望目标 | 命中排名 | Top-1 定位追溯（`locator` / `original_locator`） | BM25 分数 | 人工相关性核查 |
|---|---|---|---|---|---|---|---|---|
| Q1-S1-EN | S1 竞赛认定 | `ACM-ICPC 国家级一等奖 创新创业学分` | `COMPETITION_RESEARCH` | `BETA-SYN-S1-2026#1` | 1 | `第 1 章 第 3 条` / `PDF 第 2 页` | 7.099617 | 准确命中 A 类竞赛与创新学分条款 |
| Q2-S1-ZH | S1 竞赛认定 | `竞赛认定申请 综测科创加分` | `COMPETITION_RESEARCH` | `BETA-SYN-S1-2026#2` | 1 | `第 2 章 第 7 条` / `PDF 第 4 页` | 4.418056 | 准确命中认定流程与综测加分条款 |
| Q3-S2-TITLE | S2 奖学金申请 | `院级奖学金 评选通知 GPA排名` | `POLICY_AFFAIRS` | `BETA-SYN-S2-2026#1` | 1 | `第 1 节` / `PDF 第 1 页` | 8.801863 | 标题词 + GPA 正文词共同生效，置顶条件片段 |
| Q4-S2-DEADLINE | S2 奖学金申请 | `奖学金申请表 成绩单 截止时间` | `POLICY_AFFAIRS` | `BETA-SYN-S2-2026#2` | 1 | `第 2 节` / `PDF 第 2 页` | 7.146789 | 准确命中材料与截止时间片段 |
| Q5-S3-EN | S3 推免条件咨询 | `推免研究生 CET-6 425分 无不及格` | `EDUCATION_CAREER` | `BETA-SYN-S3-2027#1` | 1 | `第 3 条` / `PDF 第 1 页` | 5.623965 | 中英文外语与学业条件准确召回 |
| Q6-S3-BONUS | S3 推免条件咨询 | `CCF推荐会议 推免学术专长加分` | `EDUCATION_CAREER` | `BETA-SYN-S3-2027#2` | 1 | `第 8 条` / `PDF 第 3 页` | 6.465476 | 准确命中学术专长加分条款 |
| Q7-S4-LAB | S4 学院资源导航 | `人工智能与大数据实验室 GPU算力申请` | `COLLEGE_RESOURCES` | `BETA-SYN-S4-R3-2026#1` | 1 | `第 1 部分` / `网页 第 1 节` | 8.156222 | 对齐 R3 `实验室与科研团队`，准确命中实验室与 GPU 渠道 |
| Q8-S4-OFFICE | S4 学院资源导航 | `本科培养方案 教务办 成绩单盖章` | `COLLEGE_RESOURCES` | `BETA-SYN-S4-R2-2026#1` | 1 | `第 2 部分` / `网页 第 2 节` | 9.056452 | 对齐 R2 `培养方案与课程`，准确命中培养方案与教务办窗口 |
| Q9-MULTI-DIR | 多业务方向（全库） | `竞赛获奖 综测加分 奖学金申请表` | `None`（全库） | `BETA-SYN-S2-2026#*` | 1 | Top-4 同时召回 S2、S1、S3 相关条款 | 11.496657 | 未出现跨方向漏检 |

### 元数据与原始片段追溯核验

`tests/test_beta_retrieval_scenarios.py` 已校验同一 `Retriever` 实例下：
- `get_document_metadata(hit.version_id)` 完整返回 `record_code`、`version_no`、`applicability_raw`、`deadline_on`、`temporal_notes`、`source_verification_status`、`timeliness_verification_status`、`retrieval_status`；
- `get_parsed_chunk(hit.chunk_id)` 完整返回 `content`、`locator`、`locator_note`、`original_locator`、`source_file_key`、`chunk_no`，且与 `RetrievedChunk` 一一对应。

## 五、待完成事项（依赖上游正式资料交接）

1. 待丁晓炜完成 Beta 正式资料整理并经罗宇泽人工审核放行至 `knowledge_base/processed/alpha/approved/` 后，执行真实正式资料包的加载过滤、S1–S4 四领域检索与原文对照验收，并将真实验收结果补充至本报告。
2. 配合吴诗莹完成 Beta `AgentWorkflow` 端到端联调（验证检索召回、业务规则门禁与 Citation 引用链路）。
