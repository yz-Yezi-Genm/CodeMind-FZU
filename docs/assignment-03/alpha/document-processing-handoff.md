# 文档解析与索引模块联调交接清单

当前状态：已完成离线解析和公共模型验证，尚未调用真实索引器，尚未完成双方联调。本次成果通过独立分支及PR提交审核，不直接修改main。

## 交给索引模块的内容

| 场景 | 资料编号 | DocumentPackage文件 | 片段数 | 文件数 |
| --- | --- | --- | ---: | ---: |
| 竞赛认定 | 福大-2026-竞赛项目级别认定 | [competition-recognition-2026.json](../../../knowledge_base/processed/alpha/competition-recognition-2026.json) | 13 | 6 |
| 奖学金 | 福大-2026-本科奖学金 | [scholarship-2026.json](../../../knowledge_base/processed/alpha/scholarship-2026.json) | 4 | 3 |
| 推免 | 计算机学院-2027-推免资格推荐 | [recommendation-eligibility-2027.json](../../../knowledge_base/processed/alpha/recommendation-eligibility-2027.json) | 6 | 4 |

请使用整个审核包或相同分支文件，不能只发送JSON而遗漏`files[].storage_key`对应的正文、原件及附件。所有路径都相对于项目根目录，不依赖某位成员电脑的绝对路径。

## 接口调用示例

直接使用现有公共类和协议，不新增DTO、不变更字段。以下函数是接入示例，只有传入真实`KnowledgeIndexer`实现才会执行索引；不构造假成功结果。

```python
from pathlib import Path
from backend.contracts.models import DocumentPackage, IndexResult
from backend.contracts.protocols import KnowledgeIndexer

async def ingest_package(indexer: KnowledgeIndexer, json_path: Path) -> IndexResult:
    package = DocumentPackage.model_validate_json(
        json_path.read_text(encoding="utf-8")
    )
    return await indexer.index_document(package)
```

通用解析入口仍是`TextDocumentParser.parse_document(file_path, metadata)`。样例批处理在此基础上沿用44条预览中的文件角色，并把同版本原件、附件和整理稿装入同一个包。

## 联调时需要确认

| 检查项 | 约定或待确认内容 | 当前证据 |
| --- | --- | --- |
| 公共模型 | 使用仓库的DocumentMetadata/ParsedFile/ParsedChunk/DocumentPackage | 已通过模型回读测试 |
| 文件访问 | storage_key相对同一受控资料根目录；核对实际字节SHA-256 | 三个包的文件存在及哈希检查已通过 |
| 文档和版本身份 | 沿用record_code/version_no；不把离线预览UUID当作解析器新建的数据库主键 | 解析包沿用原登记；真实入库映射待验证 |
| 片段身份 | chunk_no在每个输入文件内从1连续编号；跨文件使用文件归属区分 | 已通过解析测试；入库主键策略待确认 |
| 正文定位 | locator/locator_note是当前MD行号与字符区间；original_locator保持null | 原件逐段对应尚未核实 |
| 重复导入 | 同一资料版本重复导入应如何处理，修订正文后是否更新version_no | 解析结果可重复；数据库幂等策略待确认 |
| blocked资料 | 所有样例保持blocked；是否允许受控离线索引或跳过，由索引实现明确报告 | 未开放正式Retriever；不得为了演示改enabled |
| 返回结果 | 使用现有IndexResult；不得添加skipped等新枚举 | 实际返回结果待联调留存 |

## 验收记录清单

- 正常情况：真实索引器收到三个包，记录每次IndexResult及实际处理片段数；即使索引成功，资料也继续blocked。
- 异常情况：缺失文件或哈希不符时，不能静默视为成功；保存实际错误或warnings。不能为了填表而伪造数据。
- 重复情况：相同包重跑，验证真实入库与索引结果，防止重复条目；配置或正文变化时保留版本依据。
- 检索隔离：正式Retriever不能返回这些blocked片段。没有可用证据时按现有问答契约处理。
- 只有获得以上实际运行记录后，才能将“真实索引联调”改为已完成。当前仅可确认解析与数据契约层验证通过。

复现命令、正常与异常单元测试见[文档处理说明](document-processing.md)；本轮修改及政策核验待办见[修订与待办](document-processing-review.md)。
