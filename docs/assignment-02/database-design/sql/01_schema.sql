-- 审核稿；PostgreSQL；只在空的专用数据库/Schema审核后执行。UUID由调用端提供。
BEGIN;
CREATE TABLE knowledge_categories (
	id UUID NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	description TEXT, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_knowledge_categories PRIMARY KEY (id), 
	CONSTRAINT uq_knowledge_categories_name UNIQUE (name)
);

COMMENT ON TABLE knowledge_categories IS '七类原始知识主题';

COMMENT ON COLUMN knowledge_categories.id IS '内部UUID；应用生成';

COMMENT ON COLUMN knowledge_categories.name IS '原始分类名称';

COMMENT ON COLUMN knowledge_categories.description IS '分类说明';

COMMENT ON COLUMN knowledge_categories.sort_order IS '显示顺序';

COMMENT ON COLUMN knowledge_categories.created_at IS '创建时间';

COMMENT ON COLUMN knowledge_categories.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE business_directions (
	id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	delivery_stage VARCHAR(16) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_business_directions PRIMARY KEY (id), 
	CONSTRAINT ck_business_directions_delivery_stage_values CHECK (delivery_stage IN ('v1', 'future')), 
	CONSTRAINT uq_business_directions_code UNIQUE (code), 
	CONSTRAINT uq_business_directions_name UNIQUE (name)
);

COMMENT ON TABLE business_directions IS '五大业务方向';

COMMENT ON COLUMN business_directions.id IS '内部UUID；应用生成';

COMMENT ON COLUMN business_directions.code IS '固定业务代码';

COMMENT ON COLUMN business_directions.name IS '业务方向名称';

COMMENT ON COLUMN business_directions.delivery_stage IS '交付阶段';

COMMENT ON COLUMN business_directions.sort_order IS '展示顺序';

COMMENT ON COLUMN business_directions.created_at IS '创建时间';

COMMENT ON COLUMN business_directions.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE users (
	id UUID NOT NULL, 
	external_subject VARCHAR(256), 
	display_name VARCHAR(128), 
	status VARCHAR(32) DEFAULT 'active' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT ck_users_status_values CHECK (status IN ('active', 'disabled', 'anonymized')), 
	CONSTRAINT uq_users_external_subject UNIQUE (external_subject)
);

COMMENT ON TABLE users IS '最小用户身份；无密码及成长档案';

COMMENT ON COLUMN users.id IS '内部UUID；应用生成';

COMMENT ON COLUMN users.external_subject IS '外部认证主体；未接入则空';

COMMENT ON COLUMN users.display_name IS '展示名称';

COMMENT ON COLUMN users.status IS '用户状态';

COMMENT ON COLUMN users.created_at IS '创建时间';

COMMENT ON COLUMN users.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE knowledge_documents (
	id UUID NOT NULL, 
	category_id UUID NOT NULL, 
	title VARCHAR(512) NOT NULL, 
	document_type VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_knowledge_documents PRIMARY KEY (id), 
	CONSTRAINT fk_knowledge_documents_category_id_knowledge_categories FOREIGN KEY(category_id) REFERENCES knowledge_categories (id) ON DELETE RESTRICT
);

CREATE INDEX ix_documents_category ON knowledge_documents (category_id);

COMMENT ON TABLE knowledge_documents IS '政策或通知的逻辑身份';

COMMENT ON COLUMN knowledge_documents.id IS '内部UUID；应用生成';

COMMENT ON COLUMN knowledge_documents.category_id IS '所属原始主分类';

COMMENT ON COLUMN knowledge_documents.title IS '逻辑文档标题';

COMMENT ON COLUMN knowledge_documents.document_type IS '资料类型';

COMMENT ON COLUMN knowledge_documents.created_at IS '创建时间';

COMMENT ON COLUMN knowledge_documents.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE conversation_sessions (
	id UUID NOT NULL, 
	user_id UUID, 
	title VARCHAR(256), 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_conversation_sessions PRIMARY KEY (id), 
	CONSTRAINT ck_conversation_sessions_session_time_order CHECK (ended_at IS NULL OR ended_at >= started_at), 
	CONSTRAINT fk_conversation_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_sessions_user_start ON conversation_sessions (user_id, started_at);

COMMENT ON TABLE conversation_sessions IS '会话；支持匿名';

COMMENT ON COLUMN conversation_sessions.id IS '内部UUID；应用生成';

COMMENT ON COLUMN conversation_sessions.user_id IS '用户；匿名为空';

COMMENT ON COLUMN conversation_sessions.title IS '会话标题';

COMMENT ON COLUMN conversation_sessions.started_at IS '开始时间';

COMMENT ON COLUMN conversation_sessions.ended_at IS '结束时间';

COMMENT ON COLUMN conversation_sessions.created_at IS '创建时间';

COMMENT ON COLUMN conversation_sessions.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE document_versions (
	id UUID NOT NULL, 
	document_id UUID NOT NULL, 
	record_code VARCHAR(128) NOT NULL, 
	version_no VARCHAR(64) NOT NULL, 
	publisher VARCHAR(256), 
	responsible_department VARCHAR(256), 
	document_number VARCHAR(128), 
	source_url TEXT NOT NULL, 
	published_on DATE, 
	issued_on DATE, 
	effective_on DATE, 
	deadline_on DATE, 
	document_written_on DATE, 
	source_page_published_on DATE, 
	source_verified_on DATE, 
	timeliness_verified_on DATE, 
	local_checked_on DATE, 
	legacy_last_verified_on DATE, 
	source_page_url TEXT, 
	applicability_raw JSONB, 
	policy_status VARCHAR(128) DEFAULT '待核验' NOT NULL, 
	source_verification_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	timeliness_verification_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	extraction_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	attachment_status VARCHAR(32) DEFAULT 'not_registered' NOT NULL, 
	v1_inclusion_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	retrieval_status VARCHAR(32) DEFAULT 'blocked' NOT NULL, 
	inclusion_reason TEXT, 
	verification_note TEXT, 
	legacy_verification_text TEXT, 
	import_snapshot JSONB, 
	temporal_notes JSONB, 
	deadline_status VARCHAR(32) DEFAULT 'unknown' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_document_versions PRIMARY KEY (id), 
	CONSTRAINT ck_document_versions_deadline_status_values CHECK (deadline_status IN ('unknown', 'unstructured', 'structured', 'none')), 
	CONSTRAINT uq_document_versions_document_id_version_no UNIQUE (document_id, version_no), 
	CONSTRAINT ck_document_versions_source_verification_status_values CHECK (source_verification_status IN ('pending', 'partial', 'verified', 'failed')), 
	CONSTRAINT ck_document_versions_timeliness_verification_status_values CHECK (timeliness_verification_status IN ('pending', 'current', 'historical', 'superseded', 'expired', 'uncertain')), 
	CONSTRAINT ck_document_versions_extraction_status_values CHECK (extraction_status IN ('pending', 'extracted', 'needs_ocr', 'failed')), 
	CONSTRAINT ck_document_versions_attachment_status_values CHECK (attachment_status IN ('not_registered', 'pending', 'partial', 'parsed', 'reviewed', 'failed')), 
	CONSTRAINT ck_document_versions_v1_inclusion_status_values CHECK (v1_inclusion_status IN ('included', 'excluded', 'pending')), 
	CONSTRAINT ck_document_versions_retrieval_status_values CHECK (retrieval_status IN ('blocked', 'review_only', 'enabled')), 
	CONSTRAINT ck_document_versions_enable_prerequisites CHECK (retrieval_status <> 'enabled' OR (v1_inclusion_status='included' AND source_verification_status='verified' AND extraction_status='extracted' AND timeliness_verification_status IN ('current','historical','superseded','expired'))), 
	CONSTRAINT fk_document_versions_document_id_knowledge_documents FOREIGN KEY(document_id) REFERENCES knowledge_documents (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_document_versions_record_code UNIQUE (record_code)
);

CREATE INDEX ix_versions_answer_filter ON document_versions (v1_inclusion_status, retrieval_status, timeliness_verification_status);

COMMENT ON TABLE document_versions IS '确定内容的版本与原登记元数据';

COMMENT ON COLUMN document_versions.id IS '内部UUID；应用生成';

COMMENT ON COLUMN document_versions.document_id IS '所属文档';

COMMENT ON COLUMN document_versions.record_code IS '原资料编号；全局保留';

COMMENT ON COLUMN document_versions.version_no IS '文档内部版本标识';

COMMENT ON COLUMN document_versions.publisher IS '发布单位';

COMMENT ON COLUMN document_versions.responsible_department IS '负责部门';

COMMENT ON COLUMN document_versions.document_number IS '文号';

COMMENT ON COLUMN document_versions.source_url IS '登记的官方来源网址；存在不等于已核验';

COMMENT ON COLUMN document_versions.published_on IS '发布日期';

COMMENT ON COLUMN document_versions.issued_on IS '印发日期';

COMMENT ON COLUMN document_versions.effective_on IS '生效日期';

COMMENT ON COLUMN document_versions.deadline_on IS '截止日期';

COMMENT ON COLUMN document_versions.document_written_on IS '文件成文日期';

COMMENT ON COLUMN document_versions.source_page_published_on IS '来源页面发布日期';

COMMENT ON COLUMN document_versions.source_verified_on IS '来源实际核验日期';

COMMENT ON COLUMN document_versions.timeliness_verified_on IS '时效实际核验日期';

COMMENT ON COLUMN document_versions.local_checked_on IS '本地检查日期';

COMMENT ON COLUMN document_versions.legacy_last_verified_on IS '原最后核验日期；不推断核验维度';

COMMENT ON COLUMN document_versions.source_page_url IS '附件来源页面';

COMMENT ON COLUMN document_versions.applicability_raw IS '适用年级/专业/对象原文';

COMMENT ON COLUMN document_versions.policy_status IS '原登记政策状态；未复核不得当现行结论';

COMMENT ON COLUMN document_versions.source_verification_status IS '来源核验';

COMMENT ON COLUMN document_versions.timeliness_verification_status IS '政策时效核验';

COMMENT ON COLUMN document_versions.extraction_status IS '正文提取';

COMMENT ON COLUMN document_versions.attachment_status IS '版本附件处理汇总';

COMMENT ON COLUMN document_versions.v1_inclusion_status IS '首版资料范围纳入状态';

COMMENT ON COLUMN document_versions.retrieval_status IS '检索开放状态';

COMMENT ON COLUMN document_versions.inclusion_reason IS '首版纳入或排除理由';

COMMENT ON COLUMN document_versions.verification_note IS '当前核查说明';

COMMENT ON COLUMN document_versions.legacy_verification_text IS '原混合核验状态原文';

COMMENT ON COLUMN document_versions.import_snapshot IS '原CSV全部37列；不可丢失或覆盖';

COMMENT ON COLUMN document_versions.temporal_notes IS '不能安全转换成单一DATE的期限和年级生效原文';

COMMENT ON COLUMN document_versions.deadline_status IS '期限结构化状态；空日期不能视为无期限';

COMMENT ON COLUMN document_versions.created_at IS '创建时间';

COMMENT ON COLUMN document_versions.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE document_business_directions (
	document_id UUID NOT NULL, 
	direction_id UUID NOT NULL, 
	mapping_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_document_business_directions PRIMARY KEY (document_id, direction_id), 
	CONSTRAINT fk_document_business_directions_document_id_knowledge_documents FOREIGN KEY(document_id) REFERENCES knowledge_documents (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_document_business_directions_direction_id_business_d_b3a9 FOREIGN KEY(direction_id) REFERENCES business_directions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_document_directions_reverse ON document_business_directions (direction_id, document_id);

COMMENT ON TABLE document_business_directions IS '文档业务方向多标签';

COMMENT ON COLUMN document_business_directions.document_id IS '文档';

COMMENT ON COLUMN document_business_directions.direction_id IS '业务方向';

COMMENT ON COLUMN document_business_directions.mapping_reason IS '分类依据';

COMMENT ON COLUMN document_business_directions.created_at IS '创建时间';

COMMENT ON COLUMN document_business_directions.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE interaction_messages (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	sequence_no INTEGER NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	content TEXT NOT NULL, 
	sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_interaction_messages PRIMARY KEY (id), 
	CONSTRAINT uq_interaction_messages_session_id_sequence_no UNIQUE (session_id, sequence_no), 
	CONSTRAINT uq_interaction_messages_id_session_id_role UNIQUE (id, session_id, role), 
	CONSTRAINT ck_interaction_messages_message_sequence_positive CHECK (sequence_no>0), 
	CONSTRAINT ck_interaction_messages_role_values CHECK (role IN ('user', 'assistant', 'system')), 
	CONSTRAINT fk_interaction_messages_session_id_conversation_sessions FOREIGN KEY(session_id) REFERENCES conversation_sessions (id) ON DELETE RESTRICT
);

COMMENT ON TABLE interaction_messages IS '用户与助手交互消息';

COMMENT ON COLUMN interaction_messages.id IS '内部UUID；应用生成';

COMMENT ON COLUMN interaction_messages.session_id IS '所属会话';

COMMENT ON COLUMN interaction_messages.sequence_no IS '会话内消息序号';

COMMENT ON COLUMN interaction_messages.role IS '消息角色';

COMMENT ON COLUMN interaction_messages.content IS '消息内容';

COMMENT ON COLUMN interaction_messages.sent_at IS '发送时间';

COMMENT ON COLUMN interaction_messages.created_at IS '创建时间';

COMMENT ON COLUMN interaction_messages.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE document_files (
	id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	file_role VARCHAR(32) NOT NULL, 
	storage_key TEXT NOT NULL, 
	original_name VARCHAR(512) NOT NULL, 
	media_type VARCHAR(128), 
	sha256 VARCHAR(64), 
	source_url TEXT, 
	processing_status VARCHAR(32) DEFAULT 'saved' NOT NULL, 
	processing_note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_document_files PRIMARY KEY (id), 
	CONSTRAINT uq_document_files_id_version_id UNIQUE (id, version_id), 
	CONSTRAINT ck_document_files_file_role_values CHECK (file_role IN ('original', 'attachment', 'extracted', 'curated')), 
	CONSTRAINT ck_document_files_processing_status_values CHECK (processing_status IN ('saved', 'extracted', 'needs_ocr', 'reviewed', 'failed')), 
	CONSTRAINT ck_document_files_sha256_length CHECK (sha256 IS NULL OR length(sha256)=64), 
	CONSTRAINT fk_document_files_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_document_files_storage_key UNIQUE (storage_key)
);

CREATE INDEX ix_files_version_role ON document_files (version_id, file_role);

COMMENT ON TABLE document_files IS '原始网页、附件、正文及整理稿';

COMMENT ON COLUMN document_files.id IS '内部UUID；应用生成';

COMMENT ON COLUMN document_files.version_id IS '所属版本';

COMMENT ON COLUMN document_files.file_role IS '文件角色';

COMMENT ON COLUMN document_files.storage_key IS '受控相对路径或对象存储键';

COMMENT ON COLUMN document_files.original_name IS '原始文件名';

COMMENT ON COLUMN document_files.media_type IS 'MIME类型';

COMMENT ON COLUMN document_files.sha256 IS '小写SHA-256；未知不伪造';

COMMENT ON COLUMN document_files.source_url IS '具体文件来源网址';

COMMENT ON COLUMN document_files.processing_status IS '单文件处理状态';

COMMENT ON COLUMN document_files.processing_note IS '文件解析及复核说明';

COMMENT ON COLUMN document_files.created_at IS '创建时间';

COMMENT ON COLUMN document_files.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE applicability_rules (
	id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	purpose VARCHAR(128) NOT NULL, 
	enrollment_mode VARCHAR(32) DEFAULT 'unknown' NOT NULL, 
	graduation_mode VARCHAR(32) DEFAULT 'unknown' NOT NULL, 
	major_mode VARCHAR(32) DEFAULT 'unknown' NOT NULL, 
	student_type_mode VARCHAR(32) DEFAULT 'unknown' NOT NULL, 
	source_locator TEXT, 
	verification_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_applicability_rules PRIMARY KEY (id), 
	CONSTRAINT ck_applicability_rules_enrollment_mode_values CHECK (enrollment_mode IN ('unknown', 'all', 'include')), 
	CONSTRAINT ck_applicability_rules_graduation_mode_values CHECK (graduation_mode IN ('unknown', 'all', 'include')), 
	CONSTRAINT ck_applicability_rules_major_mode_values CHECK (major_mode IN ('unknown', 'all', 'include')), 
	CONSTRAINT ck_applicability_rules_student_type_mode_values CHECK (student_type_mode IN ('unknown', 'all', 'include')), 
	CONSTRAINT ck_applicability_rules_verification_status_values CHECK (verification_status IN ('pending', 'verified', 'failed')), 
	CONSTRAINT fk_applicability_rules_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_rules_version_purpose ON applicability_rules (version_id, purpose);

COMMENT ON TABLE applicability_rules IS '适用规则；同用途多条OR';

COMMENT ON COLUMN applicability_rules.id IS '内部UUID；应用生成';

COMMENT ON COLUMN applicability_rules.version_id IS '所属版本';

COMMENT ON COLUMN applicability_rules.purpose IS '规则适用用途';

COMMENT ON COLUMN applicability_rules.enrollment_mode IS 'enrollment_mode：未知/全体/指定值';

COMMENT ON COLUMN applicability_rules.graduation_mode IS 'graduation_mode：未知/全体/指定值';

COMMENT ON COLUMN applicability_rules.major_mode IS 'major_mode：未知/全体/指定值';

COMMENT ON COLUMN applicability_rules.student_type_mode IS 'student_type_mode：未知/全体/指定值';

COMMENT ON COLUMN applicability_rules.source_locator IS '规则原文位置';

COMMENT ON COLUMN applicability_rules.verification_status IS '规则是否经人工核实';

COMMENT ON COLUMN applicability_rules.created_at IS '创建时间';

COMMENT ON COLUMN applicability_rules.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE agent_tasks (
	id UUID NOT NULL, 
	request_message_id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	request_role VARCHAR(16) DEFAULT 'user' NOT NULL, 
	task_type VARCHAR(64) NOT NULL, 
	status VARCHAR(32) DEFAULT 'queued' NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR(64), 
	error_summary TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_agent_tasks PRIMARY KEY (id), 
	CONSTRAINT ck_agent_tasks_request_is_user CHECK (request_role='user'), 
	CONSTRAINT fk_agent_tasks_request_message_id_session_id_request_ro_6543 FOREIGN KEY(request_message_id, session_id, request_role) REFERENCES interaction_messages (id, session_id, role) ON DELETE RESTRICT, 
	CONSTRAINT uq_agent_tasks_id_session_id UNIQUE (id, session_id), 
	CONSTRAINT ck_agent_tasks_status_values CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')), 
	CONSTRAINT ck_agent_tasks_terminal_time CHECK ((status IN ('succeeded','failed','cancelled') AND finished_at IS NOT NULL) OR (status IN ('queued','running') AND finished_at IS NULL)), 
	CONSTRAINT ck_agent_tasks_failure_reason CHECK (status <> 'failed' OR error_summary IS NOT NULL), 
	CONSTRAINT ck_agent_tasks_started_required CHECK (status NOT IN ('running','succeeded') OR started_at IS NOT NULL), 
	CONSTRAINT ck_agent_tasks_task_time_order CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at), 
	CONSTRAINT fk_agent_tasks_session_id_conversation_sessions FOREIGN KEY(session_id) REFERENCES conversation_sessions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_agent_tasks_status ON agent_tasks (status, created_at);

CREATE INDEX ix_agent_tasks_request ON agent_tasks (request_message_id);

COMMENT ON TABLE agent_tasks IS '由用户消息触发的Agent任务';

COMMENT ON COLUMN agent_tasks.id IS '内部UUID；应用生成';

COMMENT ON COLUMN agent_tasks.request_message_id IS '触发用户消息';

COMMENT ON COLUMN agent_tasks.session_id IS '触发会话；用于跨表一致性约束';

COMMENT ON COLUMN agent_tasks.request_role IS '约束触发消息必须是user';

COMMENT ON COLUMN agent_tasks.task_type IS '任务类型；首版业务代码';

COMMENT ON COLUMN agent_tasks.status IS '执行状态';

COMMENT ON COLUMN agent_tasks.started_at IS '执行开始时间';

COMMENT ON COLUMN agent_tasks.finished_at IS '执行结束时间';

COMMENT ON COLUMN agent_tasks.error_code IS '错误代码';

COMMENT ON COLUMN agent_tasks.error_summary IS '错误摘要；不保存密钥';

COMMENT ON COLUMN agent_tasks.created_at IS '创建时间';

COMMENT ON COLUMN agent_tasks.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE document_milestones (
	id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	name VARCHAR(256) NOT NULL, 
	raw_text TEXT NOT NULL, 
	precision VARCHAR(16) NOT NULL, 
	due_on DATE, 
	due_at TIMESTAMP WITH TIME ZONE, 
	timezone_name VARCHAR(64), 
	verification_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_document_milestones PRIMARY KEY (id), 
	CONSTRAINT ck_document_milestones_precision_values CHECK (precision IN ('date', 'time', 'unknown')), 
	CONSTRAINT ck_document_milestones_verification_status_values CHECK (verification_status IN ('pending', 'verified', 'failed')), 
	CONSTRAINT ck_document_milestones_time_precision CHECK ((precision='date' AND due_on IS NOT NULL AND due_at IS NULL) OR (precision='time' AND due_on IS NULL AND due_at IS NOT NULL AND timezone_name IS NOT NULL) OR (precision='unknown' AND due_on IS NULL AND due_at IS NULL)), 
	CONSTRAINT fk_document_milestones_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_milestones_due_date ON document_milestones (due_on);

CREATE INDEX ix_milestones_due_time ON document_milestones (due_at);

CREATE INDEX ix_milestones_version ON document_milestones (version_id);

COMMENT ON TABLE document_milestones IS '版本的多个办理节点；原文与时间精度分别保存';

COMMENT ON COLUMN document_milestones.id IS '内部UUID；应用生成';

COMMENT ON COLUMN document_milestones.version_id IS '所属版本';

COMMENT ON COLUMN document_milestones.name IS '办理节点名称';

COMMENT ON COLUMN document_milestones.raw_text IS '节点完整原文';

COMMENT ON COLUMN document_milestones.precision IS 'date/time/unknown';

COMMENT ON COLUMN document_milestones.due_on IS '只精确到日期的截止日';

COMMENT ON COLUMN document_milestones.due_at IS '精确截止时刻；时区感知';

COMMENT ON COLUMN document_milestones.timezone_name IS '原办理时间所用时区，精确时刻必填';

COMMENT ON COLUMN document_milestones.verification_status IS '时间转换后仍需核实原文';

COMMENT ON COLUMN document_milestones.created_at IS '创建时间';

COMMENT ON COLUMN document_milestones.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE document_version_relations (
	from_version_id UUID NOT NULL, 
	to_version_id UUID NOT NULL, 
	relation_type VARCHAR(32) NOT NULL, 
	effective_on DATE, 
	evidence_note TEXT NOT NULL, 
	evidence_url TEXT, 
	verification_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_document_version_relations PRIMARY KEY (from_version_id, to_version_id, relation_type), 
	CONSTRAINT ck_document_version_relations_relation_type_values CHECK (relation_type IN ('replaces', 'supplements', 'accompanies', 'historical_reference')), 
	CONSTRAINT ck_document_version_relations_verification_status_values CHECK (verification_status IN ('pending', 'verified', 'rejected')), 
	CONSTRAINT ck_document_version_relations_no_self_relation CHECK (from_version_id <> to_version_id), 
	CONSTRAINT fk_document_version_relations_from_version_id_document_versions FOREIGN KEY(from_version_id) REFERENCES document_versions (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_document_version_relations_to_version_id_document_versions FOREIGN KEY(to_version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_version_relations_target ON document_version_relations (to_version_id);

COMMENT ON TABLE document_version_relations IS '有证据的政策版本替代/补充/配套关系';

COMMENT ON COLUMN document_version_relations.from_version_id IS '主动替代/补充的版本';

COMMENT ON COLUMN document_version_relations.to_version_id IS '被替代/补充的目标版本';

COMMENT ON COLUMN document_version_relations.relation_type IS '有方向的政策关系';

COMMENT ON COLUMN document_version_relations.effective_on IS '关系生效日期；未知则空';

COMMENT ON COLUMN document_version_relations.evidence_note IS '关系原文证据与适用限制';

COMMENT ON COLUMN document_version_relations.evidence_url IS '官方证据网址';

COMMENT ON COLUMN document_version_relations.verification_status IS '关系核查状态';

COMMENT ON COLUMN document_version_relations.created_at IS '创建时间';

COMMENT ON COLUMN document_version_relations.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE answer_feedback (
	id UUID NOT NULL, 
	message_id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	message_role VARCHAR(16) DEFAULT 'assistant' NOT NULL, 
	version_id UUID, 
	feedback_type VARCHAR(32) NOT NULL, 
	description TEXT NOT NULL, 
	status VARCHAR(32) DEFAULT 'open' NOT NULL, 
	resolution_note TEXT, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_answer_feedback PRIMARY KEY (id), 
	CONSTRAINT uq_answer_feedback_id_version_id UNIQUE (id, version_id), 
	CONSTRAINT ck_answer_feedback_feedback_assistant CHECK (message_role='assistant'), 
	CONSTRAINT fk_answer_feedback_message_id_session_id_message_role_i_6b70 FOREIGN KEY(message_id, session_id, message_role) REFERENCES interaction_messages (id, session_id, role) ON DELETE RESTRICT, 
	CONSTRAINT ck_answer_feedback_feedback_type_values CHECK (feedback_type IN ('incorrect', 'outdated', 'applicability', 'source', 'other')), 
	CONSTRAINT ck_answer_feedback_status_values CHECK (status IN ('open', 'triaged', 'in_review', 'resolved', 'dismissed')), 
	CONSTRAINT ck_answer_feedback_feedback_resolution CHECK ((status IN ('resolved','dismissed') AND resolution_note IS NOT NULL AND resolved_at IS NOT NULL) OR (status NOT IN ('resolved','dismissed') AND resolved_at IS NULL)), 
	CONSTRAINT fk_answer_feedback_session_id_conversation_sessions FOREIGN KEY(session_id) REFERENCES conversation_sessions (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_answer_feedback_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_feedback_message ON answer_feedback (message_id);

CREATE INDEX ix_feedback_queue ON answer_feedback (status, created_at);

COMMENT ON TABLE answer_feedback IS '对助手回复的反馈及处理结果';

COMMENT ON COLUMN answer_feedback.id IS '内部UUID；应用生成';

COMMENT ON COLUMN answer_feedback.message_id IS '被反馈的助手消息';

COMMENT ON COLUMN answer_feedback.session_id IS '消息所属会话';

COMMENT ON COLUMN answer_feedback.message_role IS '固定助手角色';

COMMENT ON COLUMN answer_feedback.version_id IS '反馈主要涉及资料版本；未知则空';

COMMENT ON COLUMN answer_feedback.feedback_type IS '错误/过期/适用范围/来源/其他';

COMMENT ON COLUMN answer_feedback.description IS '反馈内容';

COMMENT ON COLUMN answer_feedback.status IS '反馈处理状态';

COMMENT ON COLUMN answer_feedback.resolution_note IS '处理说明';

COMMENT ON COLUMN answer_feedback.resolved_at IS '处理结束时间';

COMMENT ON COLUMN answer_feedback.created_at IS '创建时间';

COMMENT ON COLUMN answer_feedback.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE applicability_rule_values (
	rule_id UUID NOT NULL, 
	dimension VARCHAR(32) NOT NULL, 
	value VARCHAR(128) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_applicability_rule_values PRIMARY KEY (rule_id, dimension, value), 
	CONSTRAINT ck_applicability_rule_values_dimension_values CHECK (dimension IN ('enrollment', 'graduation', 'major', 'student_type')), 
	CONSTRAINT fk_applicability_rule_values_rule_id_applicability_rules FOREIGN KEY(rule_id) REFERENCES applicability_rules (id) ON DELETE RESTRICT
);

COMMENT ON TABLE applicability_rule_values IS '一条适用规则各维度允许值';

COMMENT ON COLUMN applicability_rule_values.rule_id IS '规则编号';

COMMENT ON COLUMN applicability_rule_values.dimension IS '条件维度';

COMMENT ON COLUMN applicability_rule_values.value IS '标准化条件值';

COMMENT ON COLUMN applicability_rule_values.created_at IS '创建时间';

COMMENT ON COLUMN applicability_rule_values.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE knowledge_chunks (
	id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	file_id UUID NOT NULL, 
	chunk_no INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	locator TEXT, 
	locator_note TEXT, 
	original_file_id UUID, 
	original_locator TEXT, 
	index_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_knowledge_chunks PRIMARY KEY (id), 
	CONSTRAINT fk_knowledge_chunks_original_file_id_version_id_document_files FOREIGN KEY(original_file_id, version_id) REFERENCES document_files (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_knowledge_chunks_file_id_version_id_document_files FOREIGN KEY(file_id, version_id) REFERENCES document_files (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_knowledge_chunks_file_id_chunk_no UNIQUE (file_id, chunk_no), 
	CONSTRAINT uq_knowledge_chunks_id_version_id UNIQUE (id, version_id), 
	CONSTRAINT ck_knowledge_chunks_chunk_no_positive CHECK (chunk_no > 0), 
	CONSTRAINT ck_knowledge_chunks_index_status_values CHECK (index_status IN ('pending', 'indexed', 'failed', 'disabled')), 
	CONSTRAINT fk_knowledge_chunks_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_chunks_version ON knowledge_chunks (version_id);

COMMENT ON TABLE knowledge_chunks IS '可追溯检索片段';

COMMENT ON COLUMN knowledge_chunks.id IS '内部UUID；应用生成';

COMMENT ON COLUMN knowledge_chunks.version_id IS '所属版本';

COMMENT ON COLUMN knowledge_chunks.file_id IS '片段来源文件';

COMMENT ON COLUMN knowledge_chunks.chunk_no IS '来源文件内片段序号；从1开始';

COMMENT ON COLUMN knowledge_chunks.content IS '片段正文';

COMMENT ON COLUMN knowledge_chunks.locator IS '页码、章节或段落位置';

COMMENT ON COLUMN knowledge_chunks.locator_note IS '定位限制说明';

COMMENT ON COLUMN knowledge_chunks.original_file_id IS '对应官方原件；未定位则空';

COMMENT ON COLUMN knowledge_chunks.original_locator IS '官方原件的页码或章节；不能冒用提取稿行号';

COMMENT ON COLUMN knowledge_chunks.index_status IS '索引状态';

COMMENT ON COLUMN knowledge_chunks.created_at IS '创建时间';

COMMENT ON COLUMN knowledge_chunks.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE verification_records (
	id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	file_id UUID, 
	check_type VARCHAR(32) NOT NULL, 
	outcome VARCHAR(32) NOT NULL, 
	checked_on DATE NOT NULL, 
	checked_at TIMESTAMP WITH TIME ZONE, 
	reviewer_label VARCHAR(128), 
	method VARCHAR(128) NOT NULL, 
	evidence_url TEXT, 
	evidence_locator TEXT, 
	note TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_verification_records PRIMARY KEY (id), 
	CONSTRAINT fk_verification_records_file_id_version_id_document_files FOREIGN KEY(file_id, version_id) REFERENCES document_files (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_verification_records_id_version_id UNIQUE (id, version_id), 
	CONSTRAINT uq_verification_records_id_version_id_file_id UNIQUE (id, version_id, file_id), 
	CONSTRAINT ck_verification_records_check_type_values CHECK (check_type IN ('source', 'timeliness', 'extraction', 'attachment', 'applicability')), 
	CONSTRAINT ck_verification_records_outcome_values CHECK (outcome IN ('passed', 'partial', 'failed', 'inconclusive')), 
	CONSTRAINT fk_verification_records_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_checks_version_date ON verification_records (version_id, checked_on);

COMMENT ON TABLE verification_records IS '只追加的核查历史';

COMMENT ON COLUMN verification_records.id IS '内部UUID；应用生成';

COMMENT ON COLUMN verification_records.version_id IS '核查版本';

COMMENT ON COLUMN verification_records.file_id IS '具体核查文件；空表示版本级';

COMMENT ON COLUMN verification_records.check_type IS '核查维度';

COMMENT ON COLUMN verification_records.outcome IS '核查结果';

COMMENT ON COLUMN verification_records.checked_on IS '真实核查日期';

COMMENT ON COLUMN verification_records.checked_at IS '真实精确时间；仅有日期则空';

COMMENT ON COLUMN verification_records.reviewer_label IS '核验人标识；历史未知则空';

COMMENT ON COLUMN verification_records.method IS '核查方法';

COMMENT ON COLUMN verification_records.evidence_url IS '证据网址';

COMMENT ON COLUMN verification_records.evidence_locator IS '证据定位';

COMMENT ON COLUMN verification_records.note IS '具体核查结论与限制';

COMMENT ON COLUMN verification_records.created_at IS '创建时间';

COMMENT ON COLUMN verification_records.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE task_results (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	result_stage VARCHAR(32) DEFAULT 'final' NOT NULL, 
	answer_mode VARCHAR(32) DEFAULT 'insufficient_data' NOT NULL, 
	result_no INTEGER NOT NULL, 
	result_type VARCHAR(32) NOT NULL, 
	content TEXT NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_task_results PRIMARY KEY (id), 
	CONSTRAINT fk_task_results_task_id_session_id_agent_tasks FOREIGN KEY(task_id, session_id) REFERENCES agent_tasks (id, session_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_task_results_id_session_id UNIQUE (id, session_id), 
	CONSTRAINT ck_task_results_result_stage_values CHECK (result_stage IN ('intermediate', 'final')), 
	CONSTRAINT ck_task_results_answer_mode_values CHECK (answer_mode IN ('current_policy', 'historical', 'procedure_reference', 'insufficient_data')), 
	CONSTRAINT uq_task_results_task_id_result_no UNIQUE (task_id, result_no), 
	CONSTRAINT ck_task_results_result_sequence_positive CHECK (result_no>0), 
	CONSTRAINT fk_task_results_session_id_conversation_sessions FOREIGN KEY(session_id) REFERENCES conversation_sessions (id) ON DELETE RESTRICT
);

COMMENT ON TABLE task_results IS '任务结果历史；重试追加';

COMMENT ON COLUMN task_results.id IS '内部UUID；应用生成';

COMMENT ON COLUMN task_results.task_id IS '所属任务';

COMMENT ON COLUMN task_results.session_id IS '会话；必须与任务一致';

COMMENT ON COLUMN task_results.result_stage IS '区分中间结果与最终结果';

COMMENT ON COLUMN task_results.answer_mode IS '回答用途；默认资料不足，不输出确定政策结论';

COMMENT ON COLUMN task_results.result_no IS '任务内结果序号';

COMMENT ON COLUMN task_results.result_type IS '结果类型：答案/导航/结构化结果等';

COMMENT ON COLUMN task_results.content IS '结果内容；结构化结果可序列化JSON文本';

COMMENT ON COLUMN task_results.generated_at IS '生成时间';

COMMENT ON COLUMN task_results.created_at IS '创建时间';

COMMENT ON COLUMN task_results.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE document_file_sources (
	file_id UUID NOT NULL, 
	source_file_id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	source_locator TEXT, 
	target_locator TEXT, 
	verification_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_document_file_sources PRIMARY KEY (file_id, source_file_id), 
	CONSTRAINT fk_document_file_sources_file_id_version_id_document_files FOREIGN KEY(file_id, version_id) REFERENCES document_files (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_document_file_sources_source_file_id_version_id_docu_4aa1 FOREIGN KEY(source_file_id, version_id) REFERENCES document_files (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT ck_document_file_sources_no_self_source CHECK (file_id<>source_file_id), 
	CONSTRAINT ck_document_file_sources_verification_status_values CHECK (verification_status IN ('pending', 'verified', 'failed')), 
	CONSTRAINT fk_document_file_sources_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_file_sources_reverse ON document_file_sources (source_file_id);

COMMENT ON TABLE document_file_sources IS '派生文件与多个同版本来源；替代单来源字段';

COMMENT ON COLUMN document_file_sources.file_id IS '派生文件';

COMMENT ON COLUMN document_file_sources.source_file_id IS '来源文件';

COMMENT ON COLUMN document_file_sources.version_id IS '同一版本';

COMMENT ON COLUMN document_file_sources.source_locator IS '来源原件定位';

COMMENT ON COLUMN document_file_sources.target_locator IS '派生稿对应位置';

COMMENT ON COLUMN document_file_sources.verification_status IS '来源对应关系核验';

COMMENT ON COLUMN document_file_sources.created_at IS '创建时间';

COMMENT ON COLUMN document_file_sources.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE verification_tasks (
	id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	file_id UUID, 
	task_type VARCHAR(64) NOT NULL, 
	description TEXT NOT NULL, 
	status VARCHAR(32) DEFAULT 'open' NOT NULL, 
	priority INTEGER DEFAULT 2 NOT NULL, 
	assignee_label VARCHAR(128), 
	completion_record_id UUID, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_verification_tasks PRIMARY KEY (id), 
	CONSTRAINT fk_verification_tasks_file_id_version_id_document_files FOREIGN KEY(file_id, version_id) REFERENCES document_files (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_verification_tasks_completion_record_id_version_id_v_b8bc FOREIGN KEY(completion_record_id, version_id) REFERENCES verification_records (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_verification_tasks_completion_record_id_version_id_f_7e3e FOREIGN KEY(completion_record_id, version_id, file_id) REFERENCES verification_records (id, version_id, file_id) ON DELETE RESTRICT, 
	CONSTRAINT ck_verification_tasks_status_values CHECK (status IN ('open', 'in_progress', 'blocked', 'done', 'cancelled')), 
	CONSTRAINT ck_verification_tasks_completion_evidence CHECK ((status='done' AND completion_record_id IS NOT NULL AND completed_at IS NOT NULL) OR (status<>'done' AND completion_record_id IS NULL AND completed_at IS NULL)), 
	CONSTRAINT ck_verification_tasks_priority_range CHECK (priority BETWEEN 1 AND 3), 
	CONSTRAINT fk_verification_tasks_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_verification_tasks_id_version_id UNIQUE (id, version_id)
);

CREATE INDEX ix_review_tasks_status ON verification_tasks (status, priority);

CREATE INDEX ix_review_tasks_version ON verification_tasks (version_id);

COMMENT ON TABLE verification_tasks IS '资料核查待办';

COMMENT ON COLUMN verification_tasks.id IS '内部UUID；应用生成';

COMMENT ON COLUMN verification_tasks.version_id IS '待办版本';

COMMENT ON COLUMN verification_tasks.file_id IS '待办文件；可空';

COMMENT ON COLUMN verification_tasks.task_type IS 'OCR/数值/目录/时效/适用范围等';

COMMENT ON COLUMN verification_tasks.description IS '具体待办';

COMMENT ON COLUMN verification_tasks.status IS '待办状态';

COMMENT ON COLUMN verification_tasks.priority IS '优先级；1最高';

COMMENT ON COLUMN verification_tasks.assignee_label IS '负责人员标识';

COMMENT ON COLUMN verification_tasks.completion_record_id IS '完成证据核查记录';

COMMENT ON COLUMN verification_tasks.completed_at IS '完成时间';

COMMENT ON COLUMN verification_tasks.created_at IS '创建时间';

COMMENT ON COLUMN verification_tasks.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE result_citations (
	id UUID NOT NULL, 
	result_id UUID NOT NULL, 
	citation_no INTEGER NOT NULL, 
	version_id UUID NOT NULL, 
	chunk_id UUID, 
	locator TEXT, 
	quoted_text TEXT, 
	source_url_snapshot TEXT NOT NULL, 
	title_snapshot VARCHAR(512) NOT NULL, 
	cited_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	verification_snapshot JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_result_citations PRIMARY KEY (id), 
	CONSTRAINT fk_result_citations_chunk_id_version_id_knowledge_chunks FOREIGN KEY(chunk_id, version_id) REFERENCES knowledge_chunks (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT uq_result_citations_result_id_citation_no UNIQUE (result_id, citation_no), 
	CONSTRAINT ck_result_citations_citation_sequence_positive CHECK (citation_no>0), 
	CONSTRAINT fk_result_citations_result_id_task_results FOREIGN KEY(result_id) REFERENCES task_results (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_result_citations_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_citations_version ON result_citations (version_id);

COMMENT ON TABLE result_citations IS '结果引用；固定版本及可选片段';

COMMENT ON COLUMN result_citations.id IS '内部UUID；应用生成';

COMMENT ON COLUMN result_citations.result_id IS '所属结果';

COMMENT ON COLUMN result_citations.citation_no IS '结果内引用序号';

COMMENT ON COLUMN result_citations.version_id IS '引用的确定版本';

COMMENT ON COLUMN result_citations.chunk_id IS '可选精确片段';

COMMENT ON COLUMN result_citations.locator IS '引用位置';

COMMENT ON COLUMN result_citations.quoted_text IS '引用片段快照';

COMMENT ON COLUMN result_citations.source_url_snapshot IS '回答时的来源网址';

COMMENT ON COLUMN result_citations.title_snapshot IS '回答时资料标题';

COMMENT ON COLUMN result_citations.cited_at IS '引用时间';

COMMENT ON COLUMN result_citations.verification_snapshot IS '回答时核查状态、使用用途及适用条件快照';

COMMENT ON COLUMN result_citations.created_at IS '创建时间';

COMMENT ON COLUMN result_citations.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE message_result_links (
	message_id UUID NOT NULL, 
	result_id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	message_role VARCHAR(16) DEFAULT 'assistant' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_message_result_links PRIMARY KEY (message_id, result_id), 
	CONSTRAINT ck_message_result_links_message_is_assistant CHECK (message_role='assistant'), 
	CONSTRAINT fk_message_result_links_message_id_session_id_message_r_0f5f FOREIGN KEY(message_id, session_id, message_role) REFERENCES interaction_messages (id, session_id, role) ON DELETE RESTRICT, 
	CONSTRAINT fk_message_result_links_result_id_session_id_task_results FOREIGN KEY(result_id, session_id) REFERENCES task_results (id, session_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_message_result_links_session_id_conversation_sessions FOREIGN KEY(session_id) REFERENCES conversation_sessions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_message_results_reverse ON message_result_links (result_id);

COMMENT ON TABLE message_result_links IS '助手消息实际采用的结果；多对多支持结果整合';

COMMENT ON COLUMN message_result_links.message_id IS '助手消息';

COMMENT ON COLUMN message_result_links.result_id IS '采用的任务结果';

COMMENT ON COLUMN message_result_links.session_id IS '同一会话';

COMMENT ON COLUMN message_result_links.message_role IS '固定assistant以约束消息角色';

COMMENT ON COLUMN message_result_links.created_at IS '创建时间';

COMMENT ON COLUMN message_result_links.updated_at IS '更新时间；更新操作须显式维护';

CREATE TABLE feedback_review_links (
	feedback_id UUID NOT NULL, 
	verification_task_id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_feedback_review_links PRIMARY KEY (feedback_id, verification_task_id), 
	CONSTRAINT fk_feedback_review_links_feedback_id_version_id_answer_feedback FOREIGN KEY(feedback_id, version_id) REFERENCES answer_feedback (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_feedback_review_links_verification_task_id_version_i_f3c8 FOREIGN KEY(verification_task_id, version_id) REFERENCES verification_tasks (id, version_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_feedback_review_links_version_id_document_versions FOREIGN KEY(version_id) REFERENCES document_versions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_feedback_reviews_task ON feedback_review_links (verification_task_id);

COMMENT ON TABLE feedback_review_links IS '反馈转核查待办；同版本证据链';

COMMENT ON COLUMN feedback_review_links.feedback_id IS '反馈';

COMMENT ON COLUMN feedback_review_links.verification_task_id IS '核查待办';

COMMENT ON COLUMN feedback_review_links.version_id IS '反馈及待办共同指向的版本';

COMMENT ON COLUMN feedback_review_links.created_at IS '创建时间';

COMMENT ON COLUMN feedback_review_links.updated_at IS '更新时间；更新操作须显式维护';
COMMIT;
