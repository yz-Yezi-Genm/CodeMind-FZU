"""Author the editable Word specification from the structured Markdown source."""
import argparse
import json
from pathlib import Path
import re
from docx import Document
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

BASE = Path(__file__).resolve().parents[1]

def xml(tag, **attrs):
    node = OxmlElement('w:' + tag)
    for key, value in attrs.items():
        node.set(qn('w:' + key), str(value))
    return node

def font(run, size=None, bold=False):
    run.font.name = 'Times New Roman'
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), '黑体' if bold else '宋体')
    run.font.color.rgb = RGBColor(0, 0, 0)
    run.bold = bold
    if size:
        run.font.size = Pt(size)

def text(value):
    value = value.replace('<br/>', '\n').replace('<br>', '\n').replace('\\|', '|')
    for key, index in [('standard', '1'), ('postgres', '2'), ('sqlalchemy', '3')]:
        value = value.replace('[^' + key + ']:', '[' + index + '] ').replace('[^' + key + ']', '[' + index + ']')
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1（\2）', value)
    return value.replace('**', '').replace('`', '')

def field(paragraph, instruction):
    run = paragraph.add_run()
    run._r.append(xml('fldChar', fldCharType='begin'))
    code = xml('instrText')
    code.set(qn('xml:space'), 'preserve')
    code.text = ' ' + instruction + ' '
    run._r.append(code)
    run._r.append(xml('fldChar', fldCharType='separate'))
    run._r.append(xml('fldChar', fldCharType='end'))
    font(run, 9)

def configure_section(section, landscape=False):
    section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    section.page_width = Mm(420 if landscape else 210)
    section.page_height = Mm(297)
    section.left_margin = Mm(23)
    section.right_margin = Mm(23)
    section.top_margin = Mm(25)
    section.bottom_margin = Mm(23)
    section.header_distance = Mm(13)
    section.footer_distance = Mm(13)

def header_footer(section):
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    font(header.add_run('CodeMind-FZU 数据库设计说明书'), 9)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(footer.add_run('第 '), 9)
    field(footer, 'PAGE')
    font(footer.add_run(' 页  共 '), 9)
    field(footer, 'NUMPAGES')
    font(footer.add_run(' 页'), 9)

def make_table(document, rows):
    count = len(rows[0])
    ratios = {6: [.23,.24,.20,.07,.07,.19], 4: [.24,.31,.18,.27], 2: [.39,.61]}.get(count, [.30,.32,.38])
    if count == 3 and rows[0][1] == '类型':
        ratios = [.37,.13,.50]
    table = document.add_table(rows=1, cols=count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    width = 164
    widths = [Mm(width*r) for r in ratios]
    for column, cell_width in zip(table.columns, widths):
        column.width = cell_width
    width_node = table._tbl.tblPr.find(qn('w:tblW'))
    width_node.set(qn('w:type'), 'dxa')
    width_node.set(qn('w:w'), str(Mm(width).twips))
    borders = xml('tblBorders')
    for name in ('top','left','bottom','right','insideH','insideV'):
        borders.append(xml(name, val='single', sz=4, color='D9D9D9'))
    table._tbl.tblPr.append(borders)
    for row_index, values in enumerate(rows):
        row = table.rows[0] if row_index == 0 else table.add_row()
        row._tr.get_or_add_trPr().append(xml('cantSplit'))
        if row_index == 0:
            row._tr.get_or_add_trPr().append(xml('tblHeader'))
        for column, value in enumerate(values):
            cell = row.cells[column]
            cell.width = widths[column]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props = cell._tc.get_or_add_tcPr()
            margins = xml('tcMar')
            for side in ('top','bottom','left','right'):
                margins.append(xml(side, w=75, type='dxa'))
            props.append(margins)
            if row_index == 0:
                props.append(xml('shd', val='clear', fill='EDEDED'))
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.first_line_indent = Mm(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.15
            paragraph.paragraph_format.keep_with_next = row_index == 0
            if len(str(value)) < 5:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            font(paragraph.add_run(text(value)), 9, row_index == 0)
    document.add_paragraph().paragraph_format.space_after = Pt(2)

def create(output):
    document = Document()
    configure_section(document.sections[0])
    document.sections[0].different_first_page_header_footer = True
    header_footer(document.sections[0])
    normal = document.styles['Normal']
    normal.font.name = 'Times New Roman'
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), '宋体')
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0,0,0)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.first_line_indent = Pt(24)
    for level, size in [(1,16),(2,14),(3,12)]:
        style = document.styles['Heading ' + str(level)]
        style.font.name = 'Times New Roman'
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0,0,0)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), '黑体')
        style.paragraph_format.first_line_indent = Pt(0)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(8)
        if level == 1:
            style.paragraph_format.page_break_before = True
    for name, size, after in [('toc 1',11,5),('toc 2',10.5,2)]:
        existing = next((style for style in document.styles if style.name.lower()==name),None)
        style = existing if existing is not None else document.styles.add_style(name,WD_STYLE_TYPE.PARAGRAPH,builtin=True)
        style.font.name = 'Times New Roman'
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0,0,0)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'宋体')
        style.paragraph_format.line_spacing = 1
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.first_line_indent = Pt(0)
    for label, size, before, after in [('CodeMind-FZU',26,120,16),('数据库设计说明书',23,0,26),('Database Design Specification',11,0,55)]:
        paragraph = document.add_paragraph(style='Title' if size == 26 else 'Normal')
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        paragraph.paragraph_format.space_before = Pt(before)
        paragraph.paragraph_format.space_after = Pt(after)
        font(paragraph.add_run(label), size, size>15)
    for label in ['项目名称：CodeMind-FZU 校园事务与发展信息智能助手', '文档名称：数据库设计说明书',
                  '文档版本：V1.3（文档规范化稿）', '技术基线：v1.2', '团队名称：AgentX', '编制人：王智洋', '编制日期：2026年11月10日']:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        paragraph.paragraph_format.space_after = Pt(8)
        font(paragraph.add_run(label),11)
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(35)
    font(paragraph.add_run('2026 秋软件工程实践 · 第二次团队作业'),10)
    document.add_page_break()
    paragraph = document.add_paragraph('目 录')
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    for run in paragraph.runs:
        font(run,16,True)
    field(document.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
    tokens = json.loads((BASE/'source/document_blocks.json').read_text(encoding='utf-8'))
    i = 0
    foldout = False
    while i < len(tokens):
        token = tokens[i]
        if token['type'] == 'heading_open':
            level = int(token['tag'][1])
            if level > 1:
                heading = text(tokens[i+1]['content'])
                wide_heading = heading.startswith('4 逻辑结构设计') or heading.startswith('4.3 资料治理关系')
                if wide_heading:
                    section = document.add_section(WD_SECTION_START.NEW_PAGE)
                    configure_section(section,True)
                    section.different_first_page_header_footer = False
                    foldout = True
                paragraph = document.add_paragraph(heading, style='Heading ' + str(min(3,level-1)))
                if wide_heading:
                    paragraph.paragraph_format.page_break_before = False
            i += 3
            continue
        if token['type'] == 'paragraph_open':
            item = tokens[i+1]
            images = [x for x in item.get('children',[]) if x['type']=='image']
            if images:
                attrs = dict(images[0]['attrs'])
                image = BASE / attrs['src']
                wide = image.stem in ('overview', 'governance')
                if wide and not foldout:
                    section = document.add_section(WD_SECTION_START.NEW_PAGE)
                    configure_section(section, True)
                    section.different_first_page_header_footer = False
                    foldout = True
                from PIL import Image
                with Image.open(image) as picture:
                    width, height = picture.size
                max_width, max_height = (365,190) if wide else (164,150 if image.stem=='concept' else 190)
                scale = min(max_width/width, max_height/height)
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.first_line_indent = Pt(0)
                paragraph.paragraph_format.keep_with_next = True
                paragraph.paragraph_format.line_spacing = 1
                run = paragraph.add_run()
                shape = run.add_picture(str(image), width=Mm(width*scale), height=Mm(height*scale))
                shape._inline.docPr.set('descr', images[0]['content'])
            else:
                value = text(item['content'])
                paragraph = document.add_paragraph()
                is_table_caption = bool(re.match(r'^表\s*(?:\d+|[A-F])-\d+',value))
                is_figure_caption = bool(re.match(r'^图\s*\d+-\d+',value))
                if is_table_caption or is_figure_caption:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    paragraph.paragraph_format.first_line_indent = Pt(0)
                    paragraph.paragraph_format.keep_with_next = is_table_caption
                    font(paragraph.add_run(value),10.5)
                else:
                    font(paragraph.add_run(value))
                    if i+4 < len(tokens) and tokens[i+3]['type']=='paragraph_open' and re.match(r'^表\s*(?:\d+|[A-F])-\d+',text(tokens[i+4]['content'])):
                        paragraph.paragraph_format.keep_with_next = True
                if is_figure_caption and foldout:
                    section = document.add_section(WD_SECTION_START.NEW_PAGE)
                    configure_section(section)
                    section.different_first_page_header_footer = False
                    foldout = False
            i += 3
            continue
        if token['type'] == 'table_open':
            rows, row = [], []
            i += 1
            while tokens[i]['type'] != 'table_close':
                if tokens[i]['type'] == 'tr_open': row = []
                elif tokens[i]['type'] == 'inline': row.append(tokens[i]['content'])
                elif tokens[i]['type'] == 'tr_close': rows.append(row)
                i += 1
            make_table(document,rows)
        elif token['type'] == 'fence':
            if token.get('info','').strip() == 'mermaid':
                raise ValueError('正式文档必须插入已渲染图形。')
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.line_spacing = 1
            paragraph.paragraph_format.space_after = Pt(6)
            font(paragraph.add_run(token['content'].rstrip()),9)
        i += 1
    document.core_properties.title = 'CodeMind-FZU 数据库设计说明书'
    document.core_properties.author = 'AgentX 王智洋'
    document.core_properties.subject = '数据库详细设计 v1.2 技术基线，v1.3文档规范化'
    for style in document.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):
            border.getparent().remove(border)
    for paragraph in document.paragraphs:
        for border in list(paragraph._p.iter(qn('w:pBdr'))):
            border.getparent().remove(border)
    update = document.settings.element.find(qn('w:updateFields'))
    if update is None:
        document.settings.element.append(xml('updateFields', val='true'))
    else:
        update.set(qn('w:val'), 'true')
    document.save(output)
    print('Editable Word:',output)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(BASE/'source/AgentX_数据库设计说明书.docx'))
    create(Path(parser.parse_args().output))
