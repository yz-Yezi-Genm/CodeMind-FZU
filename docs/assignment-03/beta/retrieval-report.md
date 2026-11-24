# Beta 本地知识检索（BM25）技术交付与合成评测报告

2026-11-24 · 知识库检索与资料入库（王智洋）

> **验收边界声明**：本报告与 PR #53 **仅代表 Beta 检索技术交付、BM25 对照评测与合成四领域基线验证，不代表正式政策资料检索验收完成**。仓库 `knowledge_base/processed/alpha/approved/` 当前正式包数为 0，PR #41 交付的 9 包 514 片段全部保持 `retrieval_status=blocked`、`human_approved=false`。待正式资料经人工签核放行至 `approved/` 后，将另行补充真实四领域查询集、期望片段标注、原文对照及真实检索指标。

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

1. **轻量标题加权 BM25（正文 + 0.1×文档标题）**（`backend/retrieval/local.py`）：
   - 将正文 BM25（片段级 `chunk.content`）与标题 BM25（文档级 `metadata.title`）分开计算，最终排序分为 `content_bm25 + 0.1 * title_bm25`（`_TITLE_WEIGHT = 0.1`），同时保留“仅正文无可检索词时跳过并报告 `TOKENLESS_CHUNKS_SKIPPED`”的既有约束。
   - 相比直接将标题词等权拼接到每个片段，轻量标题加权既保留了纯标题命中与标题+正文排序优势，又避免长标题文档的无关片段在多目标跨领域查询中挤占其他必要证据的 Top-K。
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

## 五、BM25 对照评测（仅正文 vs 轻量标题加权 BM25）

为验证在 `LocalBM25Retriever` 中引入 `metadata.title` 后，标题词是否会在长文档、相似政策标题、同名实验室或**多目标跨领域查询**场景下挤占 Top-K，使用独立压力合成集（8 份文档、39 个片段、20 条单目标压力查询 + 4 条多目标跨领域查询，见 `scripts/eval_beta_bm25_comparison.py`，全部采用 `example.invalid` 虚构来源，不触碰真实候选资料）对比了「仅正文 BM25」与「轻量标题加权 BM25（`_TITLE_WEIGHT = 0.1`）」：

复现命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.eval_beta_bm25_comparison
```

### 反例复现与权重调整效果

在复审提出的两条多目标跨领域反例上，调整前（等权拼接标题词到每个片段）与调整后（独立文档级标题 BM25 × `0.1`）对比如下：

- **M01**（`2026年本科生奖学金评定管理办法的一等奖GPA要求，以及本科毕业学分165学分要求？`，期望 `CMP-SCH-UG#4` + `CMP-STUDY-R2#1`）：
  - 调整前（等权拼接）：Top-5 全被 `CMP-SCH-UG` 占满，丢失 `CMP-STUDY-R2#1`（Recall@5 = `0.5`）；
  - 调整后（`_TITLE_WEIGHT = 0.1`）：Top-2 即同时命中 `CMP-SCH-UG#4`（#1）与 `CMP-STUDY-R2#1`（#2），**Recall@5 = `1.0`**。
- **M02**（`2026年青禾计划智能感知实验室招募报名截止日期，以及推免申请人外语CET-6要求？`，期望 `CMP-LAB-R3#3` + `CMP-REC-QUAL#1`）：
  - 调整前（等权拼接）：Top-5 被实验室包占满，丢失 `CMP-REC-QUAL#1`（Recall@5 = `0.5`）；
  - 调整后（`_TITLE_WEIGHT = 0.1`）：Top-2 即同时命中 `CMP-LAB-R3#3`（#1）与 `CMP-REC-QUAL#1`（#2），**Recall@5 = `1.0`**。

| 指标 / 维度 | 仅正文 BM25 | 标题+正文 BM25（`_TITLE_WEIGHT = 0.1`） | 变化 |
|---|---|---|---|
| 文档 / 片段 / 单目标查询 / 多目标查询 | 8 / 39 / 20 / 4 | 8 / 39 / 20 / 4 | — |
| 单目标总体 Hit@1 | 1.0 (20/20) | 1.0 (20/20) | 0.0 |
| 单目标总体 Hit@3 | 1.0 (20/20) | 1.0 (20/20) | 0.0 |
| 单目标总体 MRR | 1.0 | 1.0 | 0.0 |
| 长文档（6 查询）Top-3 模板条款（总则/组织机构/附则/联系人）挤占次数 | 4 | 4 | 0（无恶化） |
| 相似政策标题区分（4 查询）Hit@1 | 1.0 | 1.0 | 0.0 |
| 同名实验室区分（4 查询：R3 招募 vs R4 介绍、视觉组 vs 语音组）Hit@1 | 1.0 | 1.0 | 0.0 |
| 标题+正文联合查询（4 查询：政策名仅出现在标题）Hit@1 | 1.0 | 1.0 | 0.0 |
| 跨业务方向单目标竞争排序（2 查询，`business_direction_code=None`）Hit@1 | 1.0 | 1.0 | 0.0 |
| **多目标跨领域 Recall@5（4 查询：M01–M04，含两条复审反例）** | **0.875 (3/4 满召回)** | **0.875 (3/4 满召回；M01/M02/M03 均 1.0)** | **0.0（较等权拼接 0.5 提升 +0.375）** |

**结论**：采用独立正文 BM25 + 轻量文档级标题加权（`_TITLE_WEIGHT = 0.1`）后，单目标 20 条查询保持 100% Hit@1 / Hit@3 / MRR，多目标跨领域 Recall@5 与仅正文 BM25 完全持平（两条复审反例均在 Top-2 满召回），且保留纯标题检索能力，不引入向量检索或复杂重排。完整对照 JSON 见 [retrieval-bm25-comparison.json](evidence/retrieval-bm25-comparison.json)。

## 六、Python 3.10 回归与 PR #41 9 包 514 片段只读校验

测试环境：`Python 3.10.16`（`.venv`，已同步包含 PR #46 的最新 `main` `0251ec5`，含 `fastapi 0.162.5`、`httpx 0.28.1`、`pydantic 2.14.4`、`pytest 9.2.0`、`uvicorn 0.54.0`、`openpyxl` 等全部依赖）。完整终端日志见 [retrieval-py310-regression.txt](evidence/retrieval-py310-regression.txt)。

| 验证项 | 命令 | 实际结果 |
|---|---|---|
| 检索、加载器与四领域专项 | `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_local_retrieval.py tests/test_alpha_corpus.py tests/test_beta_retrieval_scenarios.py -v` | **36 passed, 12 subtests passed** |
| 后端全量 `pytest`（含 PR #46） | `.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q -rs --tb=short` | **572 passed, 3 skipped, 242 subtests passed**（0 失败） |
| S1–S4 合成基线脚本 | `.\.venv\Scripts\python.exe -X utf8 -m scripts.eval_beta_retrieval` | Hit@1 = 1.0 / Hit@3 = 1.0 / MRR = 1.0，拦截 2 份未开放诱饵 |
| Agent 离线联调 | `.\.venv\Scripts\python.exe -X utf8 -m scripts.check_retrieval_agent` | **PASS: 4 Agent -> Retriever cases** |
| PR #41 9 包 514 片段只读校验 | `.\.venv\Scripts\python.exe -X utf8 -m knowledge_base.processing.check_beta_policy_handoff` | 9 包 / 514 片段（S1:310 / S2:127 / S3:29 / S4:48）完整离线索引；全部 `blocked` 资料 `get_document_metadata()` 与 `get_parsed_chunk()` 均返回 `None`，正式检索命中 0，`approved/` 正式包数为 0 |
| 格式检查 | `git diff --check` | 退出码 0 |

## 七、后续正式资料验收事项（另行提交，不阻塞 PR #53）

1. 待正式政策资料经人工签核放行至 `knowledge_base/processed/alpha/approved/` 后，另行补充真实四领域查询集、期望片段标注、原文/章节对照及真实检索指标。
2. 配合吴诗莹完成 Beta `AgentWorkflow`（PR #46 合入后）端到端联调与回归测试。
