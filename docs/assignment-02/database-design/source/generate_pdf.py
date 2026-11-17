"""Generate the formal Word document, update its TOC, and export the PDF."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from build_specification import BASE, build, digest
from render_diagrams import render, browser_path as find_browser

def generate(output=None, browser=None, rerender=False):
    render(browser, rerender)
    _, protected = build()
    docx = BASE / 'source/AgentX_数据库设计说明书.docx'
    pdf = Path(output) if output else BASE / 'AgentX_数据库设计说明书.pdf'
    pdf.parent.mkdir(parents=True, exist_ok=True)
    author_python = os.environ.get('CODEMIND_DOCX_PYTHON', sys.executable)
    subprocess.run([author_python, str(BASE/'source/create_word_specification.py'), '--output', str(docx)], check=True)
    layout_report = BASE / 'source/document_layout_report.json'
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(BASE/'source/update_fields_export.ps1'), '-DocxPath', str(docx), '-PdfPath', str(pdf), '-ReportPath', str(layout_report)], check=True)
    assert all(digest(BASE/name) == value for name,value in protected.items())
    layout = json.loads(layout_report.read_text(encoding='utf-8-sig'))
    report = {'document': pdf.name, 'editable_word': 'source/' + docx.name,
              'version': 'V1.3', 'compiled_on': '2026-11-10',
              'pages': layout['pages'], 'toc_count': layout['toc_count'],
              'technical_inputs_unchanged': True, 'database_experiments_rerun': False,
              'tables': 23, 'fields': 233, 'foreign_key_groups': 40,
              'protected_input_sha256': protected}
    (BASE/'source/document_build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Formal PDF:',pdf)
    return pdf

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='生成Word正式说明书并更新目录后导出PDF；不重跑数据库实验')
    parser.add_argument('--output', help='默认AgentX_数据库设计说明书.pdf')
    parser.add_argument('--browser', help='图形首次渲染时的Chrome/Edge路径')
    parser.add_argument('--rerender-diagrams', action='store_true')
    args = parser.parse_args()
    generate(args.output, args.browser, args.rerender_diagrams)
