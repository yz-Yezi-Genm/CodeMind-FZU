# Beta 候选资料统一人工审核清单

更新日期：2026-11-25。当前 main 基线：`a3ffdd046c10fb7af647651c8358eee8d8dde948`，已含 #45、#51、#49。#41仅提交候选资料技术成果，合并与最终人工签核分别进行；原先#44→#41→#45顺序已取消。

## 1. 唯一统计与放行口径

本轮拟交接 **9个DocumentPackage、514个片段**：S1两包310、S2三包127、S3两包29、S4两包48。计算方式为原8包501减旧青禾35，加B8两包48。是同批来源的处理包，不是新增9份独立官方政策或已通过9份审核。

旧`beta-2026-11-23/qinghe.json`及其35片段继续作原件追溯/重提取基线，**不纳入本清单，不与R3/R4重复入库**。其他原Alpha版本和44条登记也不计入本轮514片段。

9个候选包JSON仍维持`retrieval_status=blocked`、`temporal_notes.human_approved=false`；正式approved包数0、正式检索命中0。人工签核结果以本清单及人工审核台账为准；限定范围签核通过不自动改变候选包标记，也不等于正式问答放行。必要技术修复、复验及后续统一放行完成前，所有候选包继续blocked。`source_verification_status=verified`及技术索引通过不代替人工签核。

`version_id`不是新加的DTO字段，使用合并后LocalBM25Retriever实际`index_document()`生成的UUID；复现脚本逐包验证，见[9包索引与隔离报告](beta-policy-handoff-validation.json)。原件位置、转换稿和包路径均相对仓库根，需一起接收。

## 2. 9包审核总表

| 场景 | 资料 | 片段 | 时效 | 建议审核优先级 | 人工审核结果 | 审核人 | 审核日期 |
|---|---|---:|---|---|---|---|---|
| S1 | [2026竞赛级别认定通知及三份附件](#competition) | 224 | uncertain | P0 | 待审核 | 待填写 | 待填写 |
| S1 | [创新创业实践与素质拓展学分认定办法](#innovation) | 86 | uncertain | P0 | 待审核 | 待填写 | 待填写 |
| S2 | [2026本科生奖学金评定管理办法](#scholarship) | 59 | uncertain | P0 | 待审核 | 待填写 | 待填写 |
| S2 | [计算机学院各类院级奖学金通知](#college-scholarship) | 33 | uncertain | P1（年度确认后） | 待审核 | 待填写 | 待填写 |
| S2 | [2026星火奖教奖学金通知](#xinghuo) | 35 | expired | P1 | 待审核 | 待填写 | 待填写 |
| S3 | [2027届本科推免推荐资格方案](#recommendation) | 20 | expired | P0（先审无争议条款） | 待审核 | 待填写 | 待填写 |
| S3 | [2027年接收直博生及硕士推免复试方案](#retest) | 9 | expired | P1 | 待审核 | 待填写 | 待填写 |
| S4 | [青禾R3：实验室与科研团队](#qinghe-r3) | 24 | expired | P0 | 组长限定范围签核通过（技术修复前不释放） | 组长 | 2026-11-25 |
| S4 | [青禾R4：研究方向与公开介绍](#qinghe-r4) | 24 | historical | P0 | 辅助审核完成，待组长决定 | 待填写 | 待填写 |

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
- 当前时效：`uncertain`；截止日：`未单列`。判断依据及待人工确认问题：2026认定结果本身可追溯；缺少截至2026-11-24覆盖后续通知/替代目录的版本核查记录，以及目录205行、合并区域、脚注的逐项人工语义确认。未发现替代版本不等于证明现行。
- 适用范围（保留包内实际值）：适用年级：参加相关竞赛并申请学分认定的本科生，含大一至大三；适用专业：全校相关本科专业；适用对象：竞赛学分认定申请者；教师绩效条文不作为学生问答范围。
- 拟允许回答范围（须审核后）：在最终审核明确时效后，按2026目录查询竞赛名称、级别和对应附件，注明年度及认定用途。
- 禁止回答范围：未经确认的现行认定结论；直接转换成综测加分、奖学金等级或保证个人学分/认定通过。
- 建议优先级：P0。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

<a id="innovation"></a>

### 创新创业实践与素质拓展学分认定办法（S1，86片段）

- `record_code`：`福大-2024-创新创业学分认定`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`e77bc47b-d65f-5056-aafd-56db7d294a10`。
- 发布单位：福州大学教务处；发布日期：2024-05-30。
- 官方正文：[来源页面](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1095&wbnewsid=12993)。
- 资料包：[innovation.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/innovation.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/innovation.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [innovation.html](../../../knowledge_base/processing/policy-review/2026-11-23/innovation.html)；[官方下载/来源](https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1095&wbnewsid=12993)。
- 当前时效：`uncertain`；截止日：`未单列`。判断依据及待人工确认问题：第27条有2024-09-01施行及旧版废止/过渡安排，但缺少后续修订或替代文件的确认、目标年级培养方案和学院实施口径；项目原始分与最终学分需分开。
- 适用范围（保留包内实际值）：适用年级：大一至大三及其他适用本科生；适用专业：按通知或培养方案适用；适用对象：本科生；过渡说明：第27条：2016办法待2020级毕业后自动废止，2022办法废止；具体年级和培养方案待人工确认。
- 拟允许回答范围（须审核后）：审核后的具体条款、材料与认定流程，以及明确年级/目录下的规则解释；保留原始分与学分的区别。
- 禁止回答范围：仅凭历史办法判所有年级均适用；将原始分、学分、综测分互换；未核实目录就自动认定。
- 建议优先级：P0。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

<a id="scholarship"></a>

### 2026本科生奖学金评定管理办法（S2，59片段）

- `record_code`：`福大-2026-本科奖学金`；`version_no`：`beta-review-2026-11-23-1`。
- **version_id**：`c8f6bae5-c663-5a69-a2f8-df8642b62e05`。
- 发布单位：福州大学；发布日期：2026-05-18。
- 官方正文：[来源页面](https://stuic.fzu.edu.cn/info/1032/6937.htm)。
- 资料包：[scholarship.json](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/scholarship.json)；转换稿：[Markdown](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/texts/scholarship.md)。
- 原件及其官方地址（每份SHA均在包的ParsedFile中）：
  - [scholarship.html](../../../knowledge_base/processing/policy-review/2026-11-23/scholarship.html)；[官方下载/来源](https://stuic.fzu.edu.cn/info/1032/6937.htm)。
- 当前时效：`uncertain`；截止日：`未单列`。判断依据及待人工确认问题：正文第14条载公布施行及2024办法废止，当前保留列表仍收录；但缺少后续修订/替代通知的完整核查及最终现行性确认，金额、比例、排除条件与专项细则仍需人工核对。
- 适用范围（保留包内实际值）：适用年级：全体本科生；适用专业：；适用对象：全日制在校本科生。
- 拟允许回答范围（须审核后）：审核确认时效后解释校级通则中明确列出的奖项、条件、金额/比例和评审流程，注明具体条款。
- 禁止回答范围：通则替代院级/国家/社会专项细则；根据单一成绩承诺个人获奖；未经确认的当前金额或名额。
- 建议优先级：P0。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

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
- 当前时效：`uncertain`；截止日：`未单列`。判断依据及待人工确认问题：网页发布2026-04-13，正文及申请表写2025年度，统计期还涉及2025.03—2026.02及2024—2025学年。缺学院官方对评奖年度的解释、奖项别称澄清及对应本科/研究生专项适用确认；不得自行改年度。
- 适用范围（保留包内实际值）：学院：福州大学计算机与大数据学院；对象：正式学籍、在读全日制本科生和研究生，各专项另有限制；年度歧义：网页发布2026-04-13；首段2025年度；待学院确认，不自行纠正；学业类：原文10名本科生。
- 拟允许回答范围（须审核后）：经审核仅复述该通知中无争议、带原年度限定的奖项及材料/流程，按具体专项和学生类型说明。
- 禁止回答范围：把2025自动纠正成2026或下一年度；不同奖项、本科与研究生条件混用；宣称现仍可申请。
- 建议优先级：P1（年度确认后）。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

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
- 当前时效：`expired`；截止日：`2026-04-26`。判断依据及待人工确认问题：通知2026-04-20，2026-04-26前报送已过；需人工确认2026沿用2025细则的准确范围。RAR隐私检查已完成，但旧DOC未新增为正式政策正文，不承诺附件填写指导。
- 适用范围（保留包内实际值）：学院：福州大学计算机与大数据学院；学生对象：正式学籍、在读全日制本科生和研究生；教师条款：全文为完整性保留，学生问答不得引用教师资格、名额或金额；年度：2026年沿用2025细则，申请期已过。
- 拟允许回答范围（须审核后）：审核后的2026历史通知、申请流程及原文明确的学生条款；对教师章节明确排除学生适用。
- 禁止回答范围：当前申请开放、下一年度沿用；把教师条件/金额/人数套给学生；完整旧DOC表格填写指导。
- 建议优先级：P1。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

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
- 当前时效：`expired`；截止日：`2026-09-09`。判断依据及待人工确认问题：2026-09-09 21:00申报截止；第4页计分表仍需最终逐行人工签核，志愿服务0—30/30—60/60—100小时及以上的30、60小时边界/原文符号存在争议，须官方解释；不自行选择包含端点或算分。
- 适用范围（保留包内实际值）：适用年级：2027届应届本科毕业生；大一至大三仅升学准备参考；适用专业：计算机科学与技术（含实验班）、数据科学与大数据技术、人工智能、信息安全、软件工程，以本届方案范围为准；适用对象：学院申请取得本科推免推荐资格的学生；目标届别：2027届；使用限制：不适用于下一届；不可回答当前报名开放。
- 拟允许回答范围（须审核后）：仅2027届历史资格、材料、流程及已核定的无争议条款；低年级仅作阶段准备参考，注明截止已过。
- 禁止回答范围：下一届现行资格、当前申请开放；对志愿服务争议区间自动算分、补标点或承诺录取/推荐。
- 建议优先级：P0（先审无争议条款）。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

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
- 当前时效：`expired`；截止日：`2026-09-19`。判断依据及待人工确认问题：2026-09-19 11:00首批预报名导出、9月20日16:00资格材料及9月22日复试均已过；需确认后续批次和学位/专业具体条件。PDF列示用表ZIP未转换，不能宣称完整附件指导。
- 适用范围（保留包内实际值）：对象：已取得所在学校推免资格的校内外优秀应届本科毕业生；申请硕士/直博另看细则；年度：2027年接收推免；2026年9月实施；限制：不是本科推荐资格办法；不适用于下一届或当前开放判断。
- 拟允许回答范围（须审核后）：审核后的2027年首批接收复试历史流程、材料和方案正文，分别说明硕士/直博；要求已取得所在学校推免资格。
- 禁止回答范围：当作本科取得推荐资格办法；当前或下一届仍开放；用历史计划保证当前名额；未转换表格的填写指导。
- 建议优先级：P1。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

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
- 当前时效：`historical`；截止日：`未单列`。判断依据及待人工确认问题：仅有2026-10发布时的官方附件介绍，未取得截至2026-11-24的研究方向/成果介绍续存核验，故historical，不改为current。需逐行审核简介、成果、原主页链接及缺失值。
- 适用范围（保留包内实际值）：适用年级：全体本科生；具体实验室另有接收条件；适用专业：未明确（不推断）；适用对象：计算机与大数据学院（软件学院）本科生；具体实验室按原行条件；学院：福州大学计算机与大数据学院（软件学院）；适用届别：未明确（不推断）。
- 拟允许回答范围（须审核后）：审核后注明2026年附件历史出处，介绍当时研究内容、成果/学生事迹；同名记录按原序号区分。
- 禁止回答范围：证明当前研究方向未变化；R4回答R3招募/个人资格/名额；保证成果或学生未来发展；把原链接当当前核验。
- 建议优先级：P0。
- 辅助审核日期：2026-11-25；组长签核：待决定。独立结构核验24/24行映射通过，原件哈希匹配；详细异常与来源核验见[人工审核台账](beta-human-review-ledger.md)。
- 重点待确认：第8条I列实际为个人简介；第16/17条共用同一教师主页且不足以单独支撑两个团队全部方向；第18条外部HTTP链接访问超时；第22条为学生兴趣团队且官网未能访问；第23条依托医工交叉研究院。上述内容如获历史范围签核，必须按原表归属和历史时点表述，不得推断当前状态。
- **人工审核结果：待审核；审核人：待填写；审核日期：待填写。**

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
