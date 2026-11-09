"""Offline review validation; deliberately creates only an in-memory SQLite DB."""
import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path
import unittest
from uuid import UUID

from models import metadata
from pglast import parse_sql
from sqlalchemy import Date, DateTime, Uuid, create_engine, event, insert

from build_deliverables import BASE, resolve_kb_path

EXPECTED_DIRECTIONS = [
    ('POLICY_AFFAIRS', '政策与事务办理', 1),
    ('EDUCATION_CAREER', '升学与就业发展', 2),
    ('COMPETITION_RESEARCH', '竞赛与科研信息', 3),
    ('COLLEGE_RESOURCES', '学院资源导航', 4),
    ('GROWTH_PLANNING', '个人成长档案与长期规划', 5),
]

# The shared fixture imports core material records, not all 23 tables.
CORE_IMPORT_TABLES = (
    'knowledge_categories', 'business_directions', 'knowledge_documents',
    'document_versions', 'document_files', 'document_business_directions',
    'verification_tasks', 'document_milestones',
)

def main():
    parser = argparse.ArgumentParser(description="离线验证详细设计交付物")
    parser.add_argument('--data-dir', default=None, help="指定政策资料根目录（可选，默认自动检索或使用内建测试夹具）")
    args = parser.parse_args()

    stage = json.loads((BASE / 'knowledge-base/入库预览_44条.json').read_text(encoding='utf-8'))
    _, csv_file = resolve_kb_path(args.data_dir)
    original = list(csv.DictReader(csv_file.open(encoding='utf-8-sig', newline='')))
    by_code = {r['记录编号']: r for r in original}

    assert len(metadata.tables) == 23

    # 1. 严格校验五大业务方向代码、名称与 sort_order 顺序断言（防止顺序回退）
    actual_dirs = sorted(stage['business_directions'], key=lambda d: d['sort_order'])
    assert len(actual_dirs) == 5, f"预期 5 个业务方向，实际为 {len(actual_dirs)}"
    for actual, (exp_code, exp_name, exp_order) in zip(actual_dirs, EXPECTED_DIRECTIONS):
        assert actual['code'] == exp_code, f"业务方向 code 不符：{actual['code']} != {exp_code}"
        assert actual['name'] == exp_name, f"业务方向 name 不符：{actual['name']} != {exp_name}"
        assert actual['sort_order'] == exp_order, f"业务方向 sort_order 顺序不符：{actual['sort_order']} != {exp_order}"

    # 2. 校验版本数据完整性与原始 44 条快照一致性
    versions = stage['document_versions']
    assert len(versions) == 44 and len({v['record_code'] for v in versions}) == 44
    assert all(v['import_snapshot'] == by_code[v['record_code']] for v in versions)
    assert all(len(v['import_snapshot']) == 37 for v in versions)
    assert all(v['retrieval_status'] == 'blocked' and v['timeliness_verification_status'] == 'pending' for v in versions)
    assert sum(v['extraction_status'] == 'extracted' for v in versions) == 43
    assert sum(v['extraction_status'] == 'needs_ocr' for v in versions) == 1

    # 3. SQLite 全表建表及核心资料导入验证（23张表建表，8张表插入fixture）
    engine = create_engine('sqlite://')
    event.listen(engine, 'connect', lambda db, _: db.execute('PRAGMA foreign_keys=ON'))
    metadata.create_all(engine)
    with engine.begin() as conn:
        for name in CORE_IMPORT_TABLES:
            t = metadata.tables[name]
            for row in stage[name]:
                row = row.copy()
                for key, value in row.items():
                    if value is None: continue
                    typ = t.c[key].type
                    if isinstance(typ, Uuid): row[key] = UUID(value)
                    elif isinstance(typ, DateTime): row[key] = datetime.fromisoformat(value)
                    elif isinstance(typ, Date): row[key] = date.fromisoformat(value)
                conn.execute(insert(t).values(**row))

    # 4. PostgreSQL DDL 与 Seed 脚本语法 AST 解析
    sql_counts = {}
    for p in (BASE / 'sql').glob('*.sql'):
        sql_counts[p.name] = len(parse_sql(p.read_text(encoding='utf-8')))

    # 5. 执行单元测试套件
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful()

    report = {
        'status': 'passed',
        'tables': len(metadata.tables),
        'columns': sum(len(t.c) for t in metadata.tables.values()),
        'tests_passed': result.testsRun,
        'source_records': 44,
        'snapshot_columns_per_record': 37,
        'files': len(stage['document_files']),
        'business_links': len(stage['document_business_directions']),
        'business_directions_order_verified': True,
        'sql_statements_parsed': sql_counts,
        'sqlite_core_material_import': 'passed',
        'sqlite_tables_created': len(metadata.tables),
        'sqlite_fixture_tables_inserted': list(CORE_IMPORT_TABLES),
        'sqlite_fixture_rows_inserted': {name: len(stage[name]) for name in CORE_IMPORT_TABLES},
        'sqlite_other_tables_without_fixture_import': len(metadata.tables) - len(CORE_IMPORT_TABLES),
        'all_retrieval_blocked': True,
        'limitations': [
            '候选技术基线采用 PostgreSQL 16 + SQLAlchemy 2.0，未连接实库',
            '没有执行生产部署或远程导入',
            '未重新联网核验 44 条政策有效性',
            'OCR 尚未完成',
            'Agent 和数据库服务尚未集成，服务层业务校验及 Agent 接口未实现'
        ]
    }
    (BASE / 'source/validation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
