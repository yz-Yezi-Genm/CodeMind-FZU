# Beta 政策资料交接说明

批次：2026-11-23；分支：`feat/beta-policy-review`；基线：`main@90df0f9`。

## 1. 先给组长看的入口

1. [四领域核验清单](beta-policy-verification-matrix.md)：8份资料的官方链接、发布日期、发布单位、对象/年度、时效、内容与待审核结论。
2. [冲突与缺失清单](beta-policy-gaps.md)：需要澄清的政策和不能回答的问题。
3. [候选资料manifest](../../../knowledge_base/processed/alpha/pending-review/beta-2026-11-23/manifest.json)：8份公共`DocumentPackage`，501片段，全部blocked，人工通过数0。
4. [逐片段原件映射](../../../knowledge_base/processing/policy-review/2026-11-23/chunk-source-map.json)及[青禾逐单元格审计](../../../knowledge_base/processing/policy-review/2026-11-23/qinghe-conversion-audit.json)。

正式审核前不写approved、不改enabled。不把“来源verified”“已解析”“测试通过”当成人工审核通过。现有Alpha候选包、原44条记录和公共接口保持原样。

## 2. 给王智洋的资料

建议直接同步本分支或合并后的仓库，连同依赖原件一起接收；**不要只转发8个JSON**。JSON中所有文件路径均相对仓库根目录。

| 必需内容 | 仓库位置 | 用途 |
|---|---|---|
| 本批manifest、8个JSON、8个Markdown | `knowledge_base/processed/alpha/pending-review/beta-2026-11-23/` | 格式、业务方向、原件关联及后续审核候选 |
| 本批HTML/DOCX/PDF/XLSX原件及核验记录 | `knowledge_base/processing/policy-review/2026-11-23/` | SHA、原始定位、来源日期与完整性复验 |
| 旧ZIP/RAR及原隐私审计 | `knowledge_base/processing/policy-review/2026-11-19/` | 两个包仍关联这批同哈希附件；不复制新档冒称重新下载 |
| 本页、核验表、缺口表、测试记录 | `docs/assignment-03/alpha/beta-policy-*.md/json/txt` | 接收边界和复现说明 |

接口沿用`backend.contracts.DocumentPackage / DocumentMetadata / ParsedFile / ParsedChunk`，不新增DTO。每条片段均含`source_file_key`、`original_file_key`、`original_locator`；`locator_note`的字符区间针对UTF-8/LF的Markdown文本。

S1/S2/S3/S4是场景标签。`business_direction_codes`仍取原44条字典映射，S4使用既有`COLLEGE_RESOURCES`，不创造数据库代码。

接收后目前只能做离线格式与定位验收；**正式approved加载器不应加载此目录**。四领域blocked真实候选的正式检索结果应为0，不能改状态来制造正向命中记录。组长逐份人工签核后，团队按现有approved加载规范交付对应正式版本，并通知下游同步；本生成器始终产出blocked，不承担放行功能。

## 3. 复现命令

以下在仓库根目录执行。`python`使用现有后端虚拟环境；`review-python`代表另一个安装了`knowledge_base/processing/requirements-beta-review.txt`的审核工具环境，不是项目新API，也不是固定命令名。将其替换为本机对应Python路径。

```powershell
# 可选联网刷新：会更新本批快照及核验时间。重新下载后必须重新核对并提交新的证据，不能只更新哈希。
review-python -m knowledge_base.processing.fetch_beta_policy_sources
review-python -m knowledge_base.processing.fetch_beta_policy_sources --attachments

# 离线重新提取：基于保留快照；推荐方案仅在新原件与已对照原件同哈希时复用第4页处理。
review-python -m knowledge_base.processing.extract_beta_policy_review

# 后端环境：生成候选，或只复验现有候选
python -m knowledge_base.processing.build_beta_policy_review
python -m knowledge_base.processing.build_beta_policy_review --check

# 新增的真实候选与异常门禁测试
python -m unittest knowledge_base.processing.test_beta_policy_review -v
review-python -m unittest knowledge_base.processing.test_qinghe_conversion -v

# 原Alpha资料检查与现有后端测试回归（不改写原有测试报告）
python -m unittest knowledge_base.processing.test_policy_review knowledge_base.processing.test_policy_forms_privacy -v
python -m pytest tests -q
```

审核工具实测版本：lxml 6.1.1、openpyxl 3.1.5、pypdf 6.21.4、pypdfium2 5.13.0；生产Markdown/TXT解析器不依赖新XLSX支持。后端全量测试需要另装pytest，本次为9.2.0，未修改生产依赖。复试PDF使用PDFium渲染9页并AI对照；这些图像仅用于本地比对，没有创建新PDF或伪造人工签字。

生成过程固定校验输入SHA；若官方附件内容变更、页数/表头改变或工作表出现新内容，应停下重新核验。不得通过仅修改基线哈希让检查“通过”。

## 4. 当前测试范围

本批技术检查：8个公共模型、所有关联文件SHA、501个片段字符区间和原件定位、4领域blocked问答隔离均通过；226个原非空单元格值在转换Markdown中逐一校验。

新增测试包含正常情况及异常：资料哈希篡改、原件映射篡改、候选误设enabled、XLSX表头变化、隐藏表新增内容、公式、字段空白。合成变体只在临时目录/内存内用于异常测试，不作为真实政策交付。

实际测试：新增14项通过，原Alpha资料/隐私审计13项通过，后端pytest 357项通过、28项跳过、136个子测试通过（1条既有依赖弃用警告）。跳过项不计为通过。结果见[JSON记录](beta-policy-review-test-results.json)和[日志](beta-policy-review-tests.txt)。这些是解析、证据与门禁测试，**没有运行真实Qwen、前端E2E或已审核语料的正向召回验收**。

## 5. 可转发消息

**发给组长：**

> Beta四领域的首批候选资料已整理：8份资料、501片段。青禾XLSX的24条实验室记录、226个非空单元格已全部转成Markdown，并保留工作表行列、原文件名、官方链接和SHA。每份资料都有来源、日期、适用范围及待确认项。全部仍为blocked，未进入approved，请先按核验表逐份审核。院级奖学金年度歧义、通则现行性及历史批次使用范围等问题已单列，没有自行推断或放行。

**发给王智洋：**

> Beta首批8份DocumentPackage已准备好，入口为`knowledge_base/processed/alpha/pending-review/beta-2026-11-23/manifest.json`，共501片段，公共接口不变，S4仍用COLLEGE_RESOURCES。请同步仓库及关联原件做离线接收复验；全部blocked，暂时不能建正式问答语料。青禾截止10月31日、2027届推免等历史限制均在元数据里。等组长逐份审核并通知正式approved资料后，再做四领域真实正向检索验收。
