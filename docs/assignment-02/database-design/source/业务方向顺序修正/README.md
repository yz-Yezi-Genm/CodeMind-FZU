# 业务方向初始化顺序修正

修订人：丁晓炜。日期：2026年11月9日。基线：王智洋提供的数据库详细设计v1.2修正审核包。状态：本地重新生成与核对通过，待王智洋（MieSheeeep）确认纳入其详细设计交付。

原审核包的生成脚本、实际种子SQL和JSON均把学院资源导航排在竞赛与科研信息之前。本轮从`DIRECTIONS`生成源调整顺序，重新生成对应初始化材料，统一为：

| sort_order | code | name | delivery_stage |
| --- | --- | --- | --- |
| 1 | POLICY_AFFAIRS | 政策与事务办理 | v1 |
| 2 | EDUCATION_CAREER | 升学与就业发展 | v1 |
| 3 | COMPETITION_RESEARCH | 竞赛与科研信息 | v1 |
| 4 | COLLEGE_RESOURCES | 学院资源导航 | v1 |
| 5 | GROWTH_PLANNING | 个人成长档案与长期规划 | future |

前四项为首版优先支持方向，第五项为后续迭代功能。查询展示须显式按`sort_order`排序。

## 文件与用途

| 文件 | 用途 |
| --- | --- |
| [source/build_deliverables.py](source/build_deliverables.py) | 修正后的原生成脚本；相对基线仅调整DIRECTIONS中的第三、第四项 |
| [sql/02_review_seed_44.sql](sql/02_review_seed_44.sql) | 用修正后的生成源重新生成的完整44条审核用初始化SQL |
| [knowledge-base/入库预览_44条.json](knowledge-base/入库预览_44条.json) | 同次生成的完整23表入库预览JSON |
| [knowledge-base/首版资料覆盖清单_v1.2.md](knowledge-base/首版资料覆盖清单_v1.2.md) | 从同一DIRECTIONS顺序生成的业务方向覆盖说明 |
| [顺序核对结果.json](顺序核对结果.json) | 方向ID、顺序、阶段、其他表及SQL保持情况，附各文件修正前后SHA-256 |

## 生成及核对口径

以v1.2原JSON内的44条37列`import_snapshot`作为冻结输入，使用本地149个已登记文件作只读路径及哈希输入，运行修正后的原生成器。没有用后来增加业务范围列的46列索引替换原37列输入，避免把本次顺序修订混入其他资料修订。

核对结果：五条方向ID、代码、名称和阶段保持；`sort_order`依次为1到5；SQL与JSON对应；JSON其余22表逐项相等，SQL非`business_directions`的INSERT逐行相等；44个版本、149个文件、53条文档方向关联及16个办理节点不变，检索状态仍全部为`blocked`。SQL语法解析通过。编号与名称一致，资料数量不作为方向覆盖完整的证明。

## 王智洋确认与纳入步骤

1. 核对是否仍以v1.2修正审核包为最新源；如已有更新版本，先比较`DIRECTIONS`、五条方向记录及`sort_order`，避免覆盖其新增修改。
2. 确认以最终五项顺序为准，把本目录同名文件纳入原审核包对应路径，并保留原包中的`source/models.py`及其他依赖。这里是修正文件集，不是独立可运行的完整详细设计包。
3. 后续完整重生成时使用配套的44条37列冻结输入和文件，运行原包的`source/build_deliverables.py`，再执行配套验证流程，刷新原审核包的交付校验清单与完整审核稿中相关方向展示。
4. 在PR #5回复核对及采纳结果，明确最终提交使用的SQL、生成脚本、JSON及方向顺序。

初始化SQL仍是原设计的空库审核脚本，依赖原包`sql/01_schema.sql`，不是已有数据库的更新迁移；不得因顺序修正重复导入已有库。本轮没有连接或修改实际数据库，没有覆盖GitHub原31条知识库索引，也没有把44条审核材料直接开放检索。ER图及23表结构保持上一轮版本。
