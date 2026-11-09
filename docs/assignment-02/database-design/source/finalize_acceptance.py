"""Rebuild current review documents, PDF, checksums and a separate review archive."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import shutil
import zipfile
import os
import csv
from build_deliverables import BASE, ROOT


def run(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True)

def main():
    # Exercise the shipped fixture without overwriting the actual-material preview.
    with tempfile.TemporaryDirectory(prefix='codemind-fixture-') as temp:
        clean_root = Path(temp) / 'repo'
        sample = clean_root / 'docs/assignment-02/database-design'
        shutil.copytree(BASE / 'source', sample / 'source', ignore=shutil.ignore_patterns('__pycache__', '业务方向顺序修正'))
        legacy = clean_root / 'knowledge_base/政策资料'
        legacy.mkdir(parents=True)
        # Recreate the legacy 31-row scenario from the frozen fixture; the
        # standalone ZIP must not require files elsewhere on the recipient's PC.
        with (BASE / 'source/fixtures/知识库索引_44条_fixture.csv').open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            fields, records = reader.fieldnames, list(reader)
        with (legacy / '知识库索引.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records[:31])
        clean_env = dict(os.environ)
        clean_env.pop('CODEMIND_KB_ROOT', None)
        subprocess.run([sys.executable, str(sample / 'source/build_deliverables.py')], check=True, env=clean_env)
        summary = json.loads((sample / 'source/build_summary.json').read_text(encoding='utf-8'))
        assert summary['data_source_type'] == 'builtin_fixture'
        stage = json.loads((sample / 'knowledge-base/入库预览_44条.json').read_text(encoding='utf-8'))
        assert len(stage['document_files']) == 149
        assert all(f['processing_status'] == 'failed' and f['sha256'] is None for f in stage['document_files'])
        assert all('原始索引记录状态' in f['processing_note'] for f in stage['document_files'])
        assert sum(v['extraction_status'] == 'extracted' for v in stage['document_versions']) == 43
        subprocess.run([sys.executable, str(sample / 'source/validate_deliverables.py')], check=True, env=clean_env)
    run(BASE / 'source/build_deliverables.py')
    run(BASE / 'source/validate_deliverables.py')
    report = json.loads((BASE / 'source/validation_report.json').read_text(encoding='utf-8'))
    assert report['tests_passed'] == 21
    note = '\n\n## 验收收尾修订（2026-11-09）\n\n当前验证为20项全部通过；历史修订记录中的18项保留为当时结果。内置fixture仅包含索引，不含149个物理文件：文件缺失时processing_status=failed、sha256=NULL，并保留原索引状态说明。document_versions.extraction_status及原始快照表示原索引登记的43条已提取、1条待OCR，不表示当前环境具有文件。已完整运行fixture生成与离线验证。build_summary使用仓库相对路径或external_local_materials标识。PDF及校验清单已重新生成。23表233字段及ORM结构保持不变。\n'
    revision = BASE / '修订说明_v1.2.md'
    text = revision.read_text(encoding='utf-8').split('## 验收收尾修订（2026-11-09）')[0].rstrip()
    note = note.replace('当前验证为20项全部通过', '上一轮验证为20项全部通过')
    note += '\n本轮复现性修订：默认选择顺序调整为CLI、环境变量、外部资料、完整44条fixture、仓库旧索引。新增干净克隆回归测试，当前21项测试全部通过；此前20项为上一轮记录。临时仓库保留旧索引且不提供外部资料，不传--data-dir完成默认生成与验证。\n'
    revision.write_text(text + note, encoding='utf-8')
    validation = BASE / '验证报告_v1.2.md'
    text = re.sub(r'\d+项自动测试通过', str(report['tests_passed']) + '项自动测试通过', validation.read_text(encoding='utf-8'))
    text = text.split('\nfixture复现验证：')[0].rstrip()
    text = text.replace('43条正文已提取、1条待OCR', '原索引登记43条正文已提取、1条待OCR') if '原索引登记43条' not in text else text
    text += '\n\nfixture复现验证：149个文件记录均为failed、SHA-256为空；原索引提取记录43/1保留在版本字段及快照中，与物理文件状态分开。数据源路径仅记录相对路径或类型标识。\n'
    validation.write_text(text, encoding='utf-8')
    parts = ['数据库详细设计说明书_v1.2.md', '架构与概念设计确认说明_v1.2.md', 'relational-model/关系数据模型_v1.2.md', 'data-dictionary/数据字典_v1.2.md', 'data-dictionary/约束与索引设计_v1.2.md', 'orm/ORM映射说明_v1.2.md', 'knowledge-base/知识库入库映射与存储方案_v1.2.md', 'knowledge-base/范围调整与交接说明_v1.2.md', '修订说明_v1.2.md', '业务回答与反馈规则_v1.2.md', '验证报告_v1.2.md']
    full = '# 数据库详细设计审核稿 v1.2\n\n' + '\n\n---\n\n'.join((BASE / p).read_text(encoding='utf-8') for p in parts)
    (BASE / '完整审核稿_v1.2.md').write_text(full, encoding='utf-8')
    run(BASE / 'source/generate_pdf.py')
    files = sorted(p for p in BASE.rglob('*') if p.is_file() and not any(part.startswith('.') or part == '__pycache__' for part in p.relative_to(BASE).parts[:-1]) and '校验清单' not in p.name and not p.name.startswith('给丁晓炜_') and p.name not in ('finalize_revision.py', 'revise_v12_review.py') and (p.suffix in ('.md', '.py', '.json', '.sql', '.csv', '.txt', '.mmd', '.svg', '.pdf', '.png') or p.name == '.gitattributes') and not re.search(r'v(?:0\.1|1\.[01])', p.name) and '设计审查问题清单' not in p.name)
    # Match the directory's eol=lf attributes before hashing or packaging.
    for p in files:
        if p.suffix in ('.md', '.py', '.json', '.sql', '.csv', '.txt', '.mmd', '.svg') or p.name == '.gitattributes':
            content = p.read_bytes()
            normalized = content.replace(b'\r\n', b'\n')
            if normalized != content:
                p.write_bytes(normalized)
    manifest = [dict(path=p.relative_to(BASE).as_posix(), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
    target_manifest = BASE / '交付文件校验清单.json'
    target_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    output_dir = ROOT if ROOT != BASE else BASE.parent
    target = output_dir / 'CodeMind-FZU_数据库详细设计_v1.2_验收收尾修订.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for p in files + [target_manifest]:
            archive.write(p, 'CodeMind-FZU_数据库详细设计_v1.2/' + p.relative_to(BASE).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for row in manifest:
            assert hashlib.sha256(archive.read('CodeMind-FZU_数据库详细设计_v1.2/' + row['path'])).hexdigest() == row['sha256']
    print('Verified archive:', target, 'files:', len(files) + 1)

if __name__ == '__main__':
    main()
