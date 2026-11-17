# -*- coding: utf-8 -*-
"""在 pandoc 生成的 docx 上补封面、目录域、页眉页脚和 A4 版面。

用法：python postprocess.py raw.docx final.docx
"""
import sys

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

SONG = "宋体"
HEI = "黑体"
KAI = "楷体"
TNR = "Times New Roman"

CENTER = WD_ALIGN_PARAGRAPH.CENTER
LEFT = WD_ALIGN_PARAGRAPH.LEFT


def set_run_font(run, size, bold=False, east=SONG, ascii_font=TNR):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = ascii_font
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), east)
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)


def para(doc, text="", size=12, bold=False, east=SONG, ascii_font=TNR,
         align=CENTER, before=0, after=0, line=1.5):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.alignment = align
    if text:
        set_run_font(p.add_run(text), size, bold, east, ascii_font)
    return p


def page_break(doc):
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)
    return p


def add_field(paragraph, instr, placeholder="1", size=9):
    def run_with(element):
        run = paragraph.add_run()
        run._r.append(element)
        run.font.size = Pt(size)
        return run

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run_with(begin)

    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    run_with(instr_el)

    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    run_with(sep)

    text = OxmlElement("w:t")
    text.text = placeholder
    run_with(text)

    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run_with(end)


def build_cover(doc):
    made = []
    for _ in range(4):
        made.append(para(doc)._p)
    made.append(para(doc, "CodeMind-FZU", 32, True, HEI, TNR)._p)
    made.append(para(doc)._p)
    made.append(para(doc, "系统设计说明书", 26, True, HEI, HEI)._p)
    made.append(para(doc)._p)
    made.append(para(doc, "System Design Specification", 12, False, TNR, TNR)._p)
    for _ in range(5):
        made.append(para(doc)._p)

    info = [
        "项目名称：CodeMind-FZU 校园事务与发展信息智能助手",
        "文档名称：系统设计说明书",
        "文档版本：V1.0（设计稿）",
        "团队名称：AgentX",
        "编 制 人：薛锦荣",
        "编制日期：2026 年 11 月",
    ]
    for line in info:
        made.append(para(doc, line, 12, False, SONG, TNR, CENTER, 0, 0, 2.0)._p)

    for _ in range(4):
        made.append(para(doc)._p)
    made.append(para(doc, "2026 秋软件工程实践 · 第二次团队作业", 10.5, False, KAI, TNR)._p)
    made.append(page_break(doc)._p)
    return made


def build_toc(doc):
    made = []
    made.append(para(doc, "目　　录", 16, True, HEI, HEI, CENTER, 0, 12, 1.5)._p)

    p = doc.add_paragraph()
    p.paragraph_format.alignment = LEFT

    def fld(kind):
        run = p.add_run()
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), kind)
        run._r.append(el)

    fld("begin")
    run = p.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    run._r.append(instr)
    fld("separate")
    p.add_run("（目录内容将在 Word 中自动更新）")
    fld("end")
    made.append(p._p)

    made.append(page_break(doc)._p)
    return made


def set_header_footer(doc):
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True

    header = sec.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.text = ""
    hp.alignment = CENTER
    set_run_font(hp.add_run("CodeMind-FZU 系统设计说明书"), 9, False, SONG, TNR)
    ppr = hp._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "808080")
    pbdr.append(bottom)
    ppr.append(pbdr)

    footer = sec.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.text = ""
    fp.alignment = CENTER
    set_run_font(fp.add_run("第 "), 9)
    add_field(fp, " PAGE ", "1")
    set_run_font(fp.add_run(" 页　共 "), 9)
    add_field(fp, " NUMPAGES ", "1")
    set_run_font(fp.add_run(" 页"), 9)


def format_tables(doc):
    table_width = 15.3
    for table in doc.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        columns = len(table.columns)
        if columns >= 3:
            widths = [2.9] + [(table_width - 2.9) / (columns - 1)] * (columns - 1)
        elif columns == 2:
            widths = [table_width / 2, table_width / 2]
        else:
            widths = [table_width]
        for row in table.rows:
            for idx, cell in enumerate(row.cells):
                cell.width = Cm(widths[idx])
        for index, row in enumerate(table.rows):
            trpr = row._tr.get_or_add_trPr()
            if index == 0:
                header = OxmlElement("w:tblHeader")
                header.set(qn("w:val"), "true")
                trpr.append(header)
            for cell in row.cells:
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                for p in cell.paragraphs:
                    pf = p.paragraph_format
                    pf.space_before = Pt(0)
                    pf.space_after = Pt(0)
                    pf.line_spacing = 1.0
                    pf.first_line_indent = Pt(0)
                    for run in p.runs:
                        run.font.size = Pt(10.5)
                        if index == 0:
                            run.font.bold = True


def move_to_front(doc, elements):
    body = doc.element.body
    for index, element in enumerate(elements):
        body.remove(element)
        body.insert(index, element)


def main(src, dst):
    doc = Document(src)

    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.54)
    sec.bottom_margin = Cm(2.54)
    sec.left_margin = Cm(3.0)
    sec.right_margin = Cm(2.6)
    sec.header_distance = Cm(1.5)
    sec.footer_distance = Cm(1.75)

    cover = build_cover(doc)
    toc = build_toc(doc)
    move_to_front(doc, cover + toc)

    set_header_footer(doc)
    format_tables(doc)

    props = doc.core_properties
    props.title = "CodeMind-FZU 系统设计说明书"
    props.author = "薛锦荣"
    props.subject = "2026 秋软件工程实践 第二次团队作业"

    doc.save(dst)
    print("postprocess ok:", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
