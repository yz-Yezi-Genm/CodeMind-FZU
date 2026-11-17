# Backend 接口骨架

本目录当前提供 CodeMind-FZU Alpha 阶段的公共 Pydantic v2 数据模型、Python Protocol 接口、最小 FastAPI 契约入口和 Markdown/TXT 离线文档解析，不包含真实 Agent、数据库、向量检索、Qwen 调用或管理端业务实现。

## 环境与启动

从仓库根目录执行：

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload
```

访问：
- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- OpenAPI 页面：`http://127.0.0.1:8000/docs`
- 问答入口：`POST http://127.0.0.1:8000/api/v1/ask`

健康检查可直接运行。问答入口在注入真实 `AgentService` 前会返回统一格式的 `503 SERVICE_NOT_CONFIGURED`，不会返回伪造回答。

## 公共契约

- `contracts/models.py`：请求、响应、引用、检索片段、资料入库包、索引结果及模型调用数据结构。
- `contracts/protocols.py`：Agent、Retriever、DocumentParser、KnowledgeIndexer、LLMClient 和 DocumentAdminService 的模块边界。
- 完整说明见 [Alpha 接口规范 V1.0](../docs/assignment-03/interface-contract-v1.md)。

各成员应直接复用公共模型，不要在自己的模块中复制定义同名 DTO。公共字段、状态值或函数签名需要修改时，先向罗宇泽提出并等待统一更新。

## 文档解析（Alpha）

`backend.document_processing.TextDocumentParser` 实现现有 `DocumentParser` 协议，返回公共 `DocumentPackage`。支持 Markdown/TXT、标题层级、片段编号、行号/字符定位和哈希；输出全部保持 `retrieval_status=blocked`。PDF及其他格式仅登记待处理，不伪造正文。

```bash
python -m scripts.parse_alpha_documents
python -m scripts.check_document_processing
```

三个场景样例位于 `knowledge_base/processed/alpha/`，使用2026竞赛级别认定、2026奖学金办法及学院2027届本科推免推荐方案的已有正文提取稿，共23片段。完整使用方法、核验边界和索引交接见 [文档处理说明](../docs/assignment-03/alpha/document-processing.md)。正文提取稿仍待政策与附件核验，实际索引联调尚未完成。

## 当前未实现内容

- Agent 工作流和对话历史持久化；
- Qwen 真实调用及密钥配置；
- PDF/OCR与复杂附件解析、文件存储服务和资料实际入库；
- PostgreSQL/SQLAlchemy 在线连接与迁移；
- Chroma、BM25、RRF 实际检索；
- 管理端业务 API 和认证授权。

数据库设计中的资料默认 `retrieval_status=blocked`。解析、入库或建立索引均不会自动开放正式问答检索。
