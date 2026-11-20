# ZIP / RAR 附件隐私补查

检查日期：2026-11-20；对应 PR #31。检查方法为工具提取与 AI 全量内容对照，**等待组长复审，不冒充人工签核**。

## 本次结论

检查两个压缩包中的全部 **8 个文件：5 份 XLSX、6 个工作表、3 份旧 DOC**。本快照未发现真实申请人或教师的已填写个人记录：院级表格是明确标“例”的示例，星火汇总表是占位示例，三份 DOC 是空白申请模板。原始附件字节及哈希保留，无须因本次检查移除或脱敏附件；报告不列出示例姓名、学号、政治面貌、经济情况、电话、出生日期等原值。

此结论仅针对下列精确哈希的官方附件；不是全仓库隐私保证，也不是政策有效性、正式入库或检索放行结论。候选包仍为 **3 份 review_only、2 份 blocked；enabled 0 份**。

## 每个文件的检查结果

所有文件名、成员 SHA-256、字节数、逐表行号/单元格坐标及提取摘要见[完整审计记录](../../../knowledge_base/processing/policy-review/2026-11-19/form-privacy-audit.json)。这里用类别简称，避免复制填报原值。

| 压缩包及成员 | 工作表 / 全部非空行 | 申请人数据区结论 |
|---|---|---|
| 院级 ZIP：学业类（类别三）XLSX | Sheet1；1—4 行，40 个非空单元格 | 第 4 行明确标“例”；其余为标题/表头，无其他填报记录 |
| 院级 ZIP：学术类（类别二）XLSX | Sheet1；1—4 行，36 个非空单元格 | 第 4 行明确标“例”；无其他填报记录 |
| 院级 ZIP：学生工作类（类别四）XLSX | Sheet1；1—4 行，36 个非空单元格 | 第 4 行明确标“例”；无其他填报记录 |
| 院级 ZIP：学科竞赛类（类别一）XLSX | 汇总表、本科生补充；各 1—4 行，分别 38 / 29 个非空单元格 | 两表第 4 行均明确标“例”；无其他填报记录 |
| 星火 RAR：申请表汇总表 XLSX | 汇总表；1—3 行，25 个非空单元格 | 第 3 行姓名为 X 占位、部门为多个选项，属于示范填法，无第二条填报记录；不能当真实教师或学生数据 |
| 星火 RAR：类别一旧 DOC | 全文及表格填写区 | 空白教师申请模板，个人资料、履历、事迹、签名等区无填写内容 |
| 星火 RAR：类别二旧 DOC | 全文及表格填写区 | 空白教师申请模板，无填写的申请人记录 |
| 星火 RAR：类别三旧 DOC | 全文及表格填写区 | 空白教师申请模板，无填写的申请人记录 |

六个工作表合计 **204 个非空单元格**，全部检查，未按“前几行”截断。学业类的格式范围达到第 16384 列，直接扫描底层 XML 的实际单元格，避免把宽格式区域误当成数据遗漏。

## 覆盖范围

- XLSX：所有工作表、所有实际单元格及公式/缓存、隐藏行列、合并区域、共享字符串（含未引用项）、批注、页眉页脚、定义名称、关系目标及文档属性。此批没有隐藏行列/隐藏表、公式、批注、外链或二进制嵌入对象；属性为通用软件/设备账号、版本及文档标识，未发现真实申请人身份。
- 旧 DOC：使用 antiword 0.37 的 `-t -r -s -m UTF-8.txt` 提取全部文本，包含工具支持的隐藏及删除文字；核对所有填写区、OLE 属性与流目录，并用 oletools 0.60.2 静态检查模板 VBA 与 P-code。未执行 Office、宏、外链或公式。三份模板有同源办公模板宏，未发现其中包含真实申请人/教师资料；没有把“有宏”误判成“有真实填报记录”。
- 不声称完成磁盘空闲区恢复等取证，也不将正则“没找到电话”当作隐私通过依据。正文、表格、示例语义及模板属性均进行了对照；精确字节变化或新增成员必须重新检查。

## DOC 的 OLE / VBA 静态检查摘要

下表数值来自实际运行 `audit_policy_forms` 生成的 `form-privacy-audit.json`，不是单元测试中的模拟输出。字符数是 antiword UTF-8 输出解码后的长度，非空行数按该输出统计。

| 旧 DOC | 提取字符数 | 非空文本行 | OLE 流 | 其中宏相关流 | VBA 源码模块 / P-code 报告 |
|---|---:|---:|---:|---:|---|
| 类别一 | 2944 | 41 | 19 | 13 | 5 / 1 |
| 类别二 | 2801 | 39 | 19 | 13 | 5 / 1 |
| 类别三 | 2877 | 40 | 19 | 13 | 5 / 1 |

每份 DOC 均检查了 `WordDocument`、`1Table`、`Data`、文档摘要属性及 `Macros/` 下的全部流，并记录各流 SHA-256。作者、最后保存者、标题属性存在；值经核对属于模板软件/设备账号和模板标题，报告不公开原值。未发现申请人照片或其他 `ObjectPool` 嵌入对象流。

五个 VBA 源码模块为 `ThisDocument.cls`、`RJeGov.bas`、`frmSelect.frm`、`Common.bas`、`FileDialog.cls`，另有一份 `VBA_P-code.txt` 静态反汇编报告。内容为办公模板、文件选择和文档操作逻辑；本次未发现真实申请人或教师的填报资料。三份 DOC 的对应 VBA 源码/P-code 摘要相同，正文摘要各自独立保留。P-code 仅将工具自动生成的临时输入路径头替换为 `<INPUT_DOC>`，实际代码不改写。

全程没有启动 Word 或执行宏。上述结果用于附件隐私核查，不等同于宏运行安全认证，也不表示已完成政策正文转换、人工签核或正式检索开放。

## 实际审计与单元测试的区别

| 执行入口 | 实际做了什么 | 能证明什么及其边界 |
|---|---|---|
| `python -m knowledge_base.processing.audit_policy_forms ...` | 读取两个原始归档的全部成员；重新扫描 XLSX；对三份 DOC 实际调用 antiword，再用 olefile 读取属性/流、oletools 提取 VBA/P-code；最后逐项比对已审阅基线 | 本次实际转换和静态分析产物与基线一致；结论针对这些原件字节。不是单靠旧摘要宣布通过 |
| `test_current_archives_match_full_reviewed_baseline` | 实际校验归档和所有成员哈希，并重新扫描 XLSX；DOC 的 `inspection` 使用既有基线值，不调用 antiword / oletools | 验证文件未变、XLSX 检查一致及基线关联；**不能证明本轮重新转换了 DOC 或重新分析了 VBA** |
| `test_doc_converter_includes_hidden_removed_text_and_rejects_warnings` | 用模拟的子进程结果检查 `-r/-s` 参数及遇到转换警告时拒绝通过 | 验证调用/错误处理逻辑；**不属于真实 DOC 转换审计** |

其余隐私单元测试使用合成 XLSX 检查隐藏内容覆盖、报告不泄露字段值以及归档变化时拒绝沿用结论；不替代实际附件内容对照。实际审计 JSON 与单元测试日志分别保留，不能将“13 项测试通过”当作三份 DOC 再次转换的唯一依据。

## 原件完整性与复现

| 官方附件 | 本地快照 SHA-256 |
|---|---|
| `college-attachments.zip` | `3023a76d80d3ff80ad5fa474727a4d754f1dc3b71774af15588f98505338902d` |
| `xinghuo-forms.rar` | `b99ec34294b07689725302a25aed8575057da551a040b6f7353484e7701d9ade` |

官方 URL、下载时间及原始字节摘要继续保留在[附件下载记录](../../../knowledge_base/processing/policy-review/2026-11-19/attachment-fetch.json)。未重新压缩或修改原件，因此原来的来源与完整性校验仍可复现，371 个政策片段和原件定位不变。

全量审计需要 Python、Windows `tar`、antiword 的 UTF-8 映射文件、`olefile==0.47`、`oletools==0.60.2`。它们只用于离线审计，不增加后端运行依赖。本次 antiword 从[项目源码](https://github.com/grobian/antiword)在本机编译，工具摘要保存在审计 JSON；未把工具或原始提取文本提交到公开仓库。

```powershell
# 在具备上述审计工具的环境执行；路径改为该机安装位置。
python -m knowledge_base.processing.audit_policy_forms --antiword '工具目录/antiword.exe' --antiword-home '工具目录/Resources'
# 以下测试及候选包校验使用项目原有后端环境，无须审计工具依赖。
python -m unittest knowledge_base.processing.test_policy_forms_privacy knowledge_base.processing.test_policy_review -v
python -m knowledge_base.processing.build_policy_review
python -m knowledge_base.processing.build_policy_review --check
```

[基线](../../../knowledge_base/processing/policy-review/2026-11-19/form-privacy-baseline.json)固定本次已对照内容的成员哈希、逐表/逐流检查摘要和结论。全量审计重跑会重新提取 XLSX 与 DOC，再比对该基线；成员、原件或检查输出变化会失败，不能凭旧结论接受新文件。普通回归测试只校验归档/成员哈希及 XLSX，**不冒充重新执行 DOC 转换**。

2026-11-19 的 `form-attachment-audit.json` 保留为历史“表头/版式补查”，不能单独用作此次全量隐私检查证据；以本页及 `form-privacy-audit.json` 为新记录。

## 继续保留的政策待办

竞赛通知登录核验、院级奖学金年度/称谓确认、星火旧 DOC 的正式政策转换与语义复核、人工签核仍为后续正式资料放行任务。本次 DOC 提取只服务隐私检查，没有新增正式正文、没有将任何资料改成 enabled，也没有向 `approved/` 放入资料包。PR #31 继续是 **pending-review 候选资料交付**。

验证记录：[本次专项测试](evidence/policy-review-privacy-tests.txt)（13/13通过，含6项新增隐私测试）、[原有回归测试](evidence/policy-review-privacy-regression.txt)（171项，170通过、1项Windows符号链接条件跳过）、[结果摘要](evidence/policy-review-privacy-test-result.json)和[候选包哈希/定位/检索隔离检查](evidence/policy-review-check.json)。

公开测试日志中的本机 Windows 绝对路径统一替换为 `<REPO>/` 下的相对位置，执行环境记录中的解释器路径也作同样处理；只清理机器路径，保留告警、异常堆栈的文件/行号、测试结果及原始统计。同目录历史日志中的失败记录仍按原样保留，不表述为本次重新运行结果。
