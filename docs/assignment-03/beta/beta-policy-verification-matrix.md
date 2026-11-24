# Beta 四领域官方资料核验清单

**2026-11-24收尾：本轮正式送审口径为[统一人工审核清单](beta-policy-approval-checklist.md)的9包514片段；已同步main@a3ffdd0（含#45/#51/#49）。本文保留原始8包501片段技术核验批次，全部未人工签核，不能整批当作本轮放行名单。**

最新青禾分类交付见[B8两包说明](qinghe-b8-handoff.md)：R3/R4各24片段、共48，独立待审核。本文的8包/501片段为保留的原批次基线，旧青禾混合包不用于新A4交接，其他7份不变。

核验批次：2026-11-23。首次处理基线：`main@90df0f9`（最新集成基线见上方）。执行依据：《Beta 冲刺任务书 V2.1》第 3 章丁晓炜任务、《Beta 接口规范 V2.1-Final》第 9—12 章，以及本轮个人任务通知。

## 1. 当前交付与审核口径

- 本批处理 **8 份独立政策/通知资料、501 个片段**，覆盖 S1—S4；其中 5 份是 Alpha 候选资料的重新核验版本，新增处理创新学分、接收推免复试、青禾计划 3 份资料。青禾通知及其 XLSX 属于同一份资料，不重复计数。
- 原有 44 条资料登记、七类分类和原核查记录不改动、不重新编号。本批只是其中 8 条的处理版本，不能说全体 44 条都已重新核验。
- 8 份均已核对官方正文入口、页面发布日期和关联原件；`source_verification_status=verified` 仅表示来源技术核验，不代表政策已获人工审核。
- **8 份全部 `retrieval_status=blocked`、`temporal_notes.human_approved=false`；最终人工审核通过数为 0。** 四份通则/有歧义资料的时效为 `uncertain`；星火、推荐资格、接收复试首批、青禾本批次标为 `expired`。
- 开工核查：`knowledge_base/processed/alpha/approved/` 只有说明文件，没有正式 DocumentPackage。本次不写入该目录，不修改默认 blocked 生成逻辑，不开放正式问答。
- 本文的“已核对”指自动结构/哈希检查及 AI 原文对照；不冒充项目负责人罗宇泽的最终人工签核。

## 2. 四领域清单

发布单位简写：教务处＝福州大学教务处；学工部＝福州大学学生工作部（处）；学院＝福州大学计算机与大数据学院（软件学院）。文件正文以实际落款为准。

| 场景 / 包名 | 资料名称与官方来源 | 发布日期 / 发布单位 | 年度、对象及用途 | 内容完整性与本次核对 | 时效 / 未完成事项 | 片段 / 开放状态 |
|---|---|---|---|---|---|---|
| S1 / `competition.json` | [关于公布大学生学科竞赛级别认定结果的通知](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbnewsid=14534&wbtreeid=1039)，校教〔2026〕9号 | 2026-03-06 / 教务处 | 2026 认定结果；按学校办法申请相关认定的学生；不能直接当作综测加分或奖学金目录 | 本次直接取得真实通知正文，核对文号、三个附件入口；3 DOCX 新下载与 Alpha 哈希一致；保留 205 数据行的表头、合并标记及脚注 | `uncertain`；待逐项人工语义签核、最新版本确认；本次网络可访问不代表所有网络均可访问 | 224 / blocked |
| S1 / `innovation.json` | [本科生创新创业实践与素质拓展学分认定管理实施办法](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1095&wbnewsid=12993)，校教〔2024〕7号 | 2024-05-30 / 教务处 | 本科生创新创业/素质拓展学分；按入学年级、培养方案及认定目录使用 | 第1—28条及 HTML 表格已提取，保留 rowspan/colspan；第27条明确 2024-09-01 执行、2022办法废止及2016办法过渡条件 | `uncertain`；需要人工确认目标年级与现行性；原始分、学分、综测分不可互换 | 86 / blocked |
| S2 / `scholarship.json` | [关于印发本科生奖学金评定管理办法的通知](https://stuic.fzu.edu.cn/info/1032/6937.htm)，福大学〔2026〕23号 | 2026-05-18 / 福州大学，学工部发布 | 适用全日制在籍本科生的校级通则；各奖项以具体条款为准 | 第1—15条重新提取；金额/比例/排除条件保留；第14条说明公布施行及2024办法废止；当前规章列表仍列该办法 | `uncertain`；有限版本排查不等于官方现行性证明；关键数值、适用性待最终人工审核 | 59 / blocked |
| S2 / `college-scholarship.json` | [关于做好学院各类院级奖学金评选工作的通知](https://ccds.fzu.edu.cn/info/1165/11707.htm) | 2026-04-13 / 学院 | 院级社会专项；正文含本科生/研究生及不同奖项对象，不能混用 | 网页33个单元完整提取；ZIP仍为 Alpha 已审计的同哈希原件；表格隐私检查不代替政策审核 | `uncertain`；发布2026年，正文/申请表写2025年度，另含2025.03—2026.02等区间，待学院解释，不擅自更正 | 33 / blocked |
| S2 / `xinghuo.json` | [关于做好2026年福州大学“星火奖教奖学金”评选工作的通知](https://ccds.fzu.edu.cn/info/1119/11710.htm) | 2026-04-20 / 学院 | 2026通知沿用2025细则；学生、教师条款必须分别使用 | 网页正文及教师/学生章节上下文保留；学生30人/4000元与教师16人/5000元分开；RAR沿用原隐私审计 | `expired`；2026-04-26前报送已过期；三份旧 DOC 未新增为正式政策正文，不提供完整表格填写指导 | 35 / blocked |
| S3 / `recommendation.json` | [2027年推荐优秀应届本科毕业生免试攻读研究生工作方案](https://ccds.fzu.edu.cn/info/1119/11932.htm) | 2026-09-08 / 学院 | 2027届、本院对应本科专业的推荐资格；不是下一届现行方案 | 新下载4页PDF与 Alpha 同哈希，沿用既有逐页对照；第4页表按行保留个人/集体等表头和数值 | `expired`；2026-09-09 21:00已截止；30/60志愿小时边界及计分表待官方解释/人工签核 | 20 / blocked |
| S3 / `retest.json` | [2027年招收直博生、硕士生推免复试方案及实施细则](https://ccds.fzu.edu.cn/info/1138/11961.htm) | 2026-09-17 / 学院 | 接收已取得所在学校推免资格的校内外应届本科生；硕士/直博条件分别适用 | 页面正文实际为嵌入PDF，已取得9页原件并逐页提取、渲染AI对照；第2页6行招生计划表顺序保留；不能把空网页当全文 | `expired`（首批）；9月19日11:00预报名导出、9月20日16:00资格资料、9月22日复试均已过；后续批次另查公告；复试用表ZIP未处理 | 9 / blocked |
| S4 / `qinghe.json` | [2026—2027学年“青禾计划”本科生进实验室报名通知](https://ccds.fzu.edu.cn/info/1160/12008.htm)及实验室需求XLSX | 2026-10-16 / 学院 | 本院本科生，另须符合各实验室条件；资源信息与当年报名流程 | 10个通知单元＋25个XLSX单元；24条实验室记录、9列字段、226非空单元格全量保留，另2空工作表；XLSX与报名DOCX新下载均与原归档同哈希；报名表为空白模板 | `expired`；10月31日前报名已截止；人数是当时计划，非实时空缺；联系方式为原公开渠道，未测试可达或代替联系实验室 | 35 / blocked |

统计：S1=2份、S2=3份、S3=2份、S4=1份，合计8份。青禾计划仅用于S4，`business_direction_codes`只包含`COLLEGE_RESOURCES`，不参加S1竞赛认定检索；原44条登记和全局字典不改写，原业务映射保留在本批元数据的`temporal_notes.business_scope_adjustment`中供追溯。S1—S4只用于场景标签，DTO采用既有业务方向代码。

## 3. 原件、转换稿与片段的对应关系

公共根目录均为仓库根目录，JSON中的 `storage_key` 为相对 POSIX 路径，不含个人电脑绝对路径。

| 包 | 原始文件（相对批次原件目录） | 转换稿 |
|---|---|---|
| competition | `competition.html`、`competition-attachment-1/2/3.docx` | `texts/competition.md` |
| innovation | `innovation.html` | `texts/innovation.md` |
| scholarship | `scholarship.html` | `texts/scholarship.md` |
| college-scholarship | `college-scholarship.html`；另关联11月19日ZIP | `texts/college-scholarship.md` |
| xinghuo | `xinghuo.html`；另关联11月19日RAR | `texts/xinghuo.md` |
| recommendation | `recommendation.html`、`recommendation-pdf.pdf` | `texts/recommendation.md` |
| retest | `retest.html`、`retest.pdf` | `texts/retest.md` |
| qinghe | `qinghe.html`、`qinghe-labs.xlsx`、`qinghe-registration.docx` | `texts/qinghe.md` |

- 批次原件目录：[`knowledge_base/processing/policy-review/2026-11-23/`](../../../knowledge_base/processing/policy-review/2026-11-23/)。原始响应不改写，`source-fetch.json`记录请求/最终URL、UTC核查时间、响应类型、SHA-256和字节数。
- 转换稿和待审核DTO目录：[`knowledge_base/processed/alpha/pending-review/beta-2026-11-23/`](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/)。入口为 `manifest.json`；每个包引用自己的Markdown及实际原件。
- [`source-units.json`](../../../knowledge_base/processing/policy-review/2026-11-23/source-units.json)固定所有输入哈希，并保存完整来源单元；[`chunk-source-map.json`](../../../knowledge_base/processing/policy-review/2026-11-23/chunk-source-map.json)逐一对应501个片段、字符区间、原件SHA、HTML XPath / DOCX行 / PDF页 / XLSX工作表行列及转换方法。
- [`verification-evidence.json`](../../../knowledge_base/processing/policy-review/2026-11-23/verification-evidence.json)记录8份来源检查、3个列表页的有限版本排查及空白报名表检查。没有遍历分页/全站，不据此宣称“绝无更新版本”。
- ZIP/RAR未重新下载或改写，沿用11月19日原件及11月20日补查的[隐私审计](../../../knowledge_base/processing/policy-review/2026-11-19/form-privacy-audit.json)。重新计算并对比既定哈希；未把表头/隐私检查混写成正式政策正文转换。

## 4. 青禾 XLSX 转换核对

原始文件名：**计算机与大数据学院（软件学院）本科生进实验室需求一览表.xlsx**。存储别名为 `qinghe-labs.xlsx`，真实文件名、官方附件URL与通知父页面同时记录。

- Sheet1合并标题为 `A1:I1`；字段行 `A2:I2`；实验室记录 `A3:I26`，逐行转换，附 `Sheet1!A行:I行` 定位。
- 九列为序号、实验室名称、简介、地点、联系人、电话或邮箱、计划接收人数及条件、考核方式、科研成果及学生典型事迹。研究方向从原简介/条件原文保留，不额外编造一个“方向”值。
- 保留全部非空值、换行和单元格超链接，包括WPS自定义XML中同一单元格的多个富文本链接；没有访问这些外链。原表的“无”保持“无”，空单元格明确写“原表空白，未推断”。合并标题不展开成每行数据。
- 24条记录、226/226非空单元格转换；漏项0；Sheet2、Sheet3均为空。详细单元格对照见[`qinghe-conversion-audit.json`](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-conversion-audit.json)。
- 只保留官方已公开、用于资源对接的联系方式，未收集真实学生申请记录。未给联系人发邮件、打电话或测试邮箱。
- 已检查XLSX全部工作表、共享字符串（无未使用条目）、XML及关系属性、DOCX全部XML、删除/隐藏标记及嵌入项。报名表未发现已填写申请人记录。原件含Office编辑者/WPS自定义元数据，未在报告复述账号值；静态证据见verification-evidence.json。这不是通用隐私检测器，也不替代人工审核。
- 报名流程来自通知：选实验室→在当期截止前发报名表到该实验室邮箱→材料初选→面试或笔试。每条实验室文本重复注明本批次截止已过，人数和联系方式非实时确认结果。
- 转换器专用于这份已知布局；表头改变、出现公式或表外/隐藏表新增内容会停止并要求复核。本轮没有扩展公共 `DocumentParser` 的格式支持。

## 5. 结论与下一步

技术处理已完成：新快照留存、正文/表格转换、8份DTO、501片段原件映射、哈希与字符区间检查。独立内存BM25实际索引501/501片段，8个元数据查询及501个片段查询均受blocked门禁限制，四领域正式检索为0；未持久化正式索引。具体测试和命令见[交接说明](beta-policy-handoff.md)。

仍未完成：最终人工签核、院级年度歧义澄清、通则现行性确认、目标年级适用性确认、星火旧DOC正式转换、复试用表转换、实时资源联系确认。缺口逐项见[待确认清单](beta-policy-gaps.md)。

本次可交给组长审核，也可交王智洋做**离线格式/原件接收验收**；暂不能作为正式开放语料。组长逐份审核后，才由团队按统一流程形成 approved 包并通知下游索引。不要整体把8份复制到approved或批量改enabled。
