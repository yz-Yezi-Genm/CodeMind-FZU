# Alpha 文档解析与知识资料处理

日期：2026-11-17。模块：文档解析与资料处理。本轮显式文件角色修订通过独立分支随[PR #19](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/19)提交复核。真实索引联调仍待完成。

## 1. 任务范围与接口依据

本模块遵循 [Alpha 接口规范第8节](../interface-contract-v1.md) 和现有公共模型，不修改 `backend/contracts/models.py`、`protocols.py`、API 路径或状态值，也不重复定义 `DocumentMetadata`、`ParsedFile`、`ParsedChunk`、`DocumentPackage`。

实现类为 [TextDocumentParser](../../../backend/document_processing/parser.py)，满足原有 `DocumentParser` 协议：

```python
def parse_document(
    self, file_path: Path, metadata: DocumentMetadata,
) -> DocumentPackage:
    ...
```

本周支持 Markdown（`.md`/`.markdown`）和 TXT。优先处理竞赛认定、奖学金、推免三个场景；三个场景不是新业务方向，也不替代七类主题分类。

课程作业链接：[Alpha 作业](https://edu.cnblogs.com/campus/fzu/2026-01SoftwareEngineeringandSoftwareEngineeringPractice/homework/16793)。已在用户自行登录后只读核对正文：团队需提交冲刺计划、冲刺总结、Vlog及答辩材料，记录实际工作、测试和协作过程。本模块为团队提供可复现的代码、数据和测试证据，不代表团队整体交付已完成；未执行课程提交操作。个人开发细节以队长任务及仓库正式接口为准。

## 2. 已实现的处理流程

```text
受控资料根目录 + 文档路径 + DocumentMetadata
                  ↓
检查文件范围、大小、格式、编码
                  ↓
Markdown 跳过元数据头，识别标题；TXT 保留普通文本
                  ↓
按标题分节，再按段落/行/句子及字符上限切片
                  ↓
DocumentPackage(metadata + files + chunks)
                  ↓
JSON 样例/交给 KnowledgeIndexer（本模块不执行入库或索引）
```

| 要求 | 实现方式 |
| --- | --- |
| 读取正文 | 默认严格 UTF-8/UTF-8 BOM；可显式指定 GB18030 等编码，不使用 `errors=ignore` 猜测正文 |
| 切片 | 默认最多1200个字符；优先标题分节，然后选段落、换行或句末边界；极长单行硬切，最后一段不丢失 |
| 标题层级 | 识别1—6级 ATX 标题与 Setext 标题；围栏代码中的 `#` 不当标题；完整路径写入现有 `locator_note` |
| 片段编号 | 每份输入文件内从1连续编号，写入 `chunk_no`；重跑同一输入和配置得到相同结果 |
| 文件归属 | `source_file_key` 对应包内 `ParsedFile.storage_key`；业务角色通过构造参数`file_role`显式传入，不与扩展名绑定 |
| 定位 | `locator` 保存输入文件行号和标题路径；`locator_note` 保存行号、字符区间和层级JSON字符串 |
| 文件核对 | SHA-256按原始文件字节计算；不改写输入文件 |
| 路径 | 文件必须在配置根目录内；storage_key为相对POSIX路径，不输出本机绝对路径 |
| 公共格式 | 直接返回并重新校验现有Pydantic `DocumentPackage`；JSON可以由相同类读回 |

为保证内容定位，切片不生成总结、不改写政策、不填补缺失条款。去除片段边缘空白，不重叠复制正文。切片长度是字符数，不是模型token数；复杂表格目前保留原文字和数值，较长表格可能跨片段，不保证每段都有表头，表格关系仍需人工复核。

Markdown开头存在`---`元数据头时跳过到闭合的`---`或`...`，不把该头当作政策正文。元数据以调用者传入的`DocumentMetadata`为准，文件中的YAML不能覆盖来源或检索状态。未闭合的头作为错误处理，避免把登记信息误当正文。

## 3. 元数据、核验与定位边界

- 保留发布单位、来源链接、发布日期、生效日期、适用范围、原编号和版本；缺少日期保持null，不根据文件名推断。
- 样例元数据来自已入仓库的 [44条离线预览](../../assignment-02/database-design/knowledge-base/入库预览_44条.json)，仅选取公共模型已有字段；完整原登记值保留在`import_snapshot`。预览不是运行中的数据库。
- `category_name`仍是七类主分类；`business_direction_codes`沿用预览中的`POLICY_AFFAIRS`、`EDUCATION_CAREER`、`COMPETITION_RESEARCH`等已有代码，不自行改名。
- 解析成功只把本次输入文件的`extraction_status`标记为`extracted`；这不表示资料是全文、条款正确、附件完整或政策当前有效。
- 来源核验和时效核验不因解析而升级。竞赛与推免来源状态沿用`partial`，奖学金沿用`pending`；三个样例时效均为`pending`，原有核查文字继续保留。`partial`仅表示历史上有部分核查记录。
- 样例生成时，若时效为pending且原policy_status为“当前有效”，导出表述为“时效待核验（原归档标签：当前有效）”；import_snapshot中的原始值保留，不改44条预览或原件。
- **所有输出强制`retrieval_status=blocked`，`index_status=pending`**；即使调用者传入合法的enabled元数据，输出也保持blocked，不修改调用者原对象。
- 行号从1开始；字符区间为左闭右开`[char_start, char_end)`，基于解码、去BOM、统一LF后的输入全文。行号包含被跳过的元数据头，便于回到原文件核对。
- `original_file_key`、`original_locator`默认null。样例包保留可找到的官方原件/附件文件记录，但尚未核实逐段原件定位，不把整理稿行号冒充官方网页段落或PDF页码。

`locator_note`示例（这是现有string字段内的JSON，不是新增契约字段）：

```json
{
  "coordinate_system": "decoded_text_lf_bom_removed",
  "line_start": 18,
  "line_end": 28,
  "char_start": 300,
  "char_end": 700,
  "heading_path": [{"level": 1, "title": "文件标题"}, {"level": 2, "title": "申请条件"}],
  "note": "本输入文件定位；不是官方原件页码。字符区间左闭右开，行号从1开始。"
}
```

以上数字仅解释字段含义；真实定位见样例JSON。

## 4. 三个代表性资料及实际覆盖

| 场景 | 本次解析的正文提取稿 | 登记发布日期 | 实际内容与限制 | 片段数 |
| --- | --- | --- | --- | ---: |
| 竞赛认定 | [2026大学生学科竞赛级别认定结果](../../../knowledge_base/政策资料/正文资料/学校/福州大学_2026_大学生学科竞赛级别认定结果.md) | 2026-03-06 | 网页及三份DOCX附件已有提取文字；目录行、表格和用途待复核，不直接推导奖学金或综评分值 | 13 |
| 奖学金 | [2026本科生奖学金评定管理办法](../../../knowledge_base/政策资料/正文资料/学校/福州大学_2026_本科生奖学金评定管理办法.md) | 2026-05-18 | 改用已有正文提取稿；关键金额、比例、资格条款及学院细则待核验 | 4 |
| 推免 | [学院2027届本科推免资格推荐工作方案](../../../knowledge_base/政策资料/正文资料/学院/计算机学院_2027_本科推免资格推荐工作方案.md) | 2026-09-08 | 属于本科推荐资格方案，保留PDF四页提取文字；第4页计分表待复核，申请期已过 | 6 |

三个正文样例共23片段，全部blocked，关联文件均已在本次修订中补齐。[解析前后对比](document-processing-comparison.md)列出来源、输入/输出、逐片段定位；[机器汇总](../../../knowledge_base/processed/alpha/summary.json)保留哈希和统计。旧的创新学分、推免复试资料继续作为原始知识库资料保留，但不再用来代替本次核心样例；旧的两个演示解析包已移除，避免交接时混用。

本次从已有本地知识库归档补入11个与样例对应的文件，包括3份正文提取稿及对应的整理稿、网页和附件。[归档文件校验记录](../../../knowledge_base/processing/sample-provenance.json)记录相对来源键、角色、实际字节数和SHA-256，文件未改写。新增归档文件使用`.gitattributes`的`-text`保留原始CRLF字节，原有样例文本的LF规则继续保留；解析坐标仍按解码后统一LF计算。归档副本中的“当前有效”等历史标签不是本次时效结论，解析器跳过该元数据头，沿用44条预览中的核验字段。

归档记录的crlf_count仅统计文本文件；PDF、DOCX为二进制格式，该值为null，另附“不适用”说明，不把二进制字节模式解释为文本行数。

仓库现有31条CSV与44条离线预览仍存在范围差异；本次只补齐三个样例所需文件，不修改原44条编号、总量、历史核查记录或全量CSV，也不声称44条已经正式入库。

## 5. 运行与复现

从仓库根目录执行，Python 3.12已验证：

```bash
python -m venv .venv
# 激活方式沿用 backend/README.md
python -m pip install -r backend/requirements-dev.txt

# 生成三个代表性解析包和前后对比，完全离线，不需要模型密钥/数据库
python -m scripts.parse_alpha_documents

# 完整测试及可交付测试记录
python -m scripts.check_document_processing
```

单文件CLI示例（输入MD和元数据JSON均已在仓库）：

```bash
python -m backend.document_processing "knowledge_base/政策资料/正文资料/学校/福州大学_2026_本科生奖学金评定管理办法.md" --storage-root . --metadata knowledge_base/processed/alpha/scholarship-2026.metadata.json --output output/parsed-scholarship.json --file-role extracted
```

`--max-chunk-chars`可配置片段长度，`--encoding`可显式指定编码。输出JSON不能覆盖正文或元数据输入文件。CLI正常返回0；处理失败返回1，参数错误返回2。原件路径不会出现在错误消息中。

文件角色是业务属性。通过`TextDocumentParser(root, file_role="extracted")`或CLI的`--file-role`传入，使用现有`FileRole`枚举的original、attachment、extracted、curated四个值；Python也接受该枚举实例。非法角色会被拒绝，Markdown元数据头不能覆盖角色。为兼容原调用，未传角色时仍沿用旧默认值：MD为curated、TXT为extracted、其他格式为original；已有业务登记时应显式传入，默认值不能替代业务判断。

批处理从44条预览读取角色，在调用解析器前传入，三个Markdown正文直接返回extracted，不再事后修改解析结果。角色不会改变格式支持：指定DOCX为attachment仍只登记文件，正文待处理、chunks为空、检索保持blocked；不表示已支持DOCX解析。

## 6. 异常与未支持格式

| 情况 | 结果 |
| --- | --- |
| 文件不存在/不是普通文件 | 抛出`DocumentProcessingError`，code=`DOCUMENT_NOT_FOUND` |
| 文件越过资料根目录（含解析后的链接路径） | `OUTSIDE_STORAGE_ROOT` |
| 文件过大（默认10MiB） | `FILE_TOO_LARGE` |
| 解码失败/二进制控制字符 | `TEXT_DECODE_FAILED` / `BINARY_TEXT`，不输出乱码正文 |
| 空正文/仅元数据头 | `EMPTY_DOCUMENT` |
| Markdown元数据头未闭合 | `INVALID_FRONT_MATTER` |
| PDF/DOCX/HTML等本周未支持格式 | 返回登记文件、空chunks、`extraction_status=pending`、blocked |
| 输入元数据明确为needs_ocr（包括MD占位说明） | 返回空chunks、needs_ocr、blocked；不假装已完成OCR |

不凭PDF后缀断言是扫描件。是否需要OCR未知时标记pending并写待处理说明；已确认扫描件由调用者传入`needs_ocr`。本地错误code属于解析器实现细节，不新增HTTP契约状态；后端可按已有规范转换为`DOCUMENT_PROCESSING_FAILED`。

## 7. 与数据库/索引模块交接

```python
from pathlib import Path
from backend.contracts.models import DocumentPackage
from backend.contracts.protocols import DocumentParser, KnowledgeIndexer
from backend.document_processing import TextDocumentParser

parser: DocumentParser = TextDocumentParser(Path("."), file_role="extracted")
package = parser.parse_document(file_path, metadata)

# 文件交接时可重新验证同一个公共模型
package = DocumentPackage.model_validate_json(json_path.read_text(encoding="utf-8"))

# 由索引负责人提供真实实现后，在异步调用方执行：
# result = await indexer.index_document(package)
```

王智洋可直接使用三个`DocumentPackage`JSON或解析器返回值，按`record_code + version_no`识别登记版本、按`storage_key`关联文件、按`chunk_no`保存片段。本模块不预生成数据库UUID；建表、ORM和UUID归属沿用索引模块。

`storage_root`决定逻辑键的根：样例使用仓库根，因此键带`knowledge_base/`前缀。部署时调用方应把同样的键映射到真实文件根；只拷贝JSON不代表原件已部署。

待双方联调确认：重复导入的幂等策略、后续修订资料的version_no、切片配置变化时的索引替换策略、索引器对blocked资料的存储/跳过行为及IndexResult。索引器可以做受控离线构建，但正式Retriever仍必须过滤blocked；不为演示自动改enabled。本次未联系对方或执行真实索引，不能记作已联调通过。

## 8. 测试与成果

测试覆盖Markdown/TXT、标题跳级和同级切换、围栏代码、BOM/CRLF、中文路径、长行与中文长文无丢字、表格原文字保留、元数据不变、强制blocked、JSON契约回读、可重复结果、文件哈希、待OCR、PDF/DOCX待处理、空文件/乱码/越界/大小限制以及CLI正常和异常退出。本轮新增直接解析和CLI的Markdown extracted、Markdown curated、DOCX attachment测试，包含非法角色拒绝和旧默认值兼容性。

测试结果以 [test-results.json](test-results.json) 和 [测试日志](document-processing-tests.txt) 为准。Windows无符号链接创建权限时，对应测试明确跳过；普通越界路径测试仍执行。全仓库已有接口/API测试一并运行，未修改其预期。

| 交付项 | 文件 |
| --- | --- |
| 解析模块源码/CLI | `backend/document_processing/` |
| 样例选择清单 | `knowledge_base/processing/alpha-manifest.json` |
| 可重复批处理 | `scripts/parse_alpha_documents.py` |
| 三个解析包、输入元数据、统计 | `knowledge_base/processed/alpha/` |
| 单元测试 | `tests/test_document_processing.py` |
| 测试记录生成器 | `scripts/check_document_processing.py` |
| 前后对比 | 本目录`document-processing-comparison.md` |
| 交接文档 | 本文件 |

已完成：离线Markdown/TXT解析、元数据沿用、标题/定位/切片、格式待处理标记、三个场景的正文样例及关联文件补齐、前后对比、测试和课程要求只读核对。未完成：政策时效与附件逐条核验、OCR、44条全量正文审核、数据库导入、Chroma/BM25/RRF索引接入和Agent真实问答。

具体修订与剩余工作见[修订与待办](document-processing-review.md)；真实索引对接见[联调交接清单](document-processing-handoff.md)。不能将JSON可回读或单元测试通过写成真实索引联调通过。
