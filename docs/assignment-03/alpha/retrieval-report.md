# Alpha 本地知识检索报告

2026-11-18 · 数据库与检索

本地检索已打通 `DocumentPackage → IndexResult → list[RetrievedChunk]`。竞赛认定、奖学金和推免的三个真实资料包共 23 个片段，文件及登记的 SHA-256 校验通过。三个包均保持 `blocked`，用对应问题检索均返回 `[]`。已有 Alpha V1 公共接口足够支持这条数据流，无需调整字段、状态或签名。

## 检索方法

索引器用公共模型重新验证包的快照，检查文件键、源文件和原件引用，以及文件内的片段序号。配置受控 `file_root` 时会检查文件能否读取，并比对已登记的原始字节 SHA-256。文件缺失或哈希不符时返回 `failed` 和 warnings，同时清除该版本的旧索引。重复导入同一版本会替换旧快照，片段身份按资料编号、版本号、来源文件及片段序号确定。本地 UUID 可复现，接入持久化时需要与数据库身份映射。

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

[后端测试记录](evidence/retrieval-tests.txt)共 81 项，80 项通过，1 项因 Windows 当前账户无法创建符号链接而跳过，0 失败。新增检索测试 12 项，覆盖排序、跨文件片段身份、追溯、过滤、文件损坏、重建撤回和真实资料隔离。原数据库设计的 ORM 和导入规则 21 项测试也通过。

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

将 `store` 作为 `retriever` 传入吴诗莹的 `AgentWorkflow` 即可。已用她的工作分支提交 `ed50c69` 做离线联调。三项真实资料查询均得到 `insufficient_evidence`，且模型调用次数为 0。合成奖学金查询得到一条引用，标题、来源、整理稿定位及原件定位均与片段一致。联调使用固定模型替身及测试用追问和适用性回调。[Agent 联调记录](evidence/retrieval-agent-check.txt)。

在仓库根目录复跑四项 Agent 联调用例。已获取对应 Git 提交时，可以直接运行第二条命令。

```bash
git fetch origin feat/alpha-agent-workflow-wushiying
python -X utf8 -m scripts.check_retrieval_agent
```

## 当前限制

内存索引随进程结束消失，查询逐片扫描，面向 Alpha 的小资料集。字面匹配可能遗漏同义表达，也可能因共用词命中弱相关片段。当前没有自动核验政策、判断个人适用范围、跟踪授权更新或持久化版本的功能。上游撤回开放后须重新导入同一版本才能更新内存状态。正式部署仍需接入经审核的资料来源及状态同步。
