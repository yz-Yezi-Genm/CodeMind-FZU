# Beta 候选资料技术交接

更新日期：2026-11-24。PR：#41；分支：`feat/beta-policy-review`；已同步main基线`a3ffdd046c10fb7af647651c8358eee8d8dde948`，包含#45业务规则、#51 Retriever契约及#49运行稳定性。原先#44→#41→#45顺序已经取消，不再等待#44。

## 1. 审核入口及唯一统计

先看[统一人工审核清单](beta-policy-approval-checklist.md)：本轮拟交接**9包、514片段**，S1=310、S2=127、S3=29、S4=48。每包列出version_id、原件/官方地址、转换稿、时效依据、适用范围、待确认项、拟允许/禁止回答范围、优先级及待填写的真实人工结果/审核人/日期。

组成为原批次7个非青禾包加B8 R3/R4两包。旧8包/501片段批次保留作原件核验基线，旧青禾35片段混合包**不在本轮放行清单内**，不可与新两包重复正式加载。原44条登记、原Alpha版本不重新编号或追加计算。

**#41只作为候选资料技术交付PR，可以在全部人工签核完成前合并；合并不代表任何资料获得正式问答资格，也不代表A4验收通过。** 所有真实候选仍blocked、human_approved=false；approved正式包数0、正式命中0。逐份人工审核后另开正式放行PR，由组长审核和合并。

## 2. 交付文件位置

| 内容 | 现有目录/文件 | 接收范围 |
|---|---|---|
| S1/S2/S3共7包、466片段 | `knowledge_base/processed/alpha/pending-review/beta-2026-11-23/` | competition、innovation、scholarship、college-scholarship、xinghuo、recommendation、retest及其texts；不含旧qinghe.json |
| S4 R3/R4两包、48片段 | `knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/` | 两包JSON、manifest及texts；[B8说明](qinghe-b8-handoff.md) |
| 原始HTML/DOCX/PDF/XLSX、来源记录、来源单元/映射 | `knowledge_base/processing/policy-review/2026-11-23/` | 全部引用原件；B8逐行/单元格映射qinghe-b8-source-map.json |
| 仍被引用的ZIP/RAR及隐私证据 | `knowledge_base/processing/policy-review/2026-11-19/` | 原同哈希附件及补查记录；不是重新下载或正式政策转换 |
| 处理/构建/检查/测试源码 | `knowledge_base/processing/` | 代码留项目原目录，不放docs |
| 本轮清单、交接及测试记录 | `docs/assignment-03/beta/` | Beta文档留本目录 |
| 正式库 | `knowledge_base/processed/alpha/approved/` | 本轮不写入；仍无正式包 |

不要只复制JSON：ParsedFile的storage_key均相对仓库根，原件和转换稿也必须保留。旧8包manifest仍用于501基线复验，**不能整份当作本轮9包名单**；9包唯一名单见审核清单及[机器可核对报告](beta-policy-handoff-validation.json)的index_results。

接口沿用DocumentPackage、DocumentMetadata、ParsedFile、ParsedChunk，不增加DTO或业务方向代码。S1—S4仅为场景，青禾只用COLLEGE_RESOURCES。字符区间针对LF/BOM归一化后的转换稿，不冒充原件页码；original_locator指向原件页/行/XPath，B8另有单元格和通知定位。

## 3. 与合并后main的兼容性及待协调

- #51：异步retrieve、同步get_document_metadata/get_parsed_chunk签名与既有实现一致。实际建立9个版本的514条离线技术索引，再用实际version_id/chunk_id检查blocked返回None；正式加载器必须跳过候选，不靠随机ID或空索引证明隔离。
- #45：青禾R3/R4的category_name分别精确匹配“实验室与科研团队”“研究方向与公开介绍”，同名记录不合并，中文五键沿用确认结果。不修改规则或测试fixture来配合资料。
- **S4-01/02/03的current_policy预期与真实R3 expired / R4 historical不一致**：细节及拟定历史边界见[审核清单第4节](beta-policy-approval-checklist.md#4-现行性与跨模块待协调)。交组长协调雷葭雨、林彦翔、吴诗莹。当前均blocked，不能宣称这些用例已经完成真实资料验收。
- #49：本轮全量pytest以包含运行稳定性及Qwen适配器变更的main为基线；本次仅跑离线测试，不使用真实Qwen/API凭证进行线上验收。

四个uncertain包是S1竞赛目录/创新学分、S2校级通则/院级通知。有限列表排查、施行条文或同哈希，不自动证明现行；缺失依据逐包列明。院级通知2026发布但正文2025年度的歧义不改，推免志愿服务30/60小时边界不自动算分。

青禾R3的2026-10-31期限已过；R4只是2026附件历史介绍。过期招募不能证明当前招募、接收资格、实时余量或联系渠道仍有效；历史介绍不能证明当前方向未变。历史资料需审核及工作流支持后才能按historical回答。**所有实际时效值保持不变，不为测试强改current。**

## 4. Python 3.10.11复现

在仓库根目录使用Python 3.10.11独立审核环境，不更改团队生产依赖。安装backend/requirements.txt、knowledge_base/processing/requirements-beta-review.txt、pytest、pytest-subtests。实际依赖版本见[环境记录](beta-policy-review-environment.json)。

```powershell
python --version  # 必须为3.10.11
python -m knowledge_base.processing.build_qinghe_b8
python -m knowledge_base.processing.build_qinghe_b8 --check
python -m unittest knowledge_base.processing.test_qinghe_b8 -v
python -m knowledge_base.processing.build_beta_policy_review --check
python -m knowledge_base.processing.reextract_beta_policy_review
python -m unittest knowledge_base.processing.test_beta_policy_review knowledge_base.processing.test_qinghe_conversion knowledge_base.processing.test_beta_reextraction knowledge_base.processing.test_policy_review knowledge_base.processing.test_policy_forms_privacy -v
python -m pytest tests -q -ra
python -m knowledge_base.processing.check_beta_policy_handoff
```

构建前先核对原件SHA和离线重提取；source-units失配时不写旧成果。完整清单、ParsedFile全部字段、官方通知附件绑定、来源单元及完整片段序列均需一致。青禾专用转换保护A1:I1合并区、24行、226个非空值、40个WPS链接和两张空表。构建/解析始终blocked，不承担签核或放行；异常测试变体不作为政策成果。

原8包501片段基线与B8两包均会校验；最后9包检查排除旧青禾，并独立核对各场景总数、实际索引数、9个元数据查询/514个片段查询、四方向正式命中及正式加载器结果。

## 5. 本轮测试结果与未完成验收

本次Python 3.10.11实测：B8构建及--check通过、B8专项12通过；既有资料处理/重提取/隐私65通过；后端全量449通过、28跳过、154个subtests通过、1条既有依赖弃用警告、失败0。9包实际索引514条，9个版本/514个片段查询被blocked隔离，四方向正式命中0；正式加载器跳过全部候选，approved包数0。

最新实测结果见[统一结果JSON](beta-policy-review-test-results.json)、[完整日志](beta-policy-review-tests.txt)及[9包隔离报告](beta-policy-handoff-validation.json)。B8专项目录另有qinghe-b8-tests.txt/qinghe-b8-test-results.json，旧数值不作为同步后结果。

本轮未完成且不冒称完成：所有资料最终人工签核、正式放行、S4 R1/R2/R5/R6补齐、S4-01/02/03历史模式协调、真实Qwen及正式A4问答验收、院级年度解释及推免计分争议澄清。跳过项单列，不计为通过。

## 6. 可转发交接

给组长：

> #41已按候选技术交付收尾，同步包含#45/#51/#49的main。请以beta-policy-approval-checklist.md审核9包514片段；旧青禾35片段仅留基线。所有真实资料仍blocked、human_approved=false，正式库0包。S1/S2四个uncertain的缺失依据、院级年度、推免计分争议及S4-01/02/03时效预期差异均已单列。请先复审技术交付；正式资料后续逐份审核、另PR放行。

给王智洋（供本人转发，本轮未代发）：

> 同步#41分支及原件后，请按9包清单做离线接收：S1=310、S2=127、S3=29、S4=48，总514。S4只用B8 R3/R4两包各24，排除旧qinghe.json。现在均blocked，不能作正式语料或A4正向验收。等组长逐包最终签核并通知正式approved版本后，再加载正式索引；不改公共接口或为了命中改current。
