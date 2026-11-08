"""Offline review validation; deliberately creates only an in-memory SQLite DB."""
from pathlib import Path
from uuid import UUID
from datetime import date, datetime
import json, csv, unittest
from sqlalchemy import create_engine, event, insert, Uuid, Date, DateTime
from pglast import parse_sql
from models import metadata
from build_deliverables import BASE, KB

def main():
    stage=json.loads((BASE/'knowledge-base/入库预览_44条.json').read_text(encoding='utf-8'))
    original=list(csv.DictReader((KB/'知识库索引.csv').open(encoding='utf-8-sig',newline='')))
    by_code={r['记录编号']:r for r in original}
    assert len(metadata.tables)==23
    versions=stage['document_versions']
    assert len(versions)==44 and len({v['record_code'] for v in versions})==44
    assert all(v['import_snapshot']==by_code[v['record_code']] for v in versions)
    assert all(len(v['import_snapshot'])==37 for v in versions)
    assert all(v['retrieval_status']=='blocked' and v['timeliness_verification_status']=='pending' for v in versions)
    assert sum(v['extraction_status']=='extracted' for v in versions)==43
    assert sum(v['extraction_status']=='needs_ocr' for v in versions)==1
    engine=create_engine('sqlite://')
    event.listen(engine,'connect',lambda db,_:db.execute('PRAGMA foreign_keys=ON'))
    metadata.create_all(engine)
    with engine.begin() as conn:
        for name in ['knowledge_categories','business_directions','knowledge_documents','document_versions','document_files','document_business_directions','verification_tasks','document_milestones']:
            t=metadata.tables[name]
            for row in stage[name]:
                row=row.copy()
                for key,value in row.items():
                    if value is None:continue
                    typ=t.c[key].type
                    if isinstance(typ,Uuid):row[key]=UUID(value)
                    elif isinstance(typ,DateTime):row[key]=datetime.fromisoformat(value)
                    elif isinstance(typ,Date):row[key]=date.fromisoformat(value)
                conn.execute(insert(t).values(**row))
    sql_counts={}
    for p in (BASE/'sql').glob('*.sql'):
        sql_counts[p.name]=len(parse_sql(p.read_text(encoding='utf-8')))
    loader=unittest.TestLoader()
    suite=loader.discover(str(Path(__file__).parent),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful()
    report={'status':'passed','tables':len(metadata.tables),'columns':sum(len(t.c) for t in metadata.tables.values()),'tests_passed':result.testsRun,'source_records':44,'snapshot_columns_per_record':37,'files':len(stage['document_files']),'business_links':len(stage['document_business_directions']),'sql_statements_parsed':sql_counts,'sqlite_full_stage_insert':'passed','all_retrieval_blocked':True,'limitations':['没有连接PostgreSQL实库','没有执行部署或远程导入','未重新联网核验44条政策','服务层业务校验未实现']}
    (BASE/'source/validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
