"""Check document content, pagination and preservation; no DB engine or tests."""
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET
import fitz
from models import MODEL_TABLES, metadata
from build_specification import BASE, digest

def normalized(value):
    return re.sub(r'\s+','',value)

def verify():
    pdf = BASE/'AgentX_数据库设计说明书.pdf'
    word = BASE/'source/AgentX_数据库设计说明书.docx'
    record = json.loads((BASE/'source/document_build_report.json').read_text(encoding='utf-8'))
    for name, sha in record['protected_input_sha256'].items():
        assert digest(BASE/name)==sha, '技术输入变化：'+name
    with fitz.open(pdf) as document:
        pages = [normalized(page.get_text()) for page in document]
        text = ''.join(pages)
        assert record['pages']==len(document)
        assert record['toc_count']==1
        assert sum(bool(page.get_images()) for page in document)==6
        assert 'erDiagram' not in text and 'flowchartTB' not in text
        assert all(term in pages[0] for term in ['CodeMind-FZU','数据库设计说明书','AgentX','V1.3','2026年11月10日'])
        for index, page in enumerate(pages[1:],2):
            assert f'第{index}页共{len(document)}页' in page, '页码不一致：'+str(index)
        layout = json.loads((BASE/'source/document_layout_report.json').read_text(encoding='utf-8-sig'))
        for heading in layout['headings']:
            assert normalized(heading['title']) in pages[heading['page']-1], '标题页码：'+heading['title']
        for _, table in MODEL_TABLES:
            assert table.name in text, table.name
            for column in table.c:
                assert column.name in text, table.name+'.'+column.name
            for constraint in table.constraints:
                assert constraint.name in text, constraint.name
        assert '23张表' in text and '8张表' in text
        assert all(value in text for value in ['未实际连接PostgreSQL','未完成真实政策联网复核','OCR尚未完成','Agent和数据库服务尚未集成'])
        errors = [i+1 for i,page in enumerate(document) if any(block[0]<-1 or block[1]<-1 or block[2]>page.rect.width+1 or block[3]>page.rect.height+1 for block in page.get_text('blocks'))]
        assert not errors, '文本超出页面：'+str(errors)
    with zipfile.ZipFile(word) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        styles = ET.fromstring(archive.read('word/styles.xml'))
        style_names = {s.get('{'+ns['w']+'}styleId'):s.find('w:name',ns).get('{'+ns['w']+'}val','').lower() for s in styles.findall('w:style',ns) if s.find('w:name',ns) is not None}
        fields=''.join(x.text or '' for x in root.findall('.//w:instrText',ns))
        assert 'TOC' in fields
        toc_rows=[]
        for paragraph in root.findall('.//w:p',ns):
            style=paragraph.find('./w:pPr/w:pStyle',ns)
            if style is not None and style_names.get(style.attrib.get('{'+ns['w']+'}val',''),'') in ('toc 1','toc 2','toc1','toc2'):
                value=''.join(x.text or '' for x in paragraph.findall('.//w:t',ns))
                match=re.match(r'^(.*?)\s*(\d+)\s*$',value)
                if match:
                    title,page=match.group(1),int(match.group(2))
                    assert normalized(title) in pages[page-1], '目录页码：'+value
                    toc_rows.append(value)
        assert len(toc_rows)>=40, '目录未完整更新'
        images=[name for name in archive.namelist() if name.startswith('word/media/') and not name.endswith('/')]
        assert len(images)==6
    result={'status':'passed','checks':['正式封面','Word自动目录及标题页码','全篇页码及总页数','6幅嵌入图形','23表233字段和全部约束','技术输入SHA-256不变','四项实施状态保留','页面文本边界'],
            'pages':record['pages'],'toc_entries_verified':len(toc_rows),'embedded_figures':6,
            'database_experiments_rerun':False}
    (BASE/'source/document_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':
    verify()
