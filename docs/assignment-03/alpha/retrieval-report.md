# Alpha 本地知识检索报告

2026-11-18 · 数据库与检索

本地检索已打通 `DocumentPackage → IndexResult → list[RetrievedChunk]`。竞赛认定、奖学金和推免的三个真实资料包共 23 个片段，文件及登记的 SHA-256 校验通过。三个包均保持 `blocked`，用对应问题检索均返回 `[]`。已有 Alpha V1 公共接口足够支持这条数据流，无需调整字段、状态或签名。

## 检索方法

索引器用公共模型重新验证包的快照，检查文件键、源文件和原件引用，以及文件内的片段序号。配置受控 `file_root` 时会检查文件能否读取，并比对已登记的原始字节 SHA-256。未就绪的来源文件如果没有被任何保留片段引用，可以跳过磁盘校验。其余文件缺失或哈希不符时返回 `failed` 和 warnings，同时清除该版本的旧索引。重复导入同一版本会替换旧快照，片段身份按资料编号、版本号、来源文件及片段序号确定。本地 UUID 可复现，接入持久化时需要与数据库身份映射。

片段的来源文件必须为 `extracted` 或 `reviewed`。其他状态的来源文件会被跳过，按来源文件报告 `SOURCE_FILE_NOT_READY`，其中包含状态及跳过数量。跳过片段时结果为 `partial`，`indexed_count` 只统计实际写入的片段，即使全部跳过也一样。仅用于溯源的原件不受片段来源状态限制。

只有标点等不可检索内容的片段会被跳过，并报告 `TOKENLESS_CHUNKS_SKIPPED`。受信任的入库调用提交同一资料版本的 `blocked` 或 `review_only` 状态时，索引器先撤下对应的旧快照。新包的其余内容仍需通过公共契约校验，校验失败会照常报错。

检索先筛选 `enabled` 版本，再按可选的业务方向和主分类过滤。只用筛选后的片段计算 BM25。正文和问题经 NFKC 归一化，连续汉字按相邻两字切词，单个汉字及其他字母数字词保留。片段按分数降序排列，同分按片段 UUID 排序。返回最多 `top_k` 条正分结果，包含正文、标题、官方来源字段、日期、核验状态和已有定位。BM25 分数用于排序，不能解释为置信度。

索引成功不会改动开放或核验状态。`enabled` 仍须通过公共模型约定的首版纳入、来源核验、正文提取和时效状态检查。真实资料的人工核验和开放决定由上游负责。索引器保留已核验历史资料的原时效标签，Agent 仍需判断是否适用于当前政策答复。

## 运行与结果

在仓库根目录使用项目后端环境。

```bash
python -m pip install -r backend/requirements-dev.txt
python -X utf8 -m scripts.demo_local_retrieval
python -X utf8 -m scripts.demo_local_retrieval --real
python -X utf8 -m unittest discover -s tests -v
```

| 测试问题 | 数据和条件 | 实际结果 |
| --- | --- | --- |
| 星桥奖学金申请需要什么 | 合成资料，奖学金分类，`top_k=2` | “提交申请表和实践记录”片段 3.680293，公示片段 0.747269 |
| 星桥奖学金申请需要什么 | 同上，`top_k=1` | 仅返回第 2 行的申请片段，保留第 1 页的原件定位 |
| 云帆竞赛认定 | 合成资料，竞赛业务方向 | 参赛证明和获奖记录片段，1.438410 |
| 月面推免 | 仅未开放合成资料含该词 | `[]` |
| 量子纠缠 | 无匹配词 | `[]` |
| 竞赛认定、奖学金、推免 | 丁晓炜的真实资料包，分别索引 13、4、6 个片段 | 三次均为 `[]` |

[合成包](examples/retrieval-synthetic-packages.json)使用 `example.invalid` 作为虚构来源。[合成查询日志](evidence/retrieval-synthetic.json)记录完整结果。[真实包日志](evidence/retrieval-real-blocked.json)记录三个包的索引状态、文件数及空结果。

[PowerShell 验收截图](evidence/retrieval-powershell.png)记录了合成奖学金命中与 `top_k`、真实资料索引后的零命中，以及补充来源状态校验前的 12 项检索测试结果。

[后端测试记录](evidence/retrieval-tests.txt)在同步 `main`（`0046612`）后重新生成。共 171 项，170 项通过，1 项因 Windows 当前账户无法创建符号链接而跳过，0 失败。18 项检索测试覆盖排序、追溯、过滤、文件损坏、重建撤回和真实资料隔离，也验证了来源文件就绪状态、撤回包损坏、无可检索词和缺失文件仍被引用的边界。原数据库设计的 ORM 和导入规则 21 项测试也通过。

## 联调与接入

丁晓炜的三个真实包可直接从 `knowledge_base/processed/alpha/` 读取。服务启动时创建一个索引实例，解析器或包加载任务写入它，Agent 从同一个实例读取。真实包需传入受控根目录以启用文件校验。预期的业务结果 `[]` 可映射为 Agent 的证据不足响应。

```python
from pathlib import Path

from backend.contracts import DocumentPackage, KnowledgeIndexer, RetrievalRequest, Retriever
from backend.retrieval import LocalBM25Retriever

async def index_and_retrieve(root: Path, package_path: Path, query: str):
    store = LocalBM25Retriever(file_root=root)
    indexer: KnowledgeIndexer = store
    retriever: Retriever = store
    package = DocumentPackage.model_validate_json(package_path.read_bytes())
    indexed = await indexer.index_document(package)
    hits = await retriever.retrieve(RetrievalRequest(query=query, top_k=5))
    return indexed, hits
```

将 `store` 作为 `retriever` 传入吴诗莹的 `AgentWorkflow` 即可。联调脚本直接导入当前工作区中已合入 `main` 的 `backend.services.agent_workflow.AgentWorkflow`。三项真实资料查询均得到 `insufficient_evidence`，且模型调用次数为 0。合成奖学金查询得到一条引用，标题、来源、整理稿定位及原件定位均与片段一致。联调使用固定模型替身及测试用追问和适用性回调。[Agent 联调记录](evidence/retrieval-agent-check.txt)。

在仓库根目录复跑四项 Agent 联调用例。

```bash
python -X utf8 -m scripts.check_retrieval_agent
```

### 统一加载入口与只读元数据查询（PR #35）

为配合后端组装、Agent 与业务规则的正式联调，检索模块补充了统一加载入口与只读查询方法，不修改公共契约字段或协议签名：

- `load_approved_alpha_retriever(corpus_dir=DEFAULT_APPROVED_DIR, file_root=PROJECT_ROOT, allow_missing=True) -> tuple[LocalBM25Retriever, AlphaCorpusLoadReport]`：仅加载 `approved/` 下通过人工审核且 `retrieval_status=enabled` 的资料包，支持 `manifest.json` 或目录直扫（自动忽略 `summary.json` 与 `*.metadata.json` 旁路文件）。
- `build_approved_alpha_retriever(...) -> LocalBM25Retriever`：便捷封装，直接返回 `Retriever`，但会丢弃 `AlphaCorpusLoadReport`。
- `LocalBM25Retriever.get_document_metadata(version_id: UUID)`（调用示例：`retriever.get_document_metadata(chunk.version_id)`）与 `get_parsed_chunk(chunk_id: UUID)`（调用示例：`retriever.get_parsed_chunk(chunk.chunk_id)`）：供业务规则侧通过闭包绑定只读读取文档元数据与原始片段（含 `locator_note`）；返回深拷贝，对象不存在、所属版本未开放（`blocked`/`review_only`）或重索引剔除时统一返回 `None`，不抛异常。

**正式组装加载边界约定**：
- `load_approved_alpha_retriever()` 会将所有非 `failed` 的包计入 `report.loaded_packages`，包括 `IndexingStatus.PARTIAL`（例如来源文件处于 `needs_ocr` 等未就绪状态导致 `indexed_count=0`）。未就绪片段绝不会被检索，但 `loaded_packages` 非空并不等同于“包已完整可用于正式问答”。
- `allow_missing=True`（默认）在 `approved/` 目录尚不存在时返回空索引与空报告，不抛异常；此时空报告中的 `index_results`、`warnings` 和 `total_indexed_chunks=0` 与“目录存在但为空”表现一致，因此正式后端组装不能仅凭这三项为空就判定知识库正常。
- 正式后端组装（`backend.app.alpha:app`）应调用 `load_approved_alpha_retriever(..., allow_missing=False)`（或在保留 `allow_missing=True` 时显式检查 `report.corpus_dir.is_dir()`），而非会丢弃报告的 `build_approved_alpha_retriever()`；并核对 `report.index_results`（按当前保守约定要求完整 `IndexingStatus.INDEXED`）、`warnings` 与 `report.total_indexed_chunks`，由组装层与 Agent 明确区分“知识库目录缺失/未就绪”与“正常无命中”。
- 未来届别/历史政策场景下，BM25 按词命中旧年度通知不视为检索错误；检索侧确保保留准确来源与年度元数据，由业务规则按当前保守门禁（`current-only`）拒绝错年度或历史片段，最终 Agent 返回 `insufficient_evidence`、空引用且模型调用 0 次。

## 当前限制

内存索引随进程结束消失，查询逐片扫描，面向 Alpha 的小资料集。字面匹配可能遗漏同义表达，也可能因共用词命中弱相关片段。当前没有自动核验政策、判断个人适用范围、跟踪授权更新或持久化版本的功能。上游状态变更须提交给同一内存实例才能生效。正式部署仍需接入经审核的资料来源及状态同步。
