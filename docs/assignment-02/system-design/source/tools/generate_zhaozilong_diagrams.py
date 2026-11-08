#!/usr/bin/env python3
"""Single-source diagram generator for Zhaozilong's assignment-02 deliverables.

Scene dictionaries define nodes, messages, routing, and labels. Draw.io, SVG,
and PNG files are exported from those dictionaries so their content stays
synchronized.
"""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
ARCH_DIR = ROOT / "diagrams" / "architecture"
COMM_DIR = ROOT / "diagrams" / "uml" / "communication"
FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")

P = {
    "ink": "#172033",
    "muted": "#5B6578",
    "line": "#617089",
    "bg": "#F5F8FC",
    "white": "#FFFFFF",
    "blue": "#1F5EFF",
    "blue_soft": "#EAF0FF",
    "cyan": "#0D91A8",
    "cyan_soft": "#E4F7FA",
    "purple": "#7448D8",
    "purple_soft": "#F0EAFF",
    "green": "#16845B",
    "green_soft": "#E6F6EF",
    "orange": "#C46A12",
    "orange_soft": "#FFF1DF",
    "red": "#B93C4F",
    "red_soft": "#FCEBEF",
    "gray_soft": "#EDF1F6",
}


def color(value: str) -> str:
    return P.get(value, value)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def node(id_: str, x: int, y: int, w: int, h: int, title: str,
         lines: list[str] | None = None, fill: str = "white",
         stroke: str = "line", **kwargs) -> dict:
    return {
        "id": id_, "x": x, "y": y, "w": w, "h": h, "title": title,
        "lines": lines or [], "fill": fill, "stroke": stroke, **kwargs,
    }


def message(id_: str, source: str, target: str, points: list[tuple[int, int]],
            stroke: str = "line", label: str = "",
            label_xy: tuple[int, int] | None = None, *,
            dashed: bool = False, width: int = 3) -> dict:
    return {
        "id": id_, "source": source, "target": target, "points": points,
        "stroke": stroke, "label": label,
        "label_xy": label_xy or points[len(points) // 2],
        "dashed": dashed, "width": width,
    }


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
         fill: str, bold: bool = False, anchor: str = "mm") -> None:
    draw.text(xy, value, font=font(size, bold), fill=color(fill), anchor=anchor)


def arrowhead(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]],
              fill: str, width: int) -> None:
    start, end = points[-2], points[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 15
    draw.polygon(
        [
            end,
            (end[0] - length * math.cos(angle - math.pi / 7),
             end[1] - length * math.sin(angle - math.pi / 7)),
            (end[0] - length * math.cos(angle + math.pi / 7),
             end[1] - length * math.sin(angle + math.pi / 7)),
        ],
        fill=color(fill),
    )


def draw_scene(scene: dict, svg_path: Path, png_path: Path) -> None:
    width, height = scene["width"], scene["height"]
    bg = color(scene.get("bg", "bg"))
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    for band in scene.get("bands", []):
        draw.rounded_rectangle(
            (band["x"], band["y"], band["x"] + band["w"], band["y"] + band["h"]),
            radius=22, fill=color(band["fill"]), outline=color(band.get("stroke", "gray_soft")),
            width=2,
        )
        text(draw, (band["x"] + 22, band["y"] + 23), band["label"], 20,
             band.get("text", "blue"), True, "lm")

    for line in scene.get("messages", []):
        pts = line["points"]
        stroke = color(line["stroke"])
        if line.get("dashed"):
            for start, end in zip(pts, pts[1:]):
                length = max(1, int(math.dist(start, end)))
                for offset in range(0, length, 12):
                    a, b = offset / length, min((offset + 7) / length, 1)
                    draw.line(
                        [
                            (start[0] + (end[0] - start[0]) * a,
                             start[1] + (end[1] - start[1]) * a),
                            (start[0] + (end[0] - start[0]) * b,
                             start[1] + (end[1] - start[1]) * b),
                        ],
                        fill=stroke, width=line.get("width", 3),
                    )
        else:
            draw.line(pts, fill=stroke, width=line.get("width", 3), joint="curve")
        arrowhead(draw, pts, stroke, line.get("width", 3))
        if line["label"]:
            lx, ly = line["label_xy"]
            bbox = draw.textbbox((lx, ly), line["label"], font=font(16, True), anchor="mm")
            draw.rounded_rectangle(
                (bbox[0] - 6, bbox[1] - 3, bbox[2] + 6, bbox[3] + 3),
                radius=5, fill=bg,
            )
            text(draw, (lx, ly), line["label"], 16, stroke, True)

    for item in scene["nodes"]:
        x, y, w, h = item["x"], item["y"], item["w"], item["h"]
        draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=16, fill=color(item["fill"]),
            outline=color(item["stroke"]), width=2,
        )
        lines = item["lines"]
        compact = bool(lines) and h < 100
        title_size = min(item.get("title_size", 22), 19) if compact else item.get("title_size", 22)
        line_size = min(item.get("line_size", 16), 14) if compact else item.get("line_size", 16)
        title_y = y + (23 if compact else 31)
        text(draw, (x + w // 2, title_y), item["title"], title_size, "ink", True)
        if lines:
            start_y = y + (45 if compact else 62)
            spacing = (
                min(17, max(14, (h - 48) // len(lines)))
                if compact
                else min(27, max(20, (h - 60) // len(lines)))
            )
            for idx, value in enumerate(lines):
                text(draw, (x + w // 2, start_y + idx * spacing), value,
                     line_size, "muted")
        else:
            text(draw, (x + w // 2, y + h // 2), item["title"], title_size, "ink", True)

    for item in scene.get("labels", []):
        text(draw, item["xy"], item["text"], item.get("size", 18),
             item.get("fill", "ink"), item.get("bold", False))

    for legend in scene.get("legends", []):
        x, y = legend["xy"]
        draw.rounded_rectangle(
            (x, y, x + legend["w"], y + legend["h"]), radius=12,
            fill=color("white"), outline=color("gray_soft"), width=2,
        )
        text(draw, (x + 16, y + 20), legend["title"], 17, "ink", True, "lm")
        for idx, line in enumerate(legend["lines"]):
            text(draw, (x + 16, y + 46 + idx * 21), line, 14, "muted", anchor="lm")

    png_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(png_path)
    write_svg(scene, svg_path)
    write_drawio(scene)


def write_svg(scene: dict, path: Path) -> None:
    width, height = scene["width"], scene["height"]
    bg = color(scene.get("bg", "bg"))
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<style>text{font-family:'Microsoft YaHei',sans-serif}</style>",
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" '
        'refY="5" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" '
        'fill="#617089"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
    ]
    for band in scene.get("bands", []):
        out.append(
            f'<rect x="{band["x"]}" y="{band["y"]}" width="{band["w"]}" '
            f'height="{band["h"]}" rx="22" fill="{color(band["fill"])}" '
            f'stroke="{color(band.get("stroke","gray_soft"))}" stroke-width="2"/>'
        )
        out.append(
            f'<text x="{band["x"] + 22}" y="{band["y"] + 31}" font-size="20" '
            f'font-weight="700" fill="{color(band.get("text","blue"))}">'
            f'{escape(band["label"])}</text>'
        )
    for line in scene.get("messages", []):
        points = " ".join(f"{x},{y}" for x, y in line["points"])
        dashed = ' stroke-dasharray="8 6"' if line.get("dashed") else ""
        out.append(
            f'<polyline points="{points}" fill="none" stroke="{color(line["stroke"])}" '
            f'stroke-width="{line.get("width",3)}"{dashed} marker-end="url(#arrow)"/>'
        )
        if line["label"]:
            x, y = line["label_xy"]
            out.append(
                f'<text x="{x}" y="{y + 6}" text-anchor="middle" font-size="16" '
                f'font-weight="700" fill="{color(line["stroke"])}">{escape(line["label"])}</text>'
            )
    for item in scene["nodes"]:
        out.append(
            f'<rect x="{item["x"]}" y="{item["y"]}" width="{item["w"]}" '
            f'height="{item["h"]}" rx="16" fill="{color(item["fill"])}" '
            f'stroke="{color(item["stroke"])}" stroke-width="2"/>'
        )
        lines = item["lines"]
        compact = bool(lines) and item["h"] < 100
        title_size = min(item.get("title_size", 22), 19) if compact else item.get("title_size", 22)
        line_size = min(item.get("line_size", 16), 14) if compact else item.get("line_size", 16)
        title_y = item["y"] + (34 if compact else 43)
        out.append(
            f'<text x="{item["x"] + item["w"] / 2}" y="{title_y}" text-anchor="middle" '
            f'font-size="{title_size}" font-weight="700" fill="{P["ink"]}">'
            f'{escape(item["title"])}</text>'
        )
        if lines:
            start_y = item["y"] + (55 if compact else 75)
            spacing = (
                min(17, max(14, (item["h"] - 48) // len(lines)))
                if compact
                else min(27, max(20, (item["h"] - 60) // len(lines)))
            )
            for idx, value in enumerate(lines):
                out.append(
                    f'<text x="{item["x"] + item["w"] / 2}" y="{start_y + idx * spacing}" '
                    f'text-anchor="middle" font-size="{line_size}" fill="{P["muted"]}">'
                    f'{escape(value)}</text>'
                )
    for item in scene.get("labels", []):
        out.append(
            f'<text x="{item["xy"][0]}" y="{item["xy"][1] + 6}" text-anchor="middle" '
            f'font-size="{item.get("size",18)}" font-weight="{700 if item.get("bold") else 400}" '
            f'fill="{color(item.get("fill","ink"))}">{escape(item["text"])}</text>'
        )
    for legend in scene.get("legends", []):
        x, y = legend["xy"]
        out.append(
            f'<rect x="{x}" y="{y}" width="{legend["w"]}" height="{legend["h"]}" '
            f'rx="12" fill="#FFFFFF" stroke="{P["gray_soft"]}" stroke-width="2"/>'
            f'<text x="{x+16}" y="{y+27}" font-size="17" font-weight="700" '
            f'fill="{P["ink"]}">{escape(legend["title"])}</text>'
        )
        for idx, value in enumerate(legend["lines"]):
            out.append(
                f'<text x="{x+16}" y="{y+53+idx*21}" font-size="14" '
                f'fill="{P["muted"]}">{escape(value)}</text>'
            )
    out.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")


def write_drawio(scene: dict) -> None:
    cells: list[str] = []
    for idx, band in enumerate(scene.get("bands", [])):
        cells.append(
            f'<mxCell id="band_{idx}" value="{escape(band["label"])}" '
            f'style="rounded=1;whiteSpace=wrap;html=1;fillColor={color(band["fill"])};'
            f'strokeColor={color(band.get("stroke","gray_soft"))};fontColor={color(band.get("text","blue"))};'
            'fontSize=20;fontStyle=1;align=left;spacingLeft=18;" vertex="1" parent="1">'
            f'<mxGeometry x="{band["x"]}" y="{band["y"]}" width="{band["w"]}" '
            f'height="{band["h"]}" as="geometry"/></mxCell>'
        )
    for item in scene["nodes"]:
        value = escape(f"{item['title']}\n" + "\n".join(item["lines"]), {'"': "&quot;"})
        value = value.replace("\n", "&lt;br&gt;")
        cells.append(
            f'<mxCell id="{item["id"]}" value="{value}" '
            f'style="rounded=1;whiteSpace=wrap;html=1;arcSize=12;fillColor={color(item["fill"])};'
            f'strokeColor={color(item["stroke"])};strokeWidth=2;fontColor=#172033;'
            'fontFamily=Microsoft YaHei;fontSize=16;" vertex="1" parent="1">'
            f'<mxGeometry x="{item["x"]}" y="{item["y"]}" width="{item["w"]}" '
            f'height="{item["h"]}" as="geometry"/></mxCell>'
        )
    for line in scene.get("messages", []):
        value = escape(line["label"], {'"': "&quot;"}).replace("\n", "&lt;br&gt;")
        dash = "dashed=1;" if line.get("dashed") else ""
        waypoints = "".join(
            f'<mxPoint x="{x}" y="{y}"/>' for x, y in line["points"][1:-1]
        )
        waypoint_xml = f'<Array as="points">{waypoints}</Array>' if waypoints else ""
        cells.append(
            f'<mxCell id="{line["id"]}" value="{value}" '
            f'style="edgeStyle=orthogonalEdgeStyle;rounded=1;curved=1;html=1;'
            f'endArrow=block;strokeColor={color(line["stroke"])};strokeWidth={line.get("width",3)};'
            f'{dash}fontFamily=Microsoft YaHei;fontSize=14;" edge="1" parent="1" '
            f'source="{line["source"]}" target="{line["target"]}">'
            f'<mxGeometry relative="1" as="geometry">{waypoint_xml}</mxGeometry></mxCell>'
        )
    for idx, item in enumerate(scene.get("labels", [])):
        cells.append(
            f'<mxCell id="label_{idx}" value="{escape(item["text"], {chr(34): "&quot;"})}" '
            f'style="text;html=1;align=center;verticalAlign=middle;fontColor={color(item.get("fill","ink"))};'
            f'fontSize={item.get("size",18)};fontStyle={1 if item.get("bold") else 0};" '
            f'vertex="1" parent="1"><mxGeometry x="{item["xy"][0]-150}" y="{item["xy"][1]-15}" '
            'width="300" height="30" as="geometry"/></mxCell>'
        )
    for idx, legend in enumerate(scene.get("legends", [])):
        value = escape(legend["title"] + "\n" + "\n".join(legend["lines"]))
        value = value.replace("\n", "&lt;br&gt;")
        cells.append(
            f'<mxCell id="legend_{idx}" value="{value}" style="rounded=1;whiteSpace=wrap;'
            'html=1;align=left;verticalAlign=top;spacing=10;fillColor=#FFFFFF;'
            'strokeColor=#EDF1F6;fontFamily=Microsoft YaHei;fontSize=14;" vertex="1" parent="1">'
            f'<mxGeometry x="{legend["xy"][0]}" y="{legend["xy"][1]}" '
            f'width="{legend["w"]}" height="{legend["h"]}" as="geometry"/></mxCell>'
        )
    body = "\n".join("        " + cell for cell in cells)
    filename = scene["drawio_name"]
    diagram_id = Path(filename).stem
    xml = (
        '<mxfile host="app.diagrams.net" modified="2026-11-08T09:00:00.000Z" '
        'agent="CodeMind-FZU" version="24.0.0">\n'
        f'  <diagram name="{escape(scene["title"])}" id="{diagram_id}">\n'
        f'    <mxGraphModel dx="{scene["width"]}" dy="{scene["height"]}" grid="1" '
        'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
        f'page="1" pageScale="1" pageWidth="{scene["width"]}" pageHeight="{scene["height"]}" '
        'math="0" shadow="0">\n'
        '      <root>\n        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n'
        f"{body}\n      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>\n"
    )
    target = ARCH_DIR if scene.get("kind") == "architecture" else COMM_DIR
    (target / filename).write_text(xml, encoding="utf-8")


def architecture_scene() -> dict:
    nodes = [
        node("user", 110, 165, 330, 72, "学生用户", ["统一提问 · 查看引用 · 补充信息"], "white", "blue"),
        node("maintainer", 490, 165, 330, 72, "知识库维护者", ["登记资料 · 核验元数据 · 重建索引"], "white", "blue"),
        node("sources", 870, 165, 390, 72, "学校 / 学院官方网站", ["通知 · 办法 · 附件 · 培养方案"], "white", "blue"),
        node("tavily", 1310, 165, 450, 72, "Tavily 联网工具（候选）", ["按需核验官方公开信息 · 非首版硬依赖"], "white", "blue"),
        node("web", 110, 325, 330, 78, "Web 用户入口", ["HTML / CSS / JavaScript", "提问、追问与引用展示"], "white", "cyan"),
        node("api", 490, 325, 330, 78, "FastAPI 后端", ["POST /api/ask", "校验 / 异常映射 / 统一响应"], "white", "cyan"),
        node("poc", 870, 325, 390, 78, "现有原型与离线 PoC", ["Figma 原型已有", "9 项测试通过 · 非真实模型联调"], "orange_soft", "orange"),
        node("reserved", 1310, 325, 450, 78, "响应与追踪", ["requestId / citations", "answerStatus / limitations"], "white", "cyan"),
        node("classify", 100, 500, 290, 115, "任务识别", ["事务 / 机会 / 规划", "年级、专业、年份、用途"], "white", "purple"),
        node("route", 430, 500, 290, 115, "策略选择与路由", ["四类官方依据查询", "v1.0 聚焦可靠问答"], "white", "purple"),
        node("clarify", 760, 500, 290, 115, "主动追问", ["缺关键信息时返回前端", "用户补充后重新提交"], "red_soft", "red"),
        node("agent", 1090, 500, 350, 115, "Agent 编排器", ["组织问题、证据与工具调用", "控制完整回答流程"], "white", "purple"),
        node("composer", 1480, 500, 335, 115, "回答组织", ["解释 / 引用 / 下一步建议", "冲突与不确定性提示"], "white", "purple"),
        node("hybrid", 95, 720, 290, 115, "混合检索", ["本地资料优先 · Top-K", "关键词与语义召回"], "white", "green"),
        node("chroma", 425, 720, 280, 115, "Chroma 向量索引", ["Embedding 语义召回", "返回候选分块"], "white", "green"),
        node("bm25", 745, 720, 260, 115, "BM25 索引", ["规则名称 / 文号 / 年度", "返回关键词候选"], "white", "green"),
        node("rrf", 1045, 720, 270, 115, "RRF 融合排序", ["融合两路候选", "去重并保留召回依据"], "white", "green"),
        node("verify", 1355, 720, 460, 115, "证据核验", ["来源 / 日期 / 适用范围 / 时效", "无依据或冲突时拒绝确定结论"], "white", "green"),
        node("local", 95, 935, 370, 115, "本地知识资产", ["原始资料 + 中文整理稿", "CSV 索引 / 状态 / 页码定位"], "white", "orange"),
        node("embedding", 505, 935, 280, 115, "Embedding 组件", ["文本分块向量化", "索引可重建"], "white", "orange"),
        node("qwen", 825, 935, 280, 115, "Qwen API", ["接收问题 + 证据", "返回回答草稿"], "white", "orange"),
        node("tavilyTool", 1145, 935, 285, 115, "Tavily（可选）", ["接收查询请求", "返回核验结果"], "white", "orange"),
        node("eval", 1470, 935, 345, 115, "离线 PoC 与评测", ["来源追溯 / 事实正确性", "任务适应 / 无依据处理"], "white", "orange"),
        node("ops1", 95, 1142, 500, 30, "离线测试 · 失败降级 · 调用日志 · 资料更新记录", [], "white", "line", title_size=18),
        node("ops2", 625, 1142, 530, 30, "不采集成绩、密码、统一认证凭据或无关个人数据", [], "white", "line", title_size=18),
        node("ops3", 1185, 1142, 630, 30, "数据库仅作为后续设计议题，需与数据库负责人确认首版范围", [], "white", "line", title_size=18),
    ]
    flows = [
        message("a01", "user", "web", [(275, 237), (275, 325)], "blue", "1 提问", (325, 282)),
        message("a02", "maintainer", "local", [(655, 237), (335, 935)], "orange", "资料维护", (495, 750)),
        message("a03", "sources", "local", [(1065, 237), (280, 935)], "blue", "官方原文", (650, 890)),
        message("a04", "web", "api", [(440, 364), (490, 364)], "cyan", "2 请求", (465, 346)),
        message("a05", "api", "classify", [(655, 403), (655, 500)], "purple", "3 分类", (705, 455)),
        message("a06", "classify", "route", [(390, 557), (430, 557)], "purple", "4", (410, 539)),
        message("a07", "route", "clarify", [(720, 557), (760, 557)], "red", "4a 缺信息", (740, 539), dashed=True),
        message("a08", "clarify", "web", [(805, 500), (805, 445), (275, 445), (275, 403)], "red", "4b 返回追问", (520, 428), dashed=True),
        message("a09", "user", "web", [(185, 237), (185, 325)], "blue", "4c 补充后重提", (135, 282), dashed=True),
        message("a10", "web", "api", [(430, 385), (490, 385)], "cyan", "4d 重新提交", (460, 368)),
        message("a11", "route", "agent", [(720, 557), (1090, 557)], "purple", "5 路由", (905, 539)),
        message("a12", "agent", "hybrid", [(1120, 615), (240, 720)], "green", "6 检索计划", (730, 676)),
        message("a13", "hybrid", "chroma", [(385, 777), (425, 777)], "green", "6.1a", (405, 759)),
        message("a14", "hybrid", "bm25", [(240, 720), (240, 690), (875, 690), (875, 720)], "green", "6.1b", (555, 673)),
        message("a15", "chroma", "rrf", [(705, 777), (1045, 777)], "green", "6.2a 候选", (875, 759)),
        message("a16", "bm25", "rrf", [(1005, 777), (1045, 777)], "green", "6.2b 候选", (1025, 759)),
        message("a17", "rrf", "verify", [(1315, 777), (1355, 777)], "green", "7 融合结果", (1335, 759)),
        message("a18", "verify", "tavilyTool", [(1470, 835), (1288, 935)], "orange", "8a 查询请求", (1390, 888), dashed=True),
        message("a19", "tavilyTool", "verify", [(1310, 935), (1480, 835)], "orange", "8b 返回结果", (1425, 920), dashed=True),
        message("a20", "agent", "qwen", [(1180, 615), (965, 935)], "purple", "9 问题 + 证据", (1080, 780)),
        message("a21", "qwen", "verify", [(1105, 980), (1400, 835)], "purple", "9.1 回答草稿", (1260, 895)),
        message("a22", "verify", "composer", [(1650, 720), (1650, 615)], "green", "10 核验后结果", (1720, 668)),
        message("a23", "composer", "api", [(1550, 615), (820, 388)], "cyan", "11 响应", (1200, 470)),
        message("a24", "api", "web", [(490, 364), (440, 364)], "cyan", "12 返回", (465, 455)),
        message("a25", "web", "user", [(275, 325), (275, 237)], "blue", "13 展示回答", (225, 282)),
        message("a26", "local", "embedding", [(465, 992), (505, 992)], "orange", "建立向量索引", (485, 975)),
        message("a27", "embedding", "chroma", [(645, 935), (565, 835)], "orange", "写向量", (610, 885)),
        message("a28", "local", "bm25", [(465, 1005), (875, 835)], "orange", "建立关键词索引", (660, 930)),
    ]
    return {
        "kind": "architecture",
        "title": "CodeMind-FZU 系统技术架构图",
        "drawio_name": "系统技术架构图_赵紫龙_v1.drawio",
        "width": 1920, "height": 1220, "bg": "bg",
        "bands": [
            {"x": 50, "y": 125, "w": 1820, "h": 140, "label": "01  用户、入口与资料来源", "fill": "blue_soft"},
            {"x": 50, "y": 295, "w": 1820, "h": 135, "label": "02  v1.0 Web 入口与 FastAPI 服务", "fill": "cyan_soft"},
            {"x": 50, "y": 460, "w": 1820, "h": 190, "label": "03  Agent 任务理解、策略选择与编排", "fill": "purple_soft"},
            {"x": 50, "y": 680, "w": 1820, "h": 190, "label": "04  本地知识、混合检索与证据核验", "fill": "green_soft"},
            {"x": 50, "y": 900, "w": 1820, "h": 190, "label": "05  外部模型、可选联网工具与验证资产", "fill": "orange_soft"},
            {"x": 50, "y": 1120, "w": 1820, "h": 60, "label": "06  可信性、离线评测与运行日志", "fill": "gray_soft"},
        ],
        "nodes": nodes,
        "messages": flows,
        "labels": [
            {"xy": (960, 34), "text": "CodeMind-FZU 系统技术架构图", "size": 34, "bold": True},
            {"xy": (960, 75), "text": "基于 2026-10-24 开题答辩方案 · 本地知识优先 · 可追溯回答", "size": 20, "fill": "muted"},
            {"xy": (960, 1203), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  Draw.io / SVG / PNG 由同一场景模型生成", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (1440, 32), "w": 380, "h": 98, "title": "版本边界", "lines": [
                "v1.0：四类官方资料查询与引用",
                "候选：Tavily 联网核验，非硬依赖",
                "数据库是否部署：待数据库负责人确认",
            ]},
        ],
    }


def comm_qa_scene() -> dict:
    nodes = [
        node("browser", 70, 240, 230, 90, ":学生浏览器", ["Browser"], "blue_soft", "blue"),
        node("frontend", 350, 205, 240, 95, ":Web 用户入口", ["Frontend"], "cyan_soft", "cyan"),
        node("api", 590, 520, 250, 95, ":FastAPI 后端", ["AskController"], "cyan_soft", "cyan"),
        node("router", 900, 180, 250, 95, ":任务识别", ["TaskRouter"], "purple_soft", "purple"),
        node("clarify", 1240, 210, 245, 90, ":主动追问", ["Clarifier"], "red_soft", "red"),
        node("agent", 900, 470, 270, 105, ":Agent 编排器", ["AgentOrchestrator"], "purple_soft", "purple"),
        node("retriever", 600, 735, 270, 100, ":混合检索器", ["HybridRetriever"], "green_soft", "green"),
        node("chroma", 280, 770, 230, 90, ":Chroma 向量索引", ["ChromaIndex"], "orange_soft", "orange"),
        node("bm25", 280, 970, 230, 90, ":BM25 索引", ["BM25Index"], "orange_soft", "orange"),
        node("rrf", 600, 980, 270, 90, ":RRF 融合", ["RRFRanker"], "green_soft", "green"),
        node("verify", 950, 815, 270, 100, ":证据核验", ["EvidenceVerifier"], "green_soft", "green"),
        node("tavily", 1300, 700, 250, 90, ":Tavily（可选）", ["OnlineCheck"], "orange_soft", "orange"),
        node("qwen", 1300, 980, 250, 95, ":Qwen API", ["LLMAdapter"], "purple_soft", "purple"),
        node("composer", 1470, 390, 260, 100, ":回答组织", ["AnswerComposer"], "cyan_soft", "cyan"),
    ]
    flows = [
        message("q01", "browser", "frontend", [(300, 285), (350, 255)], "blue", "1 提交", (325, 252)),
        message("q02", "frontend", "api", [(465, 300), (660, 520)], "cyan", "2 / 5.1 提交", (540, 410)),
        message("q03", "api", "router", [(715, 520), (900, 275)], "cyan", "3 校验分类", (805, 395)),
        message("q04", "router", "clarify", [(1150, 230), (1240, 250)], "red", "4a 缺信息", (1195, 228), dashed=True),
        message("q05", "clarify", "api", [(1240, 245), (1120, 245), (1120, 560), (840, 560)], "red", "4b 追问请求", (980, 492), dashed=True),
        message("q06", "api", "frontend", [(590, 555), (540, 555), (540, 325), (475, 300)], "red", "4c 返回追问", (540, 380), dashed=True),
        message("q07", "frontend", "browser", [(390, 205), (390, 170), (250, 170), (250, 240)], "red", "4d 展示追问", (320, 163), dashed=True),
        message("q08", "browser", "frontend", [(300, 315), (370, 330)], "blue", "5 补充重提", (330, 340)),
        message("q09", "router", "agent", [(1025, 275), (1025, 470)], "purple", "6 路由", (1075, 380)),
        message("q10", "agent", "retriever", [(950, 575), (735, 735)], "green", "7 检索", (830, 655)),
        message("q11", "retriever", "chroma", [(600, 795), (510, 815)], "orange", "7.1a 语义", (555, 770)),
        message("q12", "retriever", "bm25", [(600, 825), (510, 1010)], "orange", "7.1b 关键词", (550, 925)),
        message("q13", "chroma", "rrf", [(510, 815), (600, 1010)], "green", "7.2a 候选", (555, 940)),
        message("q14", "bm25", "rrf", [(510, 1015), (600, 1015)], "green", "7.2b 候选", (555, 1000)),
        message("q15", "rrf", "verify", [(870, 1015), (1040, 915)], "green", "8 融合证据", (955, 960)),
        message("q16", "verify", "tavily", [(1220, 855), (1300, 770)], "orange", "8.1 查询请求", (1260, 780), dashed=True),
        message("q17", "tavily", "verify", [(1300, 765), (1220, 835)], "orange", "8.2 返回结果", (1265, 830), dashed=True),
        message("q18", "agent", "qwen", [(1140, 575), (1350, 980)], "purple", "9 问题 + 证据", (1245, 800)),
        message("q19", "qwen", "verify", [(1300, 995), (1220, 915)], "purple", "9.1 返回草稿", (1245, 1000)),
        message("q20", "verify", "composer", [(1100, 815), (1470, 490)], "green", "10 可信结果", (1270, 665)),
        message("q21", "composer", "api", [(1470, 470), (840, 540)], "cyan", "11 最终响应", (1135, 525)),
        message("q22", "api", "frontend", [(590, 540), (590, 300)], "cyan", "12 返回前端", (540, 425)),
        message("q23", "frontend", "browser", [(350, 285), (300, 315)], "blue", "13 展示结果", (280, 375), dashed=True),
    ]
    return {
        "kind": "communication",
        "title": "UML 通信图 · 官方资料问答",
        "drawio_name": "UML通信图_智能问答_赵紫龙_v1.drawio",
        "width": 1860, "height": 1240, "bg": "bg",
        "nodes": nodes, "messages": flows,
        "labels": [
            {"xy": (930, 35), "text": "UML 通信图 · 官方资料问答", "size": 34, "bold": True},
            {"xy": (930, 76), "text": "标准路径：任务识别 → 混合检索 → 证据核验 → Qwen 草稿 → 证据复核 → 返回", "size": 20, "fill": "muted"},
            {"xy": (930, 1198), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  消息编号与通信设计说明逐项一致", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (70, 70), "w": 600, "h": 120, "title": "关键约束", "lines": [
                "4a—4d：追问返回浏览器；5/5.1：用户补充后重新提交",
                "8.1/8.2：Tavily 请求与结果双向；9.1：Qwen 返回草稿",
                "12/13：AskController 经 Frontend 返回浏览器",
            ]},
        ],
    }


def comm_ingestion_scene() -> dict:
    nodes = [
        node("maintainer", 70, 230, 235, 90, ":知识库维护者", ["Maintainer"], "blue_soft", "blue"),
        node("entry", 350, 200, 265, 95, ":维护脚本 / 管理端", ["IngestionEntry"], "cyan_soft", "cyan"),
        node("metadata", 350, 560, 265, 95, ":元数据与哈希检查", ["MetadataGate"], "cyan_soft", "cyan"),
        node("parser", 690, 185, 270, 95, ":解析与 OCR", ["ParserOCR"], "purple_soft", "purple"),
        node("local", 690, 440, 270, 105, ":本地知识资产", ["LocalKnowledge"], "orange_soft", "orange"),
        node("chunks", 690, 700, 270, 95, ":分块与定位", ["ChunkBuilder"], "green_soft", "green"),
        node("csv", 1060, 185, 250, 90, ":CSV 元数据索引", ["IndexCSV"], "orange_soft", "orange"),
        node("chroma", 1060, 415, 250, 95, ":Chroma 向量库", ["ChromaBuilder"], "purple_soft", "purple"),
        node("bm25", 1060, 660, 250, 95, ":BM25 索引", ["BM25Builder"], "orange_soft", "orange"),
        node("quality", 1040, 890, 290, 115, ":质量与发布闸门", ["QualityGate", "Chroma PASS && BM25 PASS"], "green_soft", "green"),
        node("tests", 1400, 650, 270, 95, ":离线评测", ["PoCTestSuite"], "green_soft", "green"),
        node("report", 1400, 890, 270, 95, ":更新报告", ["MaintenanceReport"], "cyan_soft", "cyan"),
    ]
    flows = [
        message("i01", "maintainer", "entry", [(305, 275), (350, 250)], "blue", "1 登记资料", (330, 238)),
        message("i02", "entry", "metadata", [(482, 295), (482, 560)], "cyan", "2 检查", (530, 425)),
        message("i03", "metadata", "parser", [(615, 575), (690, 235)], "cyan", "3 解析", (660, 385)),
        message("i04", "parser", "local", [(825, 280), (825, 440)], "purple", "4 保存", (875, 360)),
        message("i05", "local", "csv", [(960, 470), (1060, 235)], "orange", "5 更新索引", (1010, 345)),
        message("i06", "local", "chunks", [(825, 545), (825, 700)], "green", "6 分块", (875, 625)),
        message("i07", "chunks", "chroma", [(960, 730), (1060, 465)], "purple", "7a 构建", (1010, 590)),
        message("i08", "chunks", "bm25", [(960, 750), (1060, 705)], "orange", "7b 构建", (1010, 715)),
        message("i09", "chroma", "quality", [(1185, 510), (1185, 890)], "green", "8a 索引状态", (1235, 700)),
        message("i10", "bm25", "quality", [(1185, 755), (1185, 890)], "green", "8b 索引状态", (1235, 830)),
        message("i11", "csv", "quality", [(1185, 275), (1185, 890)], "orange", "8c 元数据状态", (1235, 400)),
        message("i12", "quality", "tests", [(1330, 930), (1400, 730)], "green", "9 两项 PASS 后测试", (1410, 830)),
        message("i13", "tests", "quality", [(1400, 725), (1330, 925)], "green", "9.1 测试结果", (1430, 780), dashed=True),
        message("i14", "quality", "report", [(1330, 945), (1400, 945)], "green", "10 发布许可", (1365, 925)),
        message("i15", "report", "entry", [(1400, 935), (615, 265)], "cyan", "10.1 状态反馈", (1000, 600), dashed=True),
    ]
    return {
        "kind": "communication",
        "title": "UML 通信图 · 知识资料维护与索引更新",
        "drawio_name": "UML通信图_知识入库_赵紫龙_v1.drawio",
        "width": 1860, "height": 1180, "bg": "bg",
        "nodes": nodes, "messages": flows,
        "labels": [
            {"xy": (930, 35), "text": "UML 通信图 · 知识资料维护与索引更新", "size": 34, "bold": True},
            {"xy": (930, 76), "text": "本地资料 → CSV/Chroma/BM25 → 双索引质量闸门 → 测试 → 发布与状态反馈", "size": 20, "fill": "muted"},
            {"xy": (930, 1105), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  项目知识库基准 44 条；当前仓库 CSV 31 条，仅表示现有索引记录", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (70, 70), "w": 620, "h": 115, "title": "质量闸门", "lines": [
                "只有 Chroma 与 BM25 均 PASS，QualityGate 才允许测试",
                "CSV 只表示元数据状态，不替代两个索引的构建结果",
                "任意索引失败：不进入发布，保留上一可用版本",
            ]},
        ],
    }


def main() -> None:
    specs = [
        (architecture_scene(), ARCH_DIR / "系统技术架构图_赵紫龙_v1.svg",
         ARCH_DIR / "系统技术架构图_赵紫龙_v1.png"),
        (comm_qa_scene(), COMM_DIR / "UML通信图_智能问答_赵紫龙_v1.svg",
         COMM_DIR / "UML通信图_智能问答_赵紫龙_v1.png"),
        (comm_ingestion_scene(), COMM_DIR / "UML通信图_知识入库_赵紫龙_v1.svg",
         COMM_DIR / "UML通信图_知识入库_赵紫龙_v1.png"),
    ]
    for scene, svg_path, png_path in specs:
        draw_scene(scene, svg_path, png_path)


if __name__ == "__main__":
    main()
