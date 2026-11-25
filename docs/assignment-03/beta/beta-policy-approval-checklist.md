# Beta 候选资料统一人工审核清单

更新日期：2026-11-25。当前 main 基线：`a3ffdd046c10fb7af647651c8358eee8d8dde948`，已含 #45、#51、#49。#41仅提交候选资料技术成果，合并与最终人工签核分别进行；原先#44→#41→#45顺序已取消。

## 1. 唯一统计与放行口径

本轮拟交接 **9个DocumentPackage、514个片段**：S1两包310、S2三包127、S3两包29、S4两包48。计算方式为原8包501减旧青禾35，加B8两包48。是同批来源的处理包，不是新增9份独立官方政策或已通过9份审核。

旧`beta-2026-11-23/qinghe.json`及其35片段继续作原件追溯/重提取基线，**不纳入本清单，不与R3/R4重复入库**。其他原Alpha版本和44条登记也不计入本轮514片段。

9个候选包均维持`retrieval_status=blocked`；其中6个资料包已同步登记`temporal_notes.human_approved=true`（仅限定范围人工签核），其余3个资料包仍为`human_approved=false`（第04份推免推荐资格待业务规则修复与复审；青禾R3/R4的包级签核标记尚未同步，且R3仍有技术修复项）。正式approved包数0、正式检索命中0。限定范围签核通过不等于正式问答放行；必要技术修复、复验及后续统一放行完成前，所有候选包继续blocked。`source_verification_status=verified`及技术索引通过不代替人工签核。

`version_id`不是新加的DTO字段，使用合并后LocalBM25Retriever实际`index_document()`生成的UUID；复现脚本逐包验证，见[9包索引与隔离报告](beta-policy-handoff-validation.json)。原件位置、转换稿和包路径均相对仓库根，需一起接收。

## 2. 9包审核总表

| 场景 | 资料 | 片段 | 时效 | 建议审核优先级 | 人工审核结果 | 审核人 | 审核日期 |
|---|---|---:|---|---|---|---|---|
| S1 | [2026竞赛级别认定通知及三份附件](#competition) | 224 | current | P0 | 通过（限定范围；检索仍blocked） | 组长 | 2026-11-24 |
| S1 | [创新创业实践与素质拓展学分认定办法](#innovation) | 86 | current | P0 | 通过（限定范围；检索仍blocked） | 组长 | 2026-11-24 |
| S2 | [2026本科生奖学金评定管理办法](#scholarship) | 59 | current | P0 | 通过（限定范围；检索仍blocked） | 组长 | 2026-11-24 |
| S2 | [计算机学院各类院级奖学金通知](#college-scholarship) | 33 | expired | P1（历史资料） | 通过（限定范围；检索仍blocked） | 组长 | 2026-11-25 |
| S2 | [2026星火奖教奖学金通知](#xinghuo) | 35 | expired | P1 | 通过（限定范围；检索仍blocked） | 组长 | 2026-11-25 |
| S3 | [2027届本科推免推荐资格方案](#recommendation) | 20 | expired | P0（先审无争议条款） | 暂缓签核（PDF版式复核通过；志愿服务计分/Agent门禁待修） | 组长 | 2026-11-25 |
| S3 | [2027年接收直博生及硕士推免复试方案](#retest) | 9 | expired | P1 | 通过（限定范围；检索仍blocked） | 组长 | 2026-11-25 |
| S4 | [青禾R3：实验室与科研团队](#qinghe-r3) | 24 | expired | P0 | 组长限定范围签核通过（技术修复前不释放） | 组长 | 2026-11-25 |
| S4 | [青禾R4：研究方向与公开介绍](#qinghe-r4) | 24 | historical | P0 | 组长限定范围历史审核通过 | 组长 | 2026-11-25 |

P0表示优先送审，不表示通过；有争议的年度、现行性或计分即使P0也不先放行。人工审核记录仅由组长或经明确授权的审核人填写，不能用AI核验日期代替审核日期。

## 3. 逐包审核卡

<a id="competition"></a>

### 2026竞赛级别认定通知及三份附件（S1，224片段）

- `record_code`：`福大-2026-竞赛项目级别认定`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`92e414c2-6b8c-5f69-b073-05921b0faa55`。
- 发布单位：福州大学教务处；发布日期：2026-03-06。
- 官方正文：[来源页面](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbnewsid=14534&wbtreeid=1039)。
- 资料包：[competition.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/competition.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/competition.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [福州大学大学生学科竞赛级别认定（直接认定）一览表（2026年版）.docx](../../../knowledge_base/processing/policy-review/2026-11-23/competition-attachment-1.docx)；[官方下载/来源](https://jwch.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1744984858&wbfileid=16766605)。
  - [福州大学大学生学科竞赛级别认定一览表（2026版）.docx](../../../knowledge_base/processing/policy-review/2026-11-23/competition-attachment-2.docx)；[官方下载/来源](https://jwch.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1744984858&wbfileid=16766606)。
  - [福州大学大学生体育类竞赛级别认定一览表（2026版）.docx](../../../knowledge_base/processing/policy-review/2026-11-23/competition-attachment-3.docx)；[官方下载/来源](https://jwch.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1744984858&wbfileid=16766607)。
  - [competition.html](../../../knowledge_base/processing/policy-review/2026-11-23/competition.html)；[官方下载/来源](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbnewsid=14534&wbtreeid=1039)。
- 当前时效：`current`；组长于2026-11-24已审核通过2026版目录的限定范围现行性。跨年度个人认定及计算机学院具体过渡口径仍未核实，遇此类问题须追问或拒答。
- 适用范围（保留包内实际值）：适用年级：参加相关竞赛并申请学分认定的本科生，含大一至大三；适用专业：全校相关本科专业；适用对象：竞赛学分认定申请者；教师绩效条文不作为学生问答范围。
- 已审核允许回答范围（正式检索开放后方可使用）：在最终审核明确时效后，按2026目录查询竞赛名称、级别和对应附件，注明年度及认定用途。
- 禁止回答范围：未经确认的现行认定结论；直接转换成综测加分、奖学金等级或保证个人学分/认定通过。
- 建议优先级：P0。
- **人工审核结果：限定范围审核通过；审核人：组长；审核日期：2026-11-24。** 认可2026版目录current时效及上述限制；205条竞赛数据和三份附件已按本轮人工复核结论签核。候选包与manifest登记`current / human_approved=true`，`retrieval_status=blocked`保持不变。

<a id="innovation"></a>

### 创新创业实践与素质拓展学分认定办法（S1，86片段）

- `record_code`：`福大-2024-创新创业学分认定`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`e77bc47b-d65f-5056-aafd-56db7d294a10`。
- 发布单位：福州大学教务处；发布日期：2024-05-30。
- 官方正文：[来源页面](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1095&wbnewsid=12993)。
- 资料包：[innovation.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/innovation.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/innovation.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [innovation.html](../../../knowledge_base/processing/policy-review/2026-11-23/innovation.html)；[官方下载/来源](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1095&wbnewsid=12993)。
- 当前时效：`current`；组长于2026-11-24认可校级通用办法的current时效。具体年级、专业、培养方案、竞赛目录和学院实施口径仍须分别核验，不推断所有本科生或所有项目均可直接适用。
- 适用范围（保留包内实际值）：适用年级：大一至大三及其他适用本科生；适用专业：按通知或培养方案适用；适用对象：本科生；过渡说明：第27条：2016办法待2020级毕业后自动废止，2022办法废止；具体年级和培养方案待人工确认。
- 已审核允许回答范围（正式检索开放后方可使用）：审核后的具体条款、材料与认定流程，以及明确年级/目录下的规则解释；保留原始分与学分的区别。
- 禁止回答范围：仅凭历史办法判所有年级均适用；将原始分、学分、综测分互换；未核实目录就自动认定。
- 建议优先级：P0。
- **人工审核结果：限定范围审核通过；审核人：组长；审核日期：2026-11-24。** 认可校级通用办法current时效及上述限制；原始分、创新学分与综测分的边界继续保留。候选包与manifest登记`current / human_approved=true`，`retrieval_status=blocked`保持不变。

<a id="scholarship"></a>

### 2026本科生奖学金评定管理办法（S2，59片段）

- `record_code`：`福大-2026-本科奖学金`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`c8f6bae5-c663-5a69-a2f8-df8642b62e05`。
- 发布单位：福州大学；发布日期：2026-05-18。
- 官方正文：[来源页面](https://stuic.fzu.edu.cn/info/1032/6937.htm)。
- 资料包：[scholarship.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/scholarship.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/scholarship.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [scholarship.html](../../../knowledge_base/processing/policy-review/2026-11-23/scholarship.html)；[官方下载/来源](https://stuic.fzu.edu.cn/info/1032/6937.htm)。
- 当前时效：`current`；组长于2026-11-24认可福大学〔2026〕23号校级通则的current时效。具体专项、院级细则、实时名额和申报开放状态不由本通则单独证明。
- 适用范围（保留包内实际值）：适用年级：全体本科生；适用专业：；适用对象：全日制在校本科生。
- 已审核允许回答范围（正式检索开放后方可使用）：审核确认时效后解释校级通则中明确列出的奖项、条件、金额/比例和评审流程，注明具体条款。
- 禁止回答范围：通则替代院级/国家/社会专项细则；根据单一成绩承诺个人获奖；未经确认的当前金额或名额。
- 建议优先级：P0。
- **人工审核结果：限定范围审核通过；审核人：组长；审核日期：2026-11-24。** 认可current时效及上述限定回答范围。候选包与manifest登记`current / human_approved=true`，`retrieval_status=blocked`保持不变。

<a id="college-scholarship"></a>

### 计算机学院各类院级奖学金通知（S2，33片段）

- `record_code`：`计算机学院-2026-院级奖学金`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`d04c3928-f9e5-5c43-95d5-9e82958454b0`。
- 发布单位：福州大学计算机与大数据学院（软件学院）；发布日期：2026-04-13。
- 官方正文：[来源页面](https://ccds.fzu.edu.cn/info/1165/11707.htm)。
- 资料包：[college-scholarship.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/college-scholarship.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/college-scholarship.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [2026年计算机与大数据学院（软件学院）院级奖学金汇总表.zip](../../../knowledge_base/processing/policy-review/2026-11-19/college-attachments.zip)；[官方下载/来源](https://ccds.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1776636274&wbfileid=18248426)。
  - [college-scholarship.html](../../../knowledge_base/processing/policy-review/2026-11-23/college-scholarship.html)；[官方下载/来源](https://ccds.fzu.edu.cn/info/1165/11707.htm)。
- 当前包状态：`expired / blocked`。组长已于2026-11-25人工审核通过限定范围历史资料；确认2026评选周期，各专项原文中的`2025年度`、`2024-2025学年`、`上学年`、`评选年度`等业绩参考期间分别保留，不强行归一。`human_approved=true`，但`retrieval_status=blocked`，暂不开放正式检索。
- 适用范围（保留包内实际值）：学院：福州大学计算机与大数据学院；对象：正式学籍、在读全日制本科生和研究生，各专项另有限制；评选周期：后续2026官方结果公示已确认2026周期；业绩参考期间：原文分项出现2025年度、2024-2025学年及上学年等口径；学业类：原文10名本科生。
- 已审核允许范围（正式检索开放后方可使用）：仅作为2026评选周期历史资料，复述该通知中有原文依据、带明确专项及业绩参考期间限定的奖项、条件和流程；按具体专项和学生类型分别说明。当前仍blocked，不进入生产检索。
- 禁止回答范围：把不同业绩统计期间合并或自动替换；把教师奖教金与学生奖学金混为一谈；不同奖项、本科与研究生条件混用；宣称现仍可申请。
- 官方交叉证据：[2026年评审结果公示](https://ccds.fzu.edu.cn/info/1165/11723.htm)确认2026周期及五个奖项全称；[2026年星火奖教奖学金通知](https://ccds.fzu.edu.cn/info/1119/11710.htm)说明2026年沿用2025年评选细则，并区分教师奖教金与学生奖学金。附件边界：本通知ZIP含四类学生汇总表；独立`xinghuo-forms.rar`属于第07份资料，不混入本包。
- **人工审核结果：限定范围历史审核通过；审核人：组长；审核日期：2026-11-25。** 组长认可2026评选周期及各专项原文业绩参考期间，认可奖项名称处理。候选包和manifest已登记`timeliness_verification_status=expired`、`human_approved=true`；`retrieval_status=blocked`保持不变。本次签核不等于正式检索放行。

<a id="xinghuo"></a>

### 2026星火奖教奖学金通知（S2，35片段）

- `record_code`：`计算机学院-2026-星火奖学金`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`908442f5-eaed-59bf-a613-c79f143994c4`。
- 发布单位：福州大学计算机与大数据学院（软件学院）；发布日期：2026-04-20。
- 官方正文：[来源页面](https://ccds.fzu.edu.cn/info/1119/11710.htm)。
- 资料包：[xinghuo.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/xinghuo.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/xinghuo.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [附件：《“星火奖教奖学金”申请表》《“星火奖教奖学金”汇总表》](../../../knowledge_base/processing/policy-review/2026-11-19/xinghuo-forms.rar)；[官方下载/来源](https://ccds.fzu.edu.cn/2026nianxinghuojiangjiaojinshenqingbiao.rar)。
  - [xinghuo.html](../../../knowledge_base/processing/policy-review/2026-11-23/xinghuo.html)；[官方下载/来源](https://ccds.fzu.edu.cn/info/1119/11710.htm)。
- 当前时效：`expired`；截止日：`2026-04-26`。组长已确认仅作为2026年度历史规则参考；教师与学生条款严格隔离，学生专用申请表、团队资格及参评年度统计口径均不作推断。
- 适用范围（保留包内实际值）：学院：福州大学计算机与大数据学院；学生对象：正式学籍、在读全日制本科生和研究生；教师条款：全文为完整性保留，学生问答不得引用教师资格、名额或金额；年度：2026年沿用2025细则，申请期已过。
- 已审核允许回答范围（正式检索开放后方可使用）：审核后的2026历史通知、申请流程及原文明确的学生条款；对教师章节明确排除学生适用。
- 禁止回答范围：当前申请开放、下一年度沿用；把教师条件/金额/人数套给学生；完整旧DOC表格填写指导。
- 建议优先级：P1。
- **人工审核结果：限定范围历史审核通过；审核人：组长；审核日期：2026-11-25。** 仅限通知正文已核实的2026年规则，教师与学生条款严格隔离；学生表格、团队资格、参评年度统计口径不作推断。候选包与manifest登记`expired / human_approved=true`，`retrieval_status=blocked`保持不变。

<a id="recommendation"></a>

### 2027届本科推免推荐资格方案（S3，20片段）

- `record_code`：`计算机学院-2027-推免资格推荐`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`cfcfa918-e8f5-50a7-a1bb-fbff63862581`。
- 发布单位：计算机与大数据学院（软件学院）；发布日期：2026-09-08。
- 官方正文：[来源页面](https://ccds.fzu.edu.cn/info/1119/11932.htm)。
- 资料包：[recommendation.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/recommendation.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/recommendation.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [recommendation-pdf.pdf](../../../knowledge_base/processing/policy-review/2026-11-23/recommendation-pdf.pdf)；[官方下载/来源](https://ccds.fzu.edu.cn/__local/2/65/3C/D04CE20168D8D7DDFDA27D48782_915BB2AE_383A0.pdf)。
  - [recommendation.html](../../../knowledge_base/processing/policy-review/2026-11-23/recommendation.html)；[官方下载/来源](https://ccds.fzu.edu.cn/info/1119/11932.htm)。
- 当前时效：`expired`；申报截止：`2026-09-09 21:00`；综合测评材料截止：`2026-09-08 12:00`。仅作为2027届历史方案，不适用于下一届，不回答当前报名开放。
- 适用范围（保留包内实际值）：适用年级：2027届应届本科毕业生；大一至大三仅升学准备参考；适用专业：计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程，以本届方案范围为准；适用对象：学院申请取得本科推免推荐资格的学生；目标届别：2027届；使用限制：不适用于下一届；不可回答当前报名开放。
- PDF第4页版式辅助复核（2026-11-25）：原件SHA-256 `39e96e8a22588c1b1b1d8fed10144df40df417b54a64ed1278395c6f85ed8fa7`与既有版式核验PDF一致，页面图像SHA-256 `39389afd6e002a4d02a9f4cf40b5d8252c7d408b657bdbcd7f38472efb0d95c7`。竞赛表4列、8条数据行，国际级/国家级各4行，个人/集体分值列完整；论文表4列、4条数据行，类别和作者条件合并单元格完整；表下注及志愿服务、参军、国际组织实习条款均保留。**PDF版式问题已关闭。**本届第4页没有省部级/校级竞赛分值行，也没有知识产权表，不得从旧年度方案补入。
- 志愿服务原文保持不变：`0-30小时加原始分2分；30-60小时）加原始分4分，60-100小时及以上加原始分6分，不重复累加。`**组长确认的项目解释口径**：0≤h<30计2分（0小时也计2分）；30≤h<60计4分；h≥60计6分；不重复累加。30和60小时归入后一档；60小时及以上均为6分，不设100小时封顶。此为组长确认的项目解释，不宣称是官方文件明确写出的左闭右开区间。不得修改官方原件。第2页所列志愿服务成绩权重为总成绩的0.3%，与原始分分开回答。
- 其他文字问题：国际组织实习条款中的`《国家留学基金委与有关国际组织合作项目列表`缺少闭合书名号；保留原文，不推断文件或项目范围。
- Agent门禁辅助复核：公共加载/工作流门禁要求资料`retrieval_status=enabled`、来源核验通过及`human_approved=true`；当前候选包为`blocked`、`human_approved=false`，不会进入正式检索/Qwen。代码：[AgentWorkflow](../../../backend/services/agent_workflow.py)、[approved语料加载器](../../../backend/retrieval/alpha_corpus.py)。
- **尚未完成的专项门禁**：[业务规则](../../../backend/services/alpha_business_rules.py)中的`_check_recommendation()`目前只区分推荐资格方案与接收复试方案，没有对志愿服务原始分重叠区间做Qwen前拒答。现有[业务规则测试](../../../tests/test_alpha_business_rules.py)和[AgentWorkflow测试](../../../tests/test_agent_workflow_qwen.py)没有覆盖0、30、60、100及100小时以上的争议边界，也没有断言这类请求不调用Qwen。
- 放行前待完成：①完成确定性计分实现：0≤h<30计2分（含0小时）；30≤h<60计4分；h≥60计6分；不重复累加；②增加边界和多轮 AgentWorkflow 回归测试，至少覆盖0、1、29、30、31、59、60、61、100、200小时；③另测“志愿服务在综合测评中占多少权重”仍能回答0.3%，且不与原始分混淆；④确认报名流程、材料要求等非计分问题不被误拦。
- 拟允许回答范围（待组长最终决定）：仅2027届历史资格、材料、流程及已核实的无争议条款；低年级仅作阶段准备参考，明确截止已过。
- 禁止回答范围：下一届现行资格、当前申请开放；不得把组长项目解释伪称为官方原文；不得保证个人推免结果。
- **人工审核结果：暂缓签核；审核人：组长；审核日期：2026-11-25。**组长已确认志愿服务项目解释口径，但尚未完成代码实现和回归测试；第04份资料整体仍未签核、未放行。候选包和正式检索状态未修改。
<a id="retest"></a>

### 2027年接收直博生及硕士推免复试方案（S3，9片段）

- `record_code`：`计算机学院-2026-推免复试参考`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`22d8e751-93e5-5f81-88b2-8de460f9b009`。
- 发布单位：福州大学计算机与大数据学院（软件学院）；发布日期：2026-09-17。
- 官方正文：[来源页面](https://ccds.fzu.edu.cn/info/1138/11961.htm)。
- 资料包：[retest.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/retest.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/retest.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [retest.html](../../../knowledge_base/processing/policy-review/2026-11-23/retest.html)；[官方下载/来源](https://ccds.fzu.edu.cn/info/1138/11961.htm)。
  - [retest.pdf](../../../knowledge_base/processing/policy-review/2026-11-23/retest.pdf)；[官方下载/来源](https://ccds.fzu.edu.cn/__local/9/F5/B3/3C086BF8E9CE78EA45247803BC4_34362834_60F24.pdf)。
- 当前时效：`expired`；2027届接收推免复试的首批预报名与复试安排已过，仅作为该批次历史方案参考。不得据此判断当前开放、剩余名额或下一届规则；ZIP附件填写指导不在签核范围内。
- 适用范围（保留包内实际值）：对象：已取得所在学校推免资格的校内外优秀应届本科毕业生；申请硕士/直博另看细则；年度：2027年接收推免；2026年9月实施；限制：不是本科推荐资格办法；不适用于下一届或当前开放判断。
- 已审核允许回答范围（正式检索开放后方可使用）：审核后的2027年首批接收复试历史流程、材料和方案正文，分别说明硕士/直博；要求已取得所在学校推免资格。
- 禁止回答范围：当作本科取得推荐资格办法；当前或下一届仍开放；用历史计划保证当前名额；未转换表格的填写指导。
- 建议优先级：P1。
- **人工审核结果：限定范围历史审核通过；审核人：组长；审核日期：2026-11-25。** ZIP附件填写指导明确排除；候选包与manifest登记`expired / human_approved=true`，`retrieval_status=blocked`保持不变。

<a id="qinghe-r3"></a>

### 青禾R3：实验室与科研团队（S4，24片段）

- `record_code`：`计算机学院-2026-青禾计划-R3`；`version_no`：`beta-b8-2026-11-23-1`。
- **version_id**：`971a0297-6295-52d5-8efe-4cfd3e2f72db`。
- 发布单位：福州大学计算机与大数据学院（软件学院）；发布日期：2026-10-16。
- 官方正文：[来源页面](https://ccds.fzu.edu.cn/info/1160/12008.htm)。
- 资料包：[qinghe-r3.json](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/qinghe-r3.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/texts/qinghe-r3.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [计算机与大数据学院（软件学院）本科生进实验室需求一览表.xlsx](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-labs.xlsx)；[官方下载/来源](https://ccds.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1776636274&wbfileid=18557344)。
  - [计算机与大数据学院（软件学院）本科生进实验室报名表 .docx](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-registration.docx)；[官方下载/来源](https://ccds.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1776636274&wbfileid=18557343)。
  - [qinghe.html](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe.html)；[官方下载/来源](https://ccds.fzu.edu.cn/info/1160/12008.htm)。
- 当前时效：`expired`；截止日：`2026-10-31`。判断依据：通知2026-10-16、10月31日前报名，deadline_on=2026-10-31，已截止。组长已完成24条记录的限定范围历史签核；现联系人可达性、新批次、当前接收资格和余量均未核实。
- 适用范围（保留包内实际值）：适用年级：全体本科生；具体实验室另有接收条件；适用专业：未明确（不推断）；适用对象：计算机与大数据学院（软件学院）本科生；具体实验室按原行条件；学院：福州大学计算机与大数据学院（软件学院）；适用届别：未明确（不推断）。
- 已签核的允许回答范围：仅解释2026—2027学年该批次实验室名单、当时接收条件与报名流程，并明确已截止、仍须原行条件及选拔；24是附件记录数，同名不合并。
- 禁止回答范围：当前仍招募、当前个人可进/具备接收资格、实时剩余名额、联系方式仍有效；历史流程冒充现行规则。
- 建议优先级：P0。
- **人工审核结果：组长限定范围签核通过；审核人：组长；审核日期：2026-11-25。四处错误href修复并复验前，继续保持blocked，不正式释放。**

<a id="qinghe-r4"></a>

### 青禾R4：研究方向与公开介绍（S4，24片段）

- `record_code`：`计算机学院-2026-青禾计划-R4`；`version_no`：`beta-b8-2026-11-23-1`。
- **version_id**：`97e81dbb-1972-5798-90d6-fef650abd223`。
- 发布单位：福州大学计算机与大数据学院（软件学院）；发布日期：2026-10-16。
- 官方正文：[来源页面](https://ccds.fzu.edu.cn/info/1160/12008.htm)。
- 资料包：[qinghe-r4.json](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/qinghe-r4.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/texts/qinghe-r4.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [计算机与大数据学院（软件学院）本科生进实验室需求一览表.xlsx](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-labs.xlsx)；[官方下载/来源](https://ccds.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1776636274&wbfileid=18557344)。
  - [计算机与大数据学院（软件学院）本科生进实验室报名表 .docx](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-registration.docx)；[官方下载/来源](https://ccds.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1776636274&wbfileid=18557343)。
  - [qinghe.html](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe.html)；[官方下载/来源](https://ccds.fzu.edu.cn/info/1160/12008.htm)。
- 当前时效：`historical`；截止日：`未单列`。仅有2026-10发布时的官方附件介绍，未取得截至2026-11-25的完整续存核验，故保持historical，不改为current；24条简介、成果及链接已完成限定范围人工复核。
- 适用范围（保留包内实际值）：适用年级：全体本科生；具体实验室另有接收条件；适用专业：未明确（不推断）；适用对象：计算机与大数据学院（软件学院）本科生；具体实验室按原行条件；学院：福州大学计算机与大数据学院（软件学院）；适用届别：未明确（不推断）。
- 拟允许回答范围（须审核后）：审核后注明2026年附件历史出处，介绍当时研究内容、成果/学生事迹；同名记录按原序号区分。
- 禁止回答范围：证明当前研究方向未变化；R4回答R3招募/个人资格/名额；保证成果或学生未来发展；把原链接当当前核验。
- 建议优先级：P0。
- 辅助审核及组长签核日期：2026-11-25；独立结构核验24/24行映射通过，原件哈希匹配；详细异常与来源核验见[人工审核台账](beta-human-review-ledger.md)。
- 签核后必须保留的异常说明：第08条I列实际为个人简介；第16/17条共用同一教师主页且不足以单独支撑两个团队全部方向；第18条外部HTTP链接访问超时；第22条为学生兴趣团队且官网未能访问；第23条依托医工交叉研究院。必须按原表归属和历史时点表述，不得推断当前状态。
- **人工审核结果：组长限定范围历史审核通过；审核人：组长；审核日期：2026-11-25。**
- 组长明确限制：保留第08、16/17、18、22、23条异常说明；不得将R4作为当前研究方向或招生依据。签核仅适用于2026年10月官方附件的历史公开介绍，不代表正式检索放行。

## 4. 现行性与跨模块待协调

四份`uncertain`恰为S1竞赛目录、创新学分，以及S2校级通则、院级通知。已知施行条款、网页仍收录、没有查到新版，都不构成完整现行性确认；逐包缺失依据已列于上方，后续须补官方版本/适用记录及人工结论。院级年度歧义与推免志愿服务计分争议原样保留，不用解析器纠正政策。

合并版#45《business-rules.md》§7.5与真实资料存在以下差异，**交组长协调雷葭雨、林彦翔、吴诗莹**，本PR不改规则/Agent/测试预期：

| 用例 | #45当前验收预期 | 本轮真实资料 | 待协调边界 |
|---|---|---|---|
| S4-01 学院有哪些实验室 | answered / current_policy | R3 expired，R4 historical，仅2026附件24条记录 | 只能说明当时附件记录，不能承诺当前完整名单/24个独立实验室；是否以historical展示由工作流与规则统一 |
| S4-02 EDA研究什么 | answered / current_policy | R4 historical，原序号14/15/24同名不合并 | 应标历史出处，不证明目前方向未变；同名记录须按原序号、内容区分 |
| S4-03 我大二能进EDA吗 | answered / current_policy | R3 expired，虽面向本院本科生，仍有单行条件及选拔 | 不能证明当前招募或个人当前接收资格；只能解释当时条件与已截止事实，最终status/mode由组长协调 |

目前全部blocked，真实正式问答只能走证据不足，不用改`uncertain/expired/historical`为`current`制造验收成功。历史回答也要等人工签核、规则及工作流集成，不属于本次已完成验收。R4保留范围背景，不承担R3资格判断；联系方式是当时公开渠道，未检验当前可达。

#51要求Retriever异步`retrieve()`及同步`get_document_metadata()`/`get_parsed_chunk()`；当前候选DTO可由已有实现完整索引，两个查询必须对blocked返回None。技术索引数与正式命中数分开统计，不以空索引/随机ID证明隔离。没有修改公共契约或其他成员业务代码。

## 5. 送审、后续放行及验收边界

1. 组长复核本清单及技术记录后可合并#41；合并不表示人工审核、正式问答或A4验收通过。
2. 之后逐包核原件、完整性、时效、适用范围及回答边界，填写真实人工结果/人/日期。仍有争议的包继续blocked。
3. 正式资料由**单独放行PR**处理，仅审核通过者可按团队规则进入approved；届时需更新manifest包路径/审批标志并复验SHA，不能原样把pending-review入口改名使用，也不能新旧青禾重复放行。
4. 王智洋当前接收仓库及依赖原件做离线技术复验；只有组长通知已审核正式版本后，才做正式索引与真实命中验收。

本轮不补S4 R1/R2/R5/R6、不承担最终签核、不开放正式库、不执行真实Qwen或正式A4正向问答，不重构已通过的转换/拆包代码。[最新交接及测试](beta-policy-handoff.md)；[B8原件映射说明](qinghe-b8-handoff.md)。
