# -*- coding: utf-8 -*-
"""把 pandoc 默认 reference.docx 改写为中文技术文档样式。

用法：python make_reference.py reference.docx
"""
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

SONG = "宋体"
HEI = "黑体"
KAI = "楷体"
TNR = "Times New Roman"

BLACK = RGBColor(0, 0, 0)


def set_rfonts(rpr, east, ascii_font):
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)
    rfonts.set(qn("w:eastAsia"), east)
    rfonts.set(qn("w:cs"), ascii_font)


def font(doc, name, east=SONG, ascii_font=TNR, size=None, bold=None, color=BLACK):
    try:
        st = doc.styles[name]
    except KeyError:
        return
    rpr = st.element.get_or_add_rPr()
    set_rfonts(rpr, east, ascii_font)
    if size is not None:
        st.font.size = Pt(size)
    if bold is not None:
        st.font.bold = bold
    if color is not None:
        st.font.color.rgb = color


def para(doc, name, before=0, after=0, line=1.5, align=None, indent=None, keep=False):
    try:
        st = doc.styles[name]
    except KeyError:
        return
    pf = st.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line is not None:
        pf.line_spacing = line
    if align is not None:
        pf.alignment = align
    pf.first_line_indent = Pt(indent) if indent is not None else None
    pf.keep_with_next = keep


def set_doc_defaults(doc):
    styles = doc.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        return
    rpr_default = defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        return
    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        rpr_default.append(rpr)
    set_rfonts(rpr, SONG, TNR)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "24")
    rpr.append(sz)


def add_table_borders(doc):
    try:
        st = doc.styles["Table"]
    except KeyError:
        return
    tbl = st.element
    tblpr = tbl.find(qn("w:tblPr"))
    if tblpr is None:
        tblpr = OxmlElement("w:tblPr")
        tbl.insert(0, tblpr)
    existing = tblpr.find(qn("w:tblBorders"))
    if existing is not None:
        tblpr.remove(existing)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblpr.append(borders)


def main(path):
    doc = Document(path)
    set_doc_defaults(doc)

    font(doc, "Normal", SONG, TNR, 12)
    para(doc, "Normal", 0, 0, 1.5, WD_ALIGN_PARAGRAPH.JUSTIFY)

    for name in ("Body Text", "First Paragraph"):
        font(doc, name, SONG, TNR, 12)
        para(doc, name, 0, 0, 1.5, WD_ALIGN_PARAGRAPH.JUSTIFY, indent=24)

    font(doc, "Compact", SONG, TNR, 12)
    para(doc, "Compact", 0, 0, 1.5, WD_ALIGN_PARAGRAPH.JUSTIFY, indent=0)

    font(doc, "Heading 1", HEI, HEI, 16, True)
    para(doc, "Heading 1", 18, 12, 1.5, WD_ALIGN_PARAGRAPH.CENTER, keep=True)
    font(doc, "Heading 2", HEI, HEI, 14, True)
    para(doc, "Heading 2", 12, 6, 1.5, WD_ALIGN_PARAGRAPH.LEFT, keep=True)
    font(doc, "Heading 3", HEI, HEI, 12, True)
    para(doc, "Heading 3", 6, 3, 1.5, WD_ALIGN_PARAGRAPH.LEFT, keep=True)
    font(doc, "Heading 4", HEI, HEI, 12, True)
    para(doc, "Heading 4", 6, 3, 1.5, WD_ALIGN_PARAGRAPH.LEFT, keep=True)

    font(doc, "Title", HEI, HEI, 26, True)
    para(doc, "Title", 0, 12, 1.5, WD_ALIGN_PARAGRAPH.CENTER)
    font(doc, "Subtitle", KAI, TNR, 14)
    para(doc, "Subtitle", 0, 0, 1.5, WD_ALIGN_PARAGRAPH.CENTER)

    for name in ("Caption", "Image Caption", "Table Caption"):
        font(doc, name, SONG, TNR, 10.5)
        para(doc, name, 6, 12, 1.0, WD_ALIGN_PARAGRAPH.CENTER)

    font(doc, "Block Text", KAI, TNR, 12)
    para(doc, "Block Text", 6, 6, 1.5, WD_ALIGN_PARAGRAPH.JUSTIFY)

    add_table_borders(doc)
    doc.save(path)
    print("reference.docx updated:", path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reference.docx")
