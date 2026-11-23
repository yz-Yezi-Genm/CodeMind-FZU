# 青禾计划 B8 两包待审核交接

本次按组长要求和林彦翔确认的B8结论，交付**R3、R4两个独立DocumentPackage，每包24片段，共48片段**。资料为2026—2027学年青禾计划原件的分类派生，不是新增48份官方资料。两包全部`blocked`、`temporal_notes.human_approved=false`，未写approved，不代表A4正式验收已通过。

B8依据：[PR #45 中的S4对接确认及业务规则](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/45/files)，核对版本`265de18`，确认单第9节B8及六类分类：R3/R4按`category_name`双向隔离；原表序号作唯一标识、保留行号，同名不合并，“无”按缺失处理。本次仅使用该确认结论，不合入其他成员未合并代码或修改公共接口。

## 1. 本轮唯一接收入口

[待审核manifest](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/manifest.json)

| 项目 | R3 | R4 |
|---|---|---|
| 文件 | [qinghe-r3.json](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/qinghe-r3.json) | [qinghe-r4.json](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/qinghe-r4.json) |
| `category_name` | 实验室与科研团队 | 研究方向与公开介绍 |
| `record_code` | 计算机学院-2026-青禾计划-R3 | 计算机学院-2026-青禾计划-R4 |
| `version_no` | beta-b8-2026-11-23-1 | beta-b8-2026-11-23-1 |
| `business_direction_codes` | 仅COLLEGE_RESOURCES | 仅COLLEGE_RESOURCES |
| 片段 | 24，原序号1—24 | 24，原序号1—24 |
| 原字段 | A序号、B名称、D地点、E联系人、F电话/邮箱、G人数/接收条件、H考核方式 | A序号、B名称、C简介/研究方向、I成果/学生典型事迹/主页 |
| 招募流程 | 每行带原通知的本批报名、初选及面试/笔试流程，附通知XPath | 不注入报名流程，不承担招募资格判断 |
| `deadline_on` | 2026-10-31，原文“10月31日前”未给时刻 | null，本包不是报名通知 |
| 时效 | expired：该批次已截止 | historical：保留2026-10发布时的介绍，不推定现在仍相同 |
| 开放/人工审核 | blocked / false | blocked / false |

每行一个片段，不为了长度任意截掉字段。原序号14、15、24中的EDA记录独立保留，序号8、18的空间数据挖掘记录也不合并。电话/邮箱只是原官方公开联系渠道，未测试当前可达；人数为当时计划，不是实时余量。R4中的成果/去向是原表陈述，不保证个人未来结果。

原8包/501片段批次继续作为核验基线，保持原样。其中旧`beta-2026-11-23/qinghe.json`的35片段混合包**不再作为S4 A4的交接包**；后续组长审核S4时使用本页的两包，不同时开放旧混合包与这两包。其他7份资料不受本次派生影响。全局业务方向字典、44条原登记不修改。

## 2. R3适用范围及缺失规则

`applicability_raw`采用已确认中文五键：

```json
{
  "适用年级": "全体本科生；具体实验室另有接收条件",
  "适用专业": null,
  "适用对象": "计算机与大数据学院（软件学院）本科生；具体实验室按原行条件",
  "学院": "福州大学计算机与大数据学院（软件学院）",
  "适用届别": null
}
```

“全体本科生”范围仅为本学院，不能覆盖外院或忽略单行条件；适用专业未独立列明，不补成“不限”；2026—2027学年是批次，不是2027届毕业生。每行原文的年级、能力等条件仍保留，不能仅凭包级范围断言“大二一定能进”。

R4也保留这五键和原表背景，但其公开介绍范围不能被解释为个人准入资格。两个包的`temporal_notes`保存父资料编号/版本、S4分类、学年、缺失处理与使用限制；原始登记仍保留于`import_snapshot`，不会冒充新的审核结论。

原表“无”或空白转为“未提供（原表为‘无’或空白；不能推断）”，不当作经核实的否定值。例：原行26的D26地点、H26考核方式为“无”，R3明确标记缺失；原值仍在映射与原件中。

## 3. 官方来源与逐行追溯

- 发布单位：福州大学计算机与大数据学院（软件学院）。
- 发布日期：2026-10-16。
- 官方通知：[2026—2027学年青禾计划本科生进实验室报名通知](https://ccds.fzu.edu.cn/info/1160/12008.htm)。
- 原始XLSX：[计算机与大数据学院（软件学院）本科生进实验室需求一览表.xlsx](https://ccds.fzu.edu.cn/system/_content/download.jsp?urltype=news.DownloadAttachUrl&owner=1776636274&wbfileid=18557344)。
- 原件SHA-256：`233ec737ae79b7b366202816211fb6ee5575b75fe241f9ef88a8d79fc0bc3fed`。
- 原通知、XLSX、空白报名DOCX全部通过`ParsedFile`关联，文件角色/来源/原名/SHA保留；转换Markdown为`curated`，表示按已知字段分类整理，不代表审核通过。
- [R3转换正文](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/texts/qinghe-r3.md)、[R4转换正文](../../../knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/texts/qinghe-r4.md)。
- [48片段原件映射](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-b8-source-map.json)：每条记录原序号、Sheet1行区间、所用列、原值及SHA、缺失标志、链接、转换稿字符区间；R3另有通知原XPath及SHA。

实验室序号N对应Sheet1第N+2行，每包`chunk_no=N`；`original_file_key`指向原XLSX，`original_locator=Sheet1!A行:I行`，映射另列实际所选列，不能误认为每包都含原表九列。

构建前先执行原批次的完整校验/原件重提取，再直接读取XLSX与官方通知生成两包。检查时再次从原件生成预期包，逐字段对照候选JSON、全文件清单/SHA、Markdown、48条映射和manifest，不靠多个已生成文件互相比对认定真实。

## 4. 复现与验收边界

在现有审核环境安装`knowledge_base/processing/requirements-beta-review.txt`后，于仓库根目录执行：

```powershell
python -m knowledge_base.processing.build_qinghe_b8
python -m knowledge_base.processing.build_qinghe_b8 --check
python -m unittest knowledge_base.processing.test_qinghe_b8 -v
```

[B8校验报告](qinghe-b8-validation-report.json)验证两包技术索引各24条，8包基线照常通过，B8真实version/chunk元数据/片段查询全部被blocked门禁隔离，正式检索为空。测试覆盖分类、截止日、中文五键、24个原序号、同名记录、字段分流、缺失标记、流程来源、篡改/丢片段、误设置人工审核、原件关联与构建前失败不写入。

技术测试日志见[qinghe-b8-tests.txt](qinghe-b8-tests.txt)，结果汇总见[qinghe-b8-test-results.json](qinghe-b8-test-results.json)。这些不代表A4正式问答验收；目前没有真实已审核政策的正向问答或Qwen验收记录。

组长下一步逐包核对原件、切片和元数据并最终签核，再按团队流程交王智洋加载正式approved资料，供规则/Agent进行A4真实验收。本次不代替组长签核，不修改规则模块，不提前启用资料。

可转发：

> 青禾已按B8拆成R3“实验室与科研团队”和R4“研究方向与公开介绍”两个独立待审核包，各24片段，共48。R3已补2026-10-31截止日及中文五键适用范围，同名记录按原序号分别保留，“无”按缺失处理。入口为pending-review/qinghe-b8-2026-11-23/manifest.json，原件、行列及通知定位均有映射。两包全部blocked、human_approved=false，请核验后再最终签核；旧35片段混合包仅留作基线，不用于本轮A4交接。
