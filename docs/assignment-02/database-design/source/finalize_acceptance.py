"""Build and package the formal specification without rerunning DB experiments."""
from pathlib import Path
import hashlib
import json
import zipfile

from generate_pdf import generate
from build_specification import BASE, PROTECTED, digest
from verify_specification import verify

def main():
    before = {name: digest(BASE/name) for name in PROTECTED}
    generate()
    verify()
    assert before == {name: digest(BASE/name) for name in PROTECTED}
    historical = {'CodeMind-FZU_数据库设计说明书.pdf', '完整审核稿_v1.2.md',
                  '数据库详细设计说明书_v1.2.md', '修订说明_v1.2.md'}
    suffixes = {'.md','.py','.json','.sql','.csv','.txt','.mmd','.svg','.png','.pdf','.docx','.ps1'}
    files = sorted(p for p in BASE.rglob('*') if p.is_file()
                   and not any(part.startswith('.') or part=='__pycache__' for part in p.relative_to(BASE).parts[:-1])
                   and (p.suffix in suffixes or p.name=='.gitattributes')
                   and p.name not in historical
                   and p.name not in {'document_blocks.json','交付文件校验清单.json'}
                   and not p.name.startswith('~$'))
    for path in files:
        if path.relative_to(BASE).as_posix() not in before and path.suffix in {'.md','.py','.json','.sql','.csv','.txt','.mmd','.svg','.ps1'}:
            content = path.read_bytes()
            if b'\r\n' in content:
                path.write_bytes(content.replace(b'\r\n',b'\n'))
    manifest = [dict(path=p.relative_to(BASE).as_posix(), bytes=p.stat().st_size, sha256=digest(p)) for p in files]
    check = BASE/'交付文件校验清单.json'
    check.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    root = BASE.parents[2] if BASE.parent.name=='assignment-02' else BASE.parent
    target = root/'AgentX_数据库设计说明书_v1.3.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in files+[check]:
            archive.write(p,'AgentX_数据库设计说明书_v1.3/'+p.relative_to(BASE).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for record in manifest:
            assert hashlib.sha256(archive.read('AgentX_数据库设计说明书_v1.3/'+record['path'])).hexdigest()==record['sha256']
    print('Verified document package:',target)

if __name__=='__main__':
    main()
