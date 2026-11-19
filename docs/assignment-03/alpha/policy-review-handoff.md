# 政策资料核验交接

## 可直接转发给王智洋

王智洋你好，我是丁晓炜。这轮已整理竞赛认定、奖学金、推免的政策复核包，保持仓库现有 `DocumentPackage` 接口，没有增加或修改公共字段。

交付入口是 `knowledge_base/processed/alpha/pending-review/manifest.json`，其中列出5份JSON资料包及统计；请按清单读取，避免把 `manifest.json` 本身当成 DocumentPackage。原件和正文也在同一仓库；`storage_key` 均相对于**仓库根目录**，不能只拷贝5个JSON而遗漏其引用文件。

目前共371个片段，3份 `review_only`、2份 `blocked`，尚无人工签核或 enabled 正式包。竞赛通知页当前需统一身份认证、院级奖学金通知年度存在歧义，因此这两包继续 blocked；其余资料也有时效或人工审核事项。请不要在接收或重建索引时自动改成 enabled。

我已用你们现有 `LocalBM25Retriever(file_root=仓库根目录)` 实测5包全部成功离线建立索引，4组查询在正式 `retrieve()` 中均返回0条，符合当前限制。检查记录在 `docs/assignment-03/alpha/evidence/policy-review-check.json`；这只是技术兼容检查，未完成正式问答效果验收。

2026-11-19用户转述王智洋的接收反馈：5份候选包、371个片段的模型格式、SHA-256、字符区间与原件定位映射全部通过，blocked/review_only正式问答隔离正常，代码对接没有问题。此处记录的是对方反馈，不冒充本模块重新执行了他的验收。

后续待办已转为人工核验放行、正式包交付及三场景真实命中验收；如需要调整公共模型，仍共同向组长提出，不各自改接口。

详细核验结果在 `docs/assignment-03/alpha/policy-verification-matrix.md`。正式放行资料将与本轮候选包分开，人工签核完成后再交付 `approved/` 中的版本。

当前逐项待办、需要的材料和可转发给王智洋/组长的文字，见[政策资料当前待办与协作分工](policy-review-next-steps.md)。2026-11-19已补5份Excel的表头/合并区域检查及学校奖学金有限范围后续修订排查；3份旧DOC仍待可靠转换。候选正文、片段数及原件未改，增补核验说明后仍为blocked/review_only。

## 接收方式

推荐拉取本分支/PR的完整仓库。下面是调用示例，使用现有接口：

```python
import json
from pathlib import Path
from backend.contracts import DocumentPackage
from backend.retrieval.local import LocalBM25Retriever

root = Path.cwd()  # 在仓库根目录执行
manifest = json.loads((root / "knowledge_base/processed/alpha/pending-review/manifest.json").read_text(encoding="utf-8"))
indexer = LocalBM25Retriever(file_root=root)

async def receive():
    for entry in manifest["packages"]:
        package = DocumentPackage.model_validate_json((root / entry["package"]).read_text(encoding="utf-8"))
        result = await indexer.index_document(package)
        print(package.metadata.record_code, result.status, result.indexed_count)
```

执行离线索引检查不代表允许正式问答使用。`review_only` 与 `blocked` 的资料都不应进入 `RetrievedChunk` 正式回答结果。

## 格式及版本

| 内容 | 交付约定 |
|---|---|
| 模型 | 直接复用 `backend/contracts/models.py` 的 `DocumentMetadata`、`ParsedFile`、`ParsedChunk`、`DocumentPackage` |
| 标识 | 原44条的 `record_code` 不变；本轮 `version_no=review-2026-11-19-1`，与旧 `import-1` 样例分开 |
| 正文 | 从官方快照提取/按PDF版式对照的 UTF-8 Markdown；Word逐行带原表头，HTML保留rowspan/colspan，星火分教师与学生标题 |
| 文件角色 | 直接提取稿显式 `extracted`；含人工待复核版式转录的推免整理稿 `curated`；HTML原件 `original`，原始下载附件 `attachment` |
| 定位 | `locator`/`locator_note` 指向本轮Markdown行号和LF字符区间；`original_file_key`/`original_locator` 指向原件XPath、OOXML表行或PDF页码。两类坐标不混用 |
| Git换行 | 快照及提取稿目录附有 `.gitattributes`，防止Windows检出改写字节，导致SHA-256失配；不要保存时自动转换提取稿换行后继续使用旧哈希 |
| 日期 | DTO的 `deadline_on` 仅存日期；推免准确截止时刻写入已有 `temporal_notes.deadline_exact_local`；星火未擅自补截止时刻 |
| 核验 | `source_verification_status` 与时效状态分开；`import_snapshot` 原样保留；本轮检查说明与人工待核验事项写入 `verification_note`、`temporal_notes` |
| 内部DTO待协调 | 任务书第3.5节指出RetrievedChunk尚未完整暴露 `deadline_on`、`applicability_raw`。本轮只在已有DocumentMetadata保留这些字段；请与吴诗莹、雷葭雨协商传递方式，不把本轮元数据齐全误认为工作流已能判断适用性 |
| 完整性 | 所有 `ParsedFile.sha256` 按原始文件字节计算；[原件映射](../../../knowledge_base/processing/policy-review/2026-11-19/chunk-source-map.json)逐片段可追溯 |
| 检索门禁 | 本轮包仅 blocked/review_only；保留原生成脚本blocked默认值；无自动批准、自动enabled或生产库写入 |

## 统一加载入口的衔接

2026-11-19核对王智洋的[PR #35](https://github.com/yz-Yezi-Genm/CodeMind-FZU/pull/35)分支代码：`backend/retrieval/alpha_corpus.py`支持 `approved/manifest.json` 和目录内直接放包JSON两种方式。该PR此时尚未合并main，不能表述为main运行入口已接入。

- 若使用manifest，`packages[].package`须指向 `approved/` 内的包；以仓库根为file_root时使用仓库相对路径。不能原样复制仍指向 `pending-review/` 的候选清单。
- 入口会跳过非enabled包；若manifest条目或 `metadata.temporal_notes` 已有 `human_approved` 且不为true，也会跳过。本轮候选包显式为false，单改 `retrieval_status` 不会通过接收检查。
- 正式放行时应在完成实际人工审核后，保留审核者、日期、版本、原件哈希、范围和用途等记录，再生成一致的正式包/manifest。不得通过删掉未审核标记来规避限制。
- 该分支还提供只读 `get_document_metadata(version_id)`、`get_parsed_chunk(chunk_id)`，可让业务规则读取原有元数据与定位，公共RetrievedChunk不必由我们擅自扩展。下游合并及规则接入完成情况仍需对应成员确认。

## 五份包及当前状态

| JSON文件 | 方向 | 片段 | 当前状态 | 主要限制 |
|---|---|---:|---|---|
| `competition.json` | 竞赛认定通知+3份DOCX | 224 | blocked | 通知页身份认证；205条数据行尚未逐条人工语义审核 |
| `scholarship.json` | 学校2026本科奖学金办法 | 59 | review_only | 有限范围后续修订排查已补，现行性和关键数值待人工签核 |
| `college-scholarship.json` | 学院院级奖学金通知 | 33 | blocked | 2026发布但正文/表头2025考核年度；专项称谓、统计区间待确认；ZIP内4份XLSX表头已提取 |
| `xinghuo.json` | 学院星火通知 | 35 | review_only | 报送期已过；RAR内教师XLSX表头已提取，另3份旧DOC待转换，不当学生表单使用 |
| `recommendation.json` | 学院2027届推免推荐资格 | 20 | review_only | 2026-09-09 21:00申请截止已过；PDF转录待人工签核，原文志愿服务边界待释义 |

## 对接记录

| 事项 | 状态 |
|---|---|
| 与现有公共模型兼容 | 已通过本地校验 |
| 用现有BM25模块接收并校验所有引用文件 | 已通过本地离线检查，非生产入库 |
| 正式检索门禁 | 已确认5包均不出现在正式检索结果 |
| 对方接收反馈 | **2026-11-19用户已提供王智洋的验收反馈**；本模块没有代发消息 |
| 王智洋对候选包格式、文件校验、定位与门禁的验收 | **对方反馈通过**，覆盖5包371片段；不是政策内容或人工放行结论 |
| approved统一加载入口 | **PR #35分支代码已核对**，当时尚未合并main；支持manifest或直接JSON，仍需实际审核放行包 |
| 人工签核及正式资料放行 | **待完成** |
| Agent/Qwen真实端到端验收 | **不属于本轮已完成结论**；由对应成员基于审核后的真实资料联调 |
