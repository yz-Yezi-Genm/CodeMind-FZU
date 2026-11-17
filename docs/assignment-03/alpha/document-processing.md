# Alpha 文档解析与知识资料处理

日期：2026-11-17。模块：丁晓炜负责的文档解析与资料处理。状态：已实现离线解析及样例验证，待 PR 审核和索引模块联调。

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

课程作业链接：[Alpha 作业](https://edu.cnblogs.com/campus/fzu/2026-01SoftwareEngineeringandSoftwareEngineeringPractice/homework/16793)。开发时普通读取及浏览器访问均跳转博客园登录页，尚未核实作业页面正文；本交付按已提供的个人任务要求和仓库正式契约落实，不声称已验证课程所有提交要求。

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
| 文件归属 | `source_file_key` 对应包内 `ParsedFile.storage_key`；MD登记为curated，TXT登记为extracted |
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
- 来源核验和时效核验不因解析而升级。三个样例仍为`pending`/`pending`，原有登记状态和核验文字继续保留。
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

| 场景 | 现有资料 | 登记发布日期 | 实际内容与限制 | 片段数 |
| --- | --- | --- | --- | ---: |
| 竞赛认定 | [创新创业实践与素质拓展学分认定办法](../../../knowledge_base/政策资料/整理资料/学校/福州大学_创新创业实践与素质拓展学分认定办法.md) | 2024-05-30 | 含提取正文和分值表，待语义复核；不是2026竞赛目录 | 9 |
| 奖学金 | [2026本科生奖学金评定管理办法](../../../knowledge_base/政策资料/整理资料/学校/福州大学_2026_本科生奖学金评定管理办法.md) | 2026-05-18 | 当前是人工整理摘要，金额和比例待核验；不冒充完整官方正文 | 1 |
| 推免 | [学院2027推免复试方案整理稿](../../../knowledge_base/政策资料/整理资料/学院/计算机学院_2026_2027_推免复试方案.md) | 2026-09-17 | 当前是简要说明；接收推免复试不是本校推荐资格审查 | 1 |

三个样例来自仓库现有文件，共11片段；全部blocked。[解析前后对比](document-processing-comparison.md)列出来源、输入/输出、逐片段定位及文字样例；[机器汇总](../../../knowledge_base/processed/alpha/summary.json)保留哈希和统计。`.gitattributes`只为这些样例相关的文本输入和元数据预览固定LF换行，使Windows/Linux克隆后的实际字节哈希可复现；未修改任何政策文字或历史核查哈希。本次ParsedFile哈希是当前仓库字节哈希，不能替代原始采集快照哈希。

仓库现有31条CSV与设计里的44条离线预览存在范围差异；预览中部分`正文资料/`、新竞赛目录、学院推免推荐方案等物理文件尚未提交。缺失文件不伪造记录。本次不额外导入个人电脑的未审核资料，也不声称已经完成44条正式入库。

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
python -m backend.document_processing "knowledge_base/政策资料/整理资料/学校/福州大学_2026_本科生奖学金评定管理办法.md" --storage-root . --metadata knowledge_base/processed/alpha/scholarship-2026.metadata.json --output output/parsed-scholarship.json
```

`--max-chunk-chars`可配置片段长度，`--encoding`可显式指定编码。输出JSON不能覆盖正文或元数据输入文件。CLI正常返回0；处理失败返回1，参数错误返回2。原件路径不会出现在错误消息中。

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

parser: DocumentParser = TextDocumentParser(Path("."))
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

测试覆盖Markdown/TXT、标题跳级和同级切换、围栏代码、BOM/CRLF、中文路径、长行与中文长文无丢字、表格原文字保留、元数据不变、强制blocked、JSON契约回读、可重复结果、文件哈希、待OCR、PDF/DOCX待处理、空文件/乱码/越界/大小限制以及CLI正常和异常退出。

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

已完成：离线Markdown/TXT解析、元数据沿用、标题/定位/切片、格式待处理标记、三个场景的可复现样例、测试和记录。未完成：政策/附件逐条核验、OCR、缺失全文补充、数据库导入、Chroma/BM25/RRF索引接入、Agent真实问答，以及课程网页登录后的正文核对。
