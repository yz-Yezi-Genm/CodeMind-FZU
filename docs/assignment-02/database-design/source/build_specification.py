"""Organize the formal specification from immutable v1.2 design inputs."""
import ast
import hashlib
import json
from pathlib import Path
from sqlalchemy.dialects import postgresql
from models import MODEL_TABLES, metadata
from render_diagrams import foreign_keys

BASE = Path(__file__).resolve().parents[1]
PROTECTED = [
    'source/models.py', 'sql/01_schema.sql', 'sql/02_review_seed_44.sql',
    'source/fixtures/知识库索引_44条_fixture.csv', 'source/validation_report.json',
    'knowledge-base/入库预览_44条.json', 'source/test_models.py', 'source/test_import_rules.py',
    'data-dictionary/数据字典_v1.2.md', 'data-dictionary/约束与索引设计_v1.2.md',
    'orm/ORM映射说明_v1.2.md', 'relational-model/关系数据模型_v1.2.md',
]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def table(head, rows):
    def clean(value):
        return str(value).replace('|', '\\|').replace('\n', '<br/>')
    return '\n'.join(['|' + '|'.join(head) + '|', '|' + '|'.join(['---'] * len(head)) + '|'] + ['|' + '|'.join(clean(x) for x in row) + '|' for row in rows]) + '\n'

def build():
    protected = {name: digest(BASE / name) for name in PROTECTED}
    dialect = postgresql.dialect()
    text = (BASE / 'source/数据库设计说明书_正文.md').read_text(encoding='utf-8')
    text += '\n\n## 附录A 完整数据字典\n\n本附录逐表列出全部233个字段。字段类型、空值、主键和默认值沿用v1.2模型；唯一约束及外键见附录B。“服务端默认”记录DDL定义，应用侧UUID生成方式见第6章。\n'
    for i, (_, relation) in enumerate(MODEL_TABLES, 1):
        text += f'\n### A.{i} {relation.name}\n\n{relation.comment}。\n\n表 A-{i} {relation.name} 字段定义\n\n'
        text += table(['字段', '含义', '候选类型', '允许空', '主键', '服务端默认'], [
            [c.name, c.comment, str(c.type.compile(dialect=dialect)), '是' if c.nullable else '否', '是' if c.primary_key else '否', str(c.server_default.arg) if c.server_default else '无'] for c in relation.c])
    text += '\n## 附录B 完整关系约束与索引\n\n### B.1 全部40组外键\n\n以下F编号与图4-1及关系子图一致。复合外键按整组列匹配，默认MATCH SIMPLE及ON DELETE RESTRICT。\n'
    for i, (relation, fk) in enumerate(foreign_keys(), 1):
        left = ', '.join(e.parent.name for e in fk.elements)
        right = ', '.join(e.column.name for e in fk.elements)
        text += f'\nF{i:02}　{relation.name} ({left}) → {fk.elements[0].column.table.name} ({right})。约束名：{fk.name}。\n'
    text += '\n### B.2 各表主键、唯一约束、检查约束与索引\n\n外键已在B.1完整列出；以下保留其余所有结构约束及显式索引。\n'
    for i, (_, relation) in enumerate(MODEL_TABLES, 1):
        rows = []
        for constraint in sorted(relation.constraints, key=lambda c: c.name or ''):
            kind = constraint.__class__.__name__
            if kind == 'ForeignKeyConstraint':
                continue
            detail = str(constraint.sqltext) if kind == 'CheckConstraint' else ', '.join(c.name for c in constraint.columns)
            rows.append([str(constraint.name), {'PrimaryKeyConstraint': 'PK', 'UniqueConstraint': 'UQ', 'CheckConstraint': 'CHECK'}.get(kind, kind), detail])
        rows.extend([index.name, 'INDEX', ', '.join(c.name for c in index.columns)] for index in sorted(relation.indexes, key=lambda c: c.name))
        text += f'\n表 B-{i} {relation.name} 约束与索引\n\n' + table(['名称', '类型', '字段或表达式'], rows)
    text += '\n## 附录C 完整 ORM 映射\n\n### C.1 实体类与表\n\n表 C-1 全部23组实体类映射\n\n'
    text += table(['实体类', '关系表', '主键'], [[cls.__name__, relation.name, ', '.join(c.name for c in relation.primary_key)] for cls, relation in MODEL_TABLES])
    text += '\n### C.2 对象关联\n\n下列导航关系直接来自已确认的命令式映射定义；未列出的关联仍由外键查询实现。\n\n表 C-2 已定义的对象导航关系\n\n'
    from models import properties
    text += table(['实体类', '导航属性', '目标实体'], [[cls.__name__, name, prop.argument.__name__] for cls, entries in properties.items() for name, prop in entries.items()])
    report = json.loads((BASE / 'source/validation_report.json').read_text(encoding='utf-8'))
    text += '\n## 附录D 既有验证记录\n\n### D.1 范围与结果\n\nv1.2离线验证记录包含21项单元测试，结果均为passed。核心资料fixture的插入范围及行数见表D-1。\n\n表 D-1 核心资料fixture插入记录\n\n'
    text += table(['表名', '既有插入行数'], list(report['sqlite_fixture_rows_inserted'].items()))
    text += '\n23张表均完成SQLite建表；上表8张表使用同一资料fixture导入，其余15张表的相关约束由独立单元测试覆盖。\n\n### D.2 单元测试清单\n\n表 D-2 既有21项测试记录\n\n'
    tests = []
    for filename in ('test_import_rules.py', 'test_models.py'):
        source = ast.parse((BASE / 'source' / filename).read_text(encoding='utf-8'))
        for node in ast.walk(source):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                tests.append([filename, node.name, '既有记录通过'])
    text += table(['测试源文件', '测试名称', '既有结果'], tests)
    text += '\n### D.3 原始机器可读报告\n\n原始报告完整记录如下，包含SQL解析数量、导入范围及实施状态。\n\n```json\n' + json.dumps(report, ensure_ascii=False, indent=2) + '\n```\n'
    stage = json.loads((BASE / 'knowledge-base/入库预览_44条.json').read_text(encoding='utf-8'))
    categories = {x['id']: x['name'] for x in stage['knowledge_categories']}
    documents = {x['id']: x for x in stage['knowledge_documents']}
    directions = {x['id']: x['name'] for x in stage['business_directions']}
    text += '\n## 附录E 知识库资料范围\n\n表 E-1 保留原编号的44条资料及业务标签\n\n原始44条×37列快照、核查原文、附件处理与待办保存在入库预览和资料分类表中；本表用于正式说明书的资料定位，不替代逐条核验清单。所有资料回答状态均为blocked。\n\n'
    rows = []
    for version in stage['document_versions']:
        document = documents[version['document_id']]
        tags = [directions[x['direction_id']] for x in stage['document_business_directions'] if x['document_id'] == document['id']]
        rows.append([version['record_code'], document['title'], categories[document['category_id']], '；'.join(tags)])
    text += table(['原资料编号', '资料名称', '原始分类', '业务方向'], rows)
    text += '\n原索引来源核查为13条已有部分记录、31条仅完成本地文件与来源登记核查；时效仍待联网复核。正文提取登记为43条已提取、1条待OCR。fixture缺少物理文件时，文件级状态必须单独标为failed、哈希为空；两类口径不得混同。\n'
    text += '\n## 附录F 技术成果定位与保全\n\n### F.1 完整技术成果\n\n表 F-1 随仓库保留的技术成果\n\n'
    text += table(['成果', '相对于database-design的路径'], [
        ['模型、23实体类及233字段', 'source/models.py'], ['PostgreSQL候选DDL及44条种子数据', 'sql/01_schema.sql；sql/02_review_seed_44.sql'],
        ['完整字段与约束原稿', 'data-dictionary/数据字典_v1.2.md；约束与索引设计_v1.2.md'],
        ['ORM原说明及源代码', 'orm/ORM映射说明_v1.2.md；source/models.py'], ['关系模型及上游概念图', 'relational-model/；er/'],
        ['44条资料、元数据和分类', 'knowledge-base/；source/fixtures/'], ['完整测试和验证记录', 'source/test_models.py；test_import_rules.py；validation_report.json'],
        ['本版正文与正式可读源稿', 'source/数据库设计说明书_正文.md；AgentX_数据库设计说明书.md'],
        ['图形源与已渲染图片', 'figures/中的mmd、svg和png'], ['重新生成正式PDF', 'source/generate_pdf.py；source/finalize_acceptance.py']])
    text += '\n### F.2 技术基线校验值\n\n表 F-2 技术输入的SHA-256\n\n'
    text += table(['技术文件', 'SHA-256'], list(protected.items()))
    output = BASE / 'AgentX_数据库设计说明书.md'
    output.write_text(text, encoding='utf-8', newline='\n')
    from markdown_it import MarkdownIt
    blocks = [token.as_dict() for token in MarkdownIt().enable('table').parse(text)]
    (BASE / 'source/document_blocks.json').write_text(json.dumps(blocks, ensure_ascii=False), encoding='utf-8', newline='\n')
    assert all(digest(BASE / name) == value for name, value in protected.items())
    assert len(tests) == report['tests_passed'] == 21
    assert len(metadata.tables) == 23 and sum(len(t.c) for t in metadata.tables.values()) == 233
    return output, protected

if __name__ == '__main__':
    output, _ = build()
    print(output)
