# ORM映射说明 v1.2

本版以 PostgreSQL 和 SQLAlchemy 2 作为数据库设计的候选技术基线，具体技术选型及首版部署方案待技术架构负责人确认。本次已完成关系数据模型、DDL 和 ORM 映射设计，但尚未部署实际数据库，也未接入 Agent。

候选ORM方案采用SQLAlchemy 2命令式映射。models.py为可导入的模型源文件，不连接数据库。字段名与列名一致，不额外制造别名；关系属性用于对象导航，底层外键/约束为最终依据。

|实体类|表名|主键|
|---|---|---|
|KnowledgeCategory|knowledge_categories|id|
|KnowledgeDocument|knowledge_documents|id|
|DocumentVersion|document_versions|id|
|DocumentFile|document_files|id|
|ApplicabilityRule|applicability_rules|id|
|ApplicabilityRuleValue|applicability_rule_values|rule_id, dimension, value|
|KnowledgeChunk|knowledge_chunks|id|
|BusinessDirection|business_directions|id|
|DocumentBusinessDirection|document_business_directions|document_id, direction_id|
|VerificationRecord|verification_records|id|
|VerificationTask|verification_tasks|id|
|User|users|id|
|ConversationSession|conversation_sessions|id|
|InteractionMessage|interaction_messages|id|
|AgentTask|agent_tasks|id|
|TaskResult|task_results|id|
|ResultCitation|result_citations|id|
|DocumentMilestone|document_milestones|id|
|DocumentFileSource|document_file_sources|file_id, source_file_id|
|MessageResultLink|message_result_links|message_id, result_id|
|DocumentVersionRelation|document_version_relations|from_version_id, to_version_id, relation_type|
|AnswerFeedback|answer_feedback|id|
|FeedbackReviewLink|feedback_review_links|feedback_id, verification_task_id|

## 对象关联

KnowledgeDocument.category、DocumentVersion.document、DocumentFile.version、ApplicabilityRule.version、ApplicabilityRuleValue.rule、KnowledgeChunk.file、DocumentBusinessDirection.document/direction、ConversationSession.user、InteractionMessage.session、AgentTask.request_message、TaskResult.task、ResultCitation.result/chunk、DocumentMilestone.version、DocumentFileSource.file/source_file、MessageResultLink.message/result均已映射。其余关联通过明确外键查询，未承诺所有反向collection均存在。

## 写入示例

```python
from sqlalchemy.orm import Session
from models import KnowledgeCategory, KnowledgeDocument, DocumentVersion
# engine由架构层配置，本文件不包含连接凭据
with Session(engine) as session, session.begin():
    category = KnowledgeCategory(name="示例分类", sort_order=99)
    document = KnowledgeDocument(category=category, title="示例政策", document_type="政策")
    version = DocumentVersion(document=document, record_code="示例-001",
        version_no="import-1", source_url="https://example.edu/policy")
    session.add(version)
# 默认检索blocked；生产入库使用已有七分类，不重复创建示例分类
```

写入时区使用UTC存储时刻、展示按Asia/Shanghai转换；政策生效等日历日期使用DATE。UUID默认由uuid4生成。组合主键关联类无单独id。禁止依赖ORM级联删除政策证据；updated_at需业务服务维护。

## 实现边界

ORM源文件及表结构已生成并通过本地可移植约束测试；数据库部署、业务服务、Agent接入、认证接入、向量检索及在线迁移尚未实施。PostgreSQL专属DDL仅经编译/语法解析，不冒充实库集成测试。

依据：[SQLAlchemy官方映射文档](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html)、[组合外键](https://docs.sqlalchemy.org/en/20/core/constraints.html#defining-foreign-keys)。
