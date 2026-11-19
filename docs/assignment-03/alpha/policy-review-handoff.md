# 政策资料核验交接

## 可直接转发给王智洋

王智洋你好，我是丁晓炜。这轮已整理竞赛认定、奖学金、推免的政策复核包，保持仓库现有 `DocumentPackage` 接口，没有增加或修改公共字段。

交付入口是 `knowledge_base/processed/alpha/pending-review/manifest.json`，其中列出5份JSON资料包及统计；请按清单读取，避免把 `manifest.json` 本身当成 DocumentPackage。原件和正文也在同一仓库；`storage_key` 均相对于**仓库根目录**，不能只拷贝5个JSON而遗漏其引用文件。

目前共371个片段，3份 `review_only`、2份 `blocked`，尚无人工签核或 enabled 正式包。竞赛通知页当前需统一身份认证、院级奖学金通知年度存在歧义，因此这两包继续 blocked；其余资料也有时效或人工审核事项。请不要在接收或重建索引时自动改成 enabled。

我已用你们现有 `LocalBM25Retriever(file_root=仓库根目录)` 实测5包全部成功离线建立索引，4组查询在正式 `retrieve()` 中均返回0条，符合当前限制。检查记录在 `docs/assignment-03/alpha/evidence/policy-review-check.json`；这只是技术兼容检查，未完成正式问答效果验收。

请帮忙确认：按清单接收公共JSON、保持复核状态、原始引用和新版本号的方式是否满足你的入库/索引模块；是否还需要单独的交付清单字段。若需要调整公共模型，我们一起向组长提出，不各自改接口。你确认前，我会把对接记录保持“待确认”。

详细核验结果在 `docs/assignment-03/alpha/policy-verification-matrix.md`。正式放行资料将与本轮候选包分开，人工签核完成后再交付 `approved/` 中的版本。

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

## 五份包及当前状态

| JSON文件 | 方向 | 片段 | 当前状态 | 主要限制 |
|---|---|---:|---|---|
| `competition.json` | 竞赛认定通知+3份DOCX | 224 | blocked | 通知页身份认证；205条数据行尚未逐条人工语义审核 |
| `scholarship.json` | 学校2026本科奖学金办法 | 59 | review_only | 后续修订排查、关键数值人工签核待完成 |
| `college-scholarship.json` | 学院院级奖学金通知 | 33 | blocked | 2026发布但正文2025年度；专项称谓、ZIP表单待确认 |
| `xinghuo.json` | 学院星火通知 | 35 | review_only | 报送期已过；RAR表单未可靠解析，保留教师/学生边界 |
| `recommendation.json` | 学院2027届推免推荐资格 | 20 | review_only | 2026-09-09 21:00申请截止已过；PDF转录待人工签核，原文志愿服务边界待释义 |

## 对接记录

| 事项 | 状态 |
|---|---|
| 与现有公共模型兼容 | 已通过本地校验 |
| 用现有BM25模块接收并校验所有引用文件 | 已通过本地离线检查，非生产入库 |
| 正式检索门禁 | 已确认5包均不出现在正式检索结果 |
| 本说明转发给王智洋 | **由用户转发；没有代发消息** |
| 王智洋对格式、用途、版本方式的确认 | **待对方确认** |
| 人工签核及正式资料放行 | **待完成** |
| Agent/Qwen真实端到端验收 | **不属于本轮已完成结论**；由对应成员基于审核后的真实资料联调 |
