"""Review-level portable constraint tests; not PostgreSQL deployment tests."""
import unittest
from uuid import uuid4
from sqlalchemy import create_engine, event, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers, Session
from models import metadata, KnowledgeCategory, KnowledgeDocument, DocumentVersion


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        event.listen(self.engine, 'connect', lambda db, _: db.execute('PRAGMA foreign_keys=ON'))
        metadata.create_all(self.engine)
        self.conn = self.engine.connect()
        self.ids = [uuid4() for _ in range(6)]
        cat, doc, v1, v2, f1, chunk = self.ids
        self.conn.execute(insert(metadata.tables['knowledge_categories']).values(id=cat, name='综评与奖学金', sort_order=1))
        self.conn.execute(insert(metadata.tables['knowledge_documents']).values(id=doc, category_id=cat, title='奖学金办法', document_type='政策'))
        for v, code in [(v1, 'A'), (v2, 'B')]:
            self.conn.execute(insert(metadata.tables['document_versions']).values(id=v, document_id=doc, record_code=code, version_no=code, source_url='https://example.edu/policy'))
        self.conn.execute(insert(metadata.tables['document_files']).values(id=f1, version_id=v1, file_role='original', storage_key='a.pdf', original_name='a.pdf'))

    def tearDown(self):
        self.conn.close()
        self.engine.dispose()

    def test_cross_version_chunk_rejected(self):
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(metadata.tables['knowledge_chunks']).values(version_id=self.ids[3], file_id=self.ids[4], chunk_no=1, content='正文'))

    def test_constraint_names_unique(self):
        for t in metadata.tables.values():
            names=[c.name for c in t.constraints]
            self.assertEqual(len(names),len(set(names)),t.name)

    def test_policy_relation_self_link_rejected(self):
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(metadata.tables['document_version_relations']).values(from_version_id=self.ids[2],to_version_id=self.ids[2],relation_type='replaces',evidence_note='测试'))

    def test_feedback_workflow_tables_exist(self):
        self.assertIn('answer_feedback',list(metadata.tables))
        self.assertIn('feedback_review_links',list(metadata.tables))

    def test_milestone_precision_enforced(self):
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(metadata.tables['document_milestones']).values(version_id=self.ids[2],name='申请',precision='time',raw_text='原文'))

    def test_multiple_sources_same_version(self):
        t=metadata.tables['document_file_sources']
        other=uuid4()
        self.conn.execute(insert(metadata.tables['document_files']).values(id=other,version_id=self.ids[2],file_role='extracted',storage_key='a.md',original_name='a.md'))
        self.conn.execute(insert(t).values(file_id=other,source_file_id=self.ids[4],version_id=self.ids[2]))
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(t).values(file_id=other,source_file_id=self.ids[4],version_id=self.ids[3]))

    def test_message_result_link_exists(self):
        sid,other,request,reply,wrong_reply,tid,rid=[uuid4() for _ in range(7)]
        for s in [sid,other]:self.conn.execute(insert(metadata.tables['conversation_sessions']).values(id=s))
        for mid,s,role,seq in [(request,sid,'user',1),(reply,sid,'assistant',2),(wrong_reply,other,'assistant',1)]:
            self.conn.execute(insert(metadata.tables['interaction_messages']).values(id=mid,session_id=s,role=role,sequence_no=seq,content='测试'))
        self.conn.execute(insert(metadata.tables['agent_tasks']).values(id=tid,request_message_id=request,session_id=sid,task_type='policy_qa'))
        self.conn.execute(insert(metadata.tables['task_results']).values(id=rid,task_id=tid,session_id=sid,result_no=1,result_type='answer',content='结果'))
        link=metadata.tables['message_result_links']
        self.conn.execute(insert(link).values(message_id=reply,result_id=rid,session_id=sid))
        for message in [request,wrong_reply]:
            with self.subTest(message=message),self.assertRaises(IntegrityError):
                self.conn.execute(insert(link).values(message_id=message,result_id=rid,session_id=sid))
        feedback_id,review_id=uuid4(),uuid4()
        fb=metadata.tables['answer_feedback']
        self.conn.execute(insert(fb).values(id=feedback_id,message_id=reply,session_id=sid,version_id=self.ids[2],feedback_type='source',description='来源存疑'))
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(fb).values(message_id=request,session_id=sid,feedback_type='other',description='错误角色'))
        self.conn.execute(insert(metadata.tables['verification_tasks']).values(id=review_id,version_id=self.ids[2],task_type='source',description='核对反馈'))
        relation=metadata.tables['feedback_review_links']
        self.conn.execute(insert(relation).values(feedback_id=feedback_id,verification_task_id=review_id,version_id=self.ids[2]))
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(relation).values(feedback_id=feedback_id,verification_task_id=review_id,version_id=self.ids[3]))
        with self.assertRaises(IntegrityError):
            self.conn.execute(fb.update().where(fb.c.id==feedback_id).values(status='resolved'))

    def test_duplicate_record_code_rejected(self):
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(metadata.tables['document_versions']).values(document_id=self.ids[1], record_code='A', version_no='C', source_url='https://example.edu'))

    def test_unreviewed_defaults_block_answer(self):
        row = self.conn.execute(metadata.tables['document_versions'].select()).mappings().first()
        self.assertEqual(row['retrieval_status'], 'blocked')
        self.assertEqual(row['timeliness_verification_status'], 'pending')
        self.assertEqual(row['v1_inclusion_status'], 'pending')

    def test_invalid_status_rejected(self):
        with self.assertRaises(IntegrityError):
            self.conn.execute(insert(metadata.tables['document_versions']).values(document_id=self.ids[1], record_code='X', version_no='X', source_url='https://example.edu', retrieval_status='auto_enabled'))

    def test_referenced_version_delete_restricted(self):
        with self.assertRaises(IntegrityError):
            self.conn.execute(metadata.tables['document_versions'].delete().where(metadata.tables['document_versions'].c.id==self.ids[2]))

    def test_orm_relationships(self):
        configure_mappers()
        with Session(self.engine) as session:
            c=KnowledgeCategory(name='科研实践与实验室', sort_order=2)
            d=KnowledgeDocument(title='实验室通知', document_type='通知', category=c)
            v=DocumentVersion(record_code='ORM',version_no='1',source_url='https://example.edu',document=d)
            session.add(v)
            session.flush()
            self.assertEqual(v.document.category.name,'科研实践与实验室')
            self.assertEqual(v.retrieval_status,'blocked')


if __name__ == '__main__':
    unittest.main(verbosity=2)
