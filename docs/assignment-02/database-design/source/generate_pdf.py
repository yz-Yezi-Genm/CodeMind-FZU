import markdown_it
import subprocess
from pathlib import Path

base_dir = Path(r'docs/assignment-02/database-design')
md_file = base_dir / '完整审核稿_v1.2.md'
md_text = md_file.read_text(encoding='utf-8')

# parse markdown
parser = markdown_it.MarkdownIt().enable('table').enable('strikethrough')
body_html = parser.render(md_text)

css = """
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #24292e;
    margin: 0;
    padding: 0;
}
h1, h2, h3, h4 {
    color: #1a365d;
    font-weight: 600;
}
h1 {
    font-size: 18pt;
    border-bottom: 2px solid #2b6cb0;
    padding-bottom: 6px;
    margin-top: 28px;
    page-break-before: always;
}
h1:first-of-type {
    page-break-before: avoid;
}
h2 {
    font-size: 13pt;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 20px;
}
h3 {
    font-size: 11pt;
    margin-top: 14px;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 8.5pt;
    page-break-inside: auto;
}
tr {
    page-break-inside: avoid;
    page-break-after: auto;
}
th, td {
    border: 1px solid #cbd5e0;
    padding: 5px 7px;
    text-align: left;
    vertical-align: top;
}
th {
    background-color: #edf2f7;
    font-weight: bold;
    color: #2d3748;
}
tr:nth-child(even) {
    background-color: #f7fafc;
}
pre {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 8px;
    font-family: Consolas, monospace;
    font-size: 8.5pt;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    page-break-inside: avoid;
}
code {
    font-family: Consolas, monospace;
    font-size: 8.5pt;
    background-color: #f1f5f9;
    padding: 2px 4px;
    border-radius: 3px;
    color: #c53030;
}
pre code {
    background-color: transparent;
    padding: 0;
    color: inherit;
}
blockquote {
    border-left: 4px solid #3182ce;
    margin: 10px 0;
    padding: 6px 12px;
    background-color: #ebf8ff;
    color: #2c5282;
}
hr {
    border: 0;
    height: 1px;
    background: #e2e8f0;
    margin: 16px 0;
}
"""

full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>CodeMind-FZU 数据库设计说明书</title>
<style>{css}</style>
</head>
<body>
{body_html}
</body>
</html>"""

temp_html = base_dir / 'temp_doc.html'
temp_html.write_text(full_html, encoding='utf-8')

pdf_output = base_dir / 'CodeMind-FZU_数据库设计说明书.pdf'
edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

cmd = [
    edge_path,
    '--headless',
    '--disable-gpu',
    '--no-pdf-header-footer',
    f'--print-to-pdf={pdf_output.resolve()}',
    str(temp_html.resolve())
]

subprocess.run(cmd, check=True)
temp_html.unlink()
print(f'PDF successfully generated: {pdf_output} (Size: {pdf_output.stat().st_size} bytes)')
