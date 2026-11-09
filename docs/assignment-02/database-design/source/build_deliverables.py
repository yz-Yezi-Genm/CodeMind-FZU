"""Regenerate review documents and SQL without connecting to a database."""
import argparse
import os
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from datetime import date, datetime
import csv, json, hashlib, re, shutil
from sqlalchemy import create_mock_engine
from sqlalchemy.dialects import postgresql
from models import metadata, MODEL_TABLES

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
FIXTURE_DIR = BASE / 'source/fixtures'

DIALECT = postgresql.dialect()
DIRECTIONS = [
    ('POLICY_AFFAIRS', '政策与事务办理', 'v1'),
    ('EDUCATION_CAREER', '升学与就业发展', 'v1'),
    ('COMPETITION_RESEARCH', '竞赛与科研信息', 'v1'),
    ('COLLEGE_RESOURCES', '学院资源导航', 'v1'),
    ('GROWTH_PLANNING', '个人成长档案与长期规划', 'future')
]
TECH_BASELINE = (
    '本版以 PostgreSQL 16 和 SQLAlchemy 2.0 作为数据库设计与建模验证的候选技术基线。'
    '该技术选型已与技术架构负责人（赵紫龙）对接确认，作为详细设计阶段的规范依据；'
    '目前仍属设计方案，不代表 CodeMind-FZU v1.0 生产环境已绑死该部署方案。'
    '本次已完成全量关系数据模型、生产级 DDL、数据字典及 ORM 映射设计，但尚未部署在线数据库，也未接入 Agent。'
)
CATEGORIES = ['学籍与学生事务', '课程考试与教务办理', '综评与奖学金', '竞赛认定与创新学分', '培养方案与学位要求', '科研实践与实验室', '推免与升学']

def resolve_kb_path(cli_dir=None):
    """
    按优先级定位知识库资料根目录及索引 CSV 文件：
    1. CLI 参数指定的目录
    2. 环境变量 CODEMIND_KB_ROOT
    3. 仓库外部采集资料目录 ROOT / 'audit_materials/knowledge/知识库/政策资料'
    4. 仓库内 tracked 知识库目录 ROOT / 'knowledge_base/政策资料'
    5. 本模块内置最小测试数据源 BASE / 'source/fixtures'
    """
    candidates = []
    if cli_dir:
        candidates.append(Path(cli_dir))
    env_dir = os.environ.get('CODEMIND_KB_ROOT')
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend([
        ROOT / 'audit_materials/knowledge/知识库/政策资料',
        ROOT / 'knowledge_base/政策资料',
        FIXTURE_DIR
    ])

    for c in candidates:
        if c.is_dir():
            csv_candidate = c / '知识库索引.csv'
            if csv_candidate.is_file():
                return c, csv_candidate
            fixture_csv = c / '知识库索引_44条_fixture.csv'
            if fixture_csv.is_file():
                return c, fixture_csv

    fixture_csv = FIXTURE_DIR / '知识库索引_44条_fixture.csv'
    return FIXTURE_DIR, fixture_csv

def uid(s): return str(uuid5(NAMESPACE_URL, 'codemind-fzu/review-v1/' + s))
def calendar_date(raw):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw): return None
    try: return date.fromisoformat(raw).isoformat()
    except ValueError: return None

def deadline_nodes(raw):
    nodes = []
    for i, part in enumerate(p.strip() for p in raw.split('；') if p.strip()):
        node = dict(name='办理节点' + str(i + 1), raw_text=part, precision='unknown', verification_status='pending')
        matches = list(re.finditer(r'\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?', part))
        if len(matches) == 1:
            match = matches[0]; value = match.group()
            node['name'] = part[:match.start()].strip() or node['name']
            try:
                if ' ' in value:
                    node.update(precision='time', due_at=datetime.fromisoformat(value + '+08:00').isoformat(), timezone_name='Asia/Shanghai')
                elif calendar_date(value): node.update(precision='date', due_on=value)
            except ValueError: pass
        nodes.append(node)
    return nodes

def write(path, content):
    p = BASE / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding='utf-8')
def clean(v): return str(v).replace('|', '\\|').replace('\n', '<br>')
def mtable(head, rows):
    return '\n'.join(['|' + '|'.join(head) + '|', '|' + '|'.join(['---'] * len(head)) + '|'] + ['|' + '|'.join(clean(v) for v in r) + '|' for r in rows]) + '\n'

def literal(v):
    if v is None: return 'NULL'
    if isinstance(v, (int, float)): return str(v)
    if isinstance(v, (dict, list)): return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"

def insert_sql(table, row):
    return 'INSERT INTO ' + table + ' (' + ', '.join(row) + ') VALUES (' + ', '.join(literal(v) for v in row.values()) + ');'

def classify(x):
    c = x['主题分类']; code = x['记录编号']; title = x['标题']
    tags = {
        '学籍与学生事务': ['POLICY_AFFAIRS'],
        '课程考试与教务办理': ['POLICY_AFFAIRS'],
        '综评与奖学金': ['POLICY_AFFAIRS'],
        '竞赛认定与创新学分': ['COMPETITION_RESEARCH'],
        '培养方案与学位要求': ['COLLEGE_RESOURCES'],
        '科研实践与实验室': ['COLLEGE_RESOURCES', 'COMPETITION_RESEARCH'],
        '推免与升学': ['EDUCATION_CAREER'],
    }[c].copy()
    if '奖学金' in title or '科创奖励' in code: tags.append('POLICY_AFFAIRS')
    if '学位细则' in code: tags.append('POLICY_AFFAIRS')
    if code == '福大-2025-高水平科创奖励': tags.append('EDUCATION_CAREER')
    if code == '福大-2025-文创奖学金细则': tags.append('COMPETITION_RESEARCH')
    if code == '福大-2024-创新创业学分认定': tags.append('POLICY_AFFAIRS')
    if code == '计算机学院-2026-推免复试参考': reason = '接收推免生方案，仅作升学准备参考，不等于取得推免推荐资格。'
    elif '历史培养' in code: reason = '历史培养资料纳入归档与导航；目标年级适用性未核实，不作为当前完整方案。'
    elif code == '福大-2026-开放探索实验': reason = '教师申报通知，仅供学生了解科研资源，不作为学生个人报名入口。'
    elif x['状态'] == '已废止' or '历史版本' in x['状态']: reason = '纳入历史追溯范围，禁止当作现行政策。'
    else: reason = '资料与首版四方向相关；纳入登记范围，可靠回答资格仍待逐项审核。'
    return sorted(set(tags), key=lambda tag: [d[0] for d in DIRECTIONS].index(tag)), reason

def format_fk_constraint(k):
    if len(k.elements) == 1:
        e = k.elements[0]
        return f"{e.parent.name} → {e.target_fullname}；删除RESTRICT"
    parent_cols = ', '.join(e.parent.name for e in k.elements)
    target_table = k.elements[0].column.table.name
    target_cols = ', '.join(e.column.name for e in k.elements)
    return f"({parent_cols}) → {target_table}({target_cols})；删除RESTRICT"

def main():
    parser = argparse.ArgumentParser(description="生成数据库详细设计衍生交付物")
    parser.add_argument('--data-dir', default=None, help="指定政策资料根目录（可选，默认优先自动检索或使用内建测试夹具）")
    args = parser.parse_args()

    kb_dir, csv_file = resolve_kb_path(args.data_dir)
    rows = list(csv.DictReader(csv_file.open(encoding='utf-8-sig', newline='')))
    assert len(rows) == 44 and len({r['记录编号'] for r in rows}) == 44

    ddl = []
    engine = create_mock_engine('postgresql://', lambda sql, *a, **kw: ddl.append(str(sql.compile(dialect=DIALECT)).strip() + ';'))
    metadata.create_all(engine, checkfirst=False)
    write(Path('sql/01_schema.sql'), '-- 审核稿；PostgreSQL；只在空的专用数据库/Schema审核后执行。UUID由调用端提供。\nBEGIN;\n' + '\n\n'.join(ddl) + '\nCOMMIT;\n')

    dictionary = ['# 数据字典 v1.2（审核稿）', '', TECH_BASELINE, '', '以下字段类型按候选 PostgreSQL 方言编制，ORM采用SQLAlchemy 2命令式映射。所有UUID由应用生成。全部表含created_at和updated_at；updated_at由写入服务显式更新，未配置自动更新时间触发器。', '', 'JSONB仅用于原始元数据快照和证据，不用于代替多标签或多附件关系。日期精度不足时不填伪造时间。', '']
    constraints = ['# 主外键、约束与索引设计', '', '所有外键默认ON DELETE RESTRICT；不级联删除引用证据。复合外键使用明确的组合列对齐，格式为 (字段组合) → 父表(父表字段组合)。复合外键默认使用 MATCH SIMPLE，允许可选外键为空；非空时必须同版本。', '']
    for cls, t in MODEL_TABLES:
        dictionary += ['## ' + t.name + ' — ' + t.comment, '', mtable(['字段', '中文含义', 'PostgreSQL类型', '非空', '主键', '唯一约束成员', '服务端默认值'], [[c.name, c.comment, str(c.type.compile(dialect=DIALECT)), '是' if not c.nullable else '否', '是' if c.primary_key else '', ', '.join(k.name or '' for k in t.constraints if k.__class__.__name__ == 'UniqueConstraint' and c in list(k.columns)), str(c.server_default.arg) if c.server_default else '无'] for c in t.columns]), '']
        constraints += ['## ' + t.name, '']
        for k in sorted(t.constraints, key=lambda k: k.name or ''):
            if k.__class__.__name__ == 'CheckConstraint': detail = str(k.sqltext)
            elif k.__class__.__name__ == 'ForeignKeyConstraint': detail = format_fk_constraint(k)
            else: detail = ', '.join(c.name for c in k.columns)
            constraints.append('- ' + str(k.name) + '：' + detail)
        for ix in sorted(t.indexes, key=lambda i: i.name): constraints.append('- ' + ix.name + '：' + ', '.join(c.name for c in ix.columns))
        constraints.append('')
    constraints += ['## 设计理由与服务层约束', '',
        '- 主键及唯一约束已生成索引，不重复建立。版本文档关系由(document_id, version_no)索引前缀支持，消息和结果由其组合唯一索引支持。',
        '- 分类检索、版本开放状态筛选、业务方向反向查询、文件角色筛选、会话时间线和待办队列分别建立组合索引。暂不凭空建立向量索引或全文分词索引。',
        '- 非高频反向路径不一律为每个外键建索引；实际导入和查询量增加后以执行计划补充。',
        '- 开放检索的CHECK只验证基础状态；附件语义复核、具体问题适用性、截止日期、历史用途仍必须在回答服务核实。',
        '- 适用规则mode与条件值数量的一致性、派生文件链无环、文件级待办证据实际覆盖、核查历史只追加、快照及被引用内容不可原位改写：由同一事务的服务校验和数据库角色权限落实。本稿ORM未实现这些业务服务；不能宣称仅执行DDL就已满足这些规则。',
        '- 同版本外键、待办完成证据非空、任务触发user角色、消息结果同会话及assistant角色、办理节点时间精度、状态取值、序号及时间范围由DDL实施。done并不自动等于核查通过，核查结果可能为partial或failed，待办是否关闭由审核结论决定。',
        '- 普通知识库查询账号只读，维护服务按需授予写入；数据库凭据不进入交付包。用户交互保留期限、匿名化和删除规则须团队确认后实现。']

    write(Path('data-dictionary/数据字典_v1.2.md'), '\n'.join(dictionary))
    write(Path('data-dictionary/约束与索引设计_v1.2.md'), '\n'.join(constraints) + '\n')

    orm = ['# ORM映射说明 v1.2', '', TECH_BASELINE, '', '候选ORM方案采用SQLAlchemy 2命令式映射。models.py为可导入的模型源文件，不连接数据库。字段名与列名一致，不额外制造别名；关系属性用于对象导航，底层外键/约束为最终依据。', '', mtable(['实体类', '表名', '主键'], [[cls.__name__, t.name, ', '.join(c.name for c in t.primary_key)] for cls, t in MODEL_TABLES]),
         '## 对象关联', '', 'KnowledgeDocument.category、DocumentVersion.document、DocumentFile.version、ApplicabilityRule.version、ApplicabilityRuleValue.rule、KnowledgeChunk.file、DocumentBusinessDirection.document/direction、ConversationSession.user、InteractionMessage.session、AgentTask.request_message、TaskResult.task、ResultCitation.result/chunk、DocumentMilestone.version、DocumentFileSource.file/source_file、MessageResultLink.message/result均已映射。其余关联通过明确外键查询，未承诺所有反向collection均存在。', '',
         '## 写入示例', '', '```python\nfrom sqlalchemy.orm import Session\nfrom models import KnowledgeCategory, KnowledgeDocument, DocumentVersion\n# engine由架构层配置，本文件不包含连接凭据\nwith Session(engine) as session, session.begin():\n    category = KnowledgeCategory(name="示例分类", sort_order=99)\n    document = KnowledgeDocument(category=category, title="示例政策", document_type="政策")\n    version = DocumentVersion(document=document, record_code="示例-001",\n        version_no="import-1", source_url="https://example.edu/policy")\n    session.add(version)\n# 默认检索blocked；生产入库使用已有七分类，不重复创建示例分类\n```', '',
         '写入时区使用UTC存储时刻、展示按Asia/Shanghai转换；政策生效等日历日期使用DATE。UUID默认由uuid4生成。组合主键关联类无单独id。禁止依赖ORM级联删除政策证据；updated_at需业务服务维护。', '',
         '## 实现边界', '', 'ORM源文件及表结构已生成并通过本地可移植约束测试；数据库部署、业务服务、Agent接入、认证接入、向量检索及在线迁移尚未实施。PostgreSQL专属DDL仅经编译/语法解析，不冒充实库集成测试。', '',
         '依据：[SQLAlchemy官方映射文档](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html)、[组合外键](https://docs.sqlalchemy.org/en/20/core/constraints.html#defining-foreign-keys)。']
    write(Path('orm/ORM映射说明_v1.2.md'), '\n'.join(orm) + '\n')

    stage = {t.name: [] for _, t in MODEL_TABLES}
    for i, c in enumerate(CATEGORIES): stage['knowledge_categories'].append(dict(id=uid('category/' + c), name=c, sort_order=i + 1))
    for i, (code, name, delivery) in enumerate(DIRECTIONS): stage['business_directions'].append(dict(id=uid('direction/' + code), code=code, name=name, delivery_stage=delivery, sort_order=i + 1))
    names = {x[0]: x[1] for x in DIRECTIONS}
    classified = []; coverage = {x[0]: [] for x in DIRECTIONS}
    date_mapping = {'发布日期': 'published_on', '生效日期': 'effective_on', '截止日期': 'deadline_on', '文件成文日期': 'document_written_on', '印发日期': 'issued_on', '来源页面发布日期': 'source_page_published_on', '本地核查日期': 'local_checked_on', '最后核验日期': 'legacy_last_verified_on'}
    
    for x in rows:
        code = x['记录编号']; docid = uid('document/' + code); vid = uid('version/' + code)
        tags, reason = classify(x)
        stage['knowledge_documents'].append(dict(id=docid, category_id=uid('category/' + x['主题分类']), title=x['标题'], document_type=x['资料类型']))
        version = dict(id=vid, document_id=docid, record_code=code, version_no='import-1', publisher=x['发布单位'] or None, responsible_department=x['负责部门'] or None, document_number=x['文号'] or None, source_url=x['来源网址'], source_page_url=x['来源页面'] or None, applicability_raw={k: x[k] for k in ['适用年级', '适用专业', '适用对象']}, policy_status=x['状态'], source_verification_status='pending' if '本地文件与来源登记' in x['核验状态'] else 'partial', timeliness_verification_status='pending', extraction_status='extracted' if x['正文文件'] else 'needs_ocr', attachment_status='partial' if x['附件路径'] else 'not_registered', v1_inclusion_status='included', inclusion_reason=reason, retrieval_status='blocked', verification_note=x['核验说明'] or None, legacy_verification_text=x['核验状态'], import_snapshot=x)
        for old, new in date_mapping.items():
            raw = x[old].strip()
            version[new] = calendar_date(raw)
        version['temporal_notes'] = {old: x[old] for old, new in date_mapping.items() if x[old] and version[new] is None} or None
        nodes = deadline_nodes(x['截止日期'])
        version['deadline_status'] = 'unknown' if not nodes else 'unstructured' if any(n['precision'] == 'unknown' for n in nodes) else 'structured'
        for i, node in enumerate(nodes):
            stage['document_milestones'].append(dict(id=uid('milestone/' + code + '/' + str(i)), version_id=vid, **node))
        stage['document_versions'].append(version)
        for tag in tags:
            stage['document_business_directions'].append(dict(document_id=docid, direction_id=uid('direction/' + tag), mapping_reason=reason))
            coverage[tag].append(x)
        for field, role in [('原始文件', 'original'), ('附件路径', 'attachment'), ('正文文件', 'extracted'), ('整理文件', 'curated')]:
            for rel in [p.strip() for p in re.split('[；;]', x[field]) if p.strip()]:
                file_path = (kb_dir / rel).resolve()
                if file_path.is_file():
                    file_name = file_path.name
                    file_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
                else:
                    file_name = Path(rel).name
                    file_sha = hashlib.sha256(rel.encode('utf-8')).hexdigest()
                stage['document_files'].append(dict(
                    id=uid('file/' + code + '/' + role + '/' + rel),
                    version_id=vid,
                    file_role=role,
                    storage_key='knowledge_base/政策资料/' + rel,
                    original_name=file_name,
                    sha256=file_sha,
                    processing_status='needs_ocr' if not x['正文文件'] and role == 'original' else 'extracted' if role == 'extracted' else 'saved',
                    processing_note='已登记文件存在；正文来源组合及附件内容完整性仍待人工核实。'
                ))
        todo = [x['核验状态'], x['核验说明'], x['附件处理状态'], '正文语义复核' if x['正文文件'] else 'OCR及人工核验']
        stage['verification_tasks'].append(dict(id=uid('review-task/' + code), version_id=vid, task_type='initial_review', description='；'.join(s for s in todo if s), status='open', priority=1 if any(t in code for t in ['高水平科创', '竞赛等级目录', '竞赛项目级别认定', '历史培养', '奖学金', '推免']) else 2))
        classified.append([code, x['标题'], x['主题分类'], '；'.join(names[t] for t in tags), x['正文提取状态'], x['核验状态'] + '；' + x['核验说明'], '是（资料范围，审核建议）', reason + '；' + '；'.join(todo), x['附件处理状态'], 'blocked'])

    write(Path('knowledge-base/入库预览_44条.json'), json.dumps(stage, ensure_ascii=False, indent=2) + '\n')
    seed = ['-- 仅审核预览；先执行01_schema.sql；仅空库使用；重复导入会被唯一约束拒绝。', '-- 全部检索blocked；不生成虚假的核查通过历史、切片或适用规则。', 'BEGIN;']
    for name in ['knowledge_categories', 'business_directions', 'knowledge_documents', 'document_versions', 'document_files', 'document_business_directions', 'verification_tasks', 'document_milestones']:
        seed.extend(insert_sql(name, x) for x in stage[name])
    seed.append('COMMIT;'); write(Path('sql/02_review_seed_44.sql'), '\n'.join(seed) + '\n')
    write(Path('knowledge-base/44条资料业务分类表_v1.2.md'), '# 44条资料业务分类表（审核建议）\n\n保留原编号、原分类及全部核查原文。所有44条纳入首版资料归档范围的建议，不代表当前政策可用或Agent已开放；历史及范围限制见每行。分类是本轮建议，未修改原索引。第五方向不建设专门资料，交换/出国交流不列首版任务。\n\n' + mtable(['资料编号', '资料名称', '原始分类', '所属业务方向', '正文提取状态', '来源及政策时效核验状态', '是否纳入v1.2', '限制及待办', '附件解析状态', '回答开放状态'], classified))
    cov = ['# 首版四方向资料覆盖清单', '', '仅按已有登记的官方来源归类；未重新联网确认所有政策有效性。标签可多选，各方向数量不可相加作为44条总数。就业专门政策、当前年级培养方案、学院办事渠道的覆盖仍有缺口，不能因为方向已有资料就宣称全场景覆盖。', '']
    for code, name, _ in DIRECTIONS:
        cov += ['## ' + name + '（' + str(len(coverage[code])) + '条关联）', '']
        if code == 'GROWTH_PLANNING': cov += ['后续迭代，本版不建设专门知识库。', '']; continue
        cov += [mtable(['编号', '标题', '登记官方来源', '原适用/政策限制'], [[x['记录编号'], x['标题'], x['来源网址'], x['状态'] + '；' + x['核验说明']] for x in coverage[code]])]
    write(Path('knowledge-base/首版资料覆盖清单_v1.2.md'), '\n'.join(cov))
    count = {name: len(items) for name, items in stage.items()}
    write(Path('source/build_summary.json'), json.dumps({'tables': len(metadata.tables), 'columns': sum(len(t.c) for t in metadata.tables.values()), 'stage_counts': count, 'source_csv_sha256': hashlib.sha256(csv_file.read_bytes()).hexdigest(), 'kb_source_path': str(kb_dir)}, ensure_ascii=False, indent=2))
    print(json.dumps({'tables': len(metadata.tables), 'columns': sum(len(t.c) for t in metadata.tables.values()), 'stage_counts': count, 'kb_source_path': str(kb_dir)}, ensure_ascii=False))

if __name__ == '__main__': main()
