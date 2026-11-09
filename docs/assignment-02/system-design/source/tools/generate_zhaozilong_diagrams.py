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


def shift_content(scene: dict, dy: int) -> None:
    """Shift swimlanes, nodes, and routed messages without moving the header."""
    scene["height"] += dy
    for band in scene.get("bands", []):
        band["y"] += dy
    for item in scene["nodes"]:
        item["y"] += dy
    for line in scene["messages"]:
        line["points"] = [(x, y + dy) for x, y in line["points"]]
        line["label_xy"] = (line["label_xy"][0], line["label_xy"][1] + dy)


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
        text(draw, (band["x"] + 22, band["y"] + 23), band["label"], band.get("size", 20),
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
            f'<text x="{band["x"] + 22}" y="{band["y"] + 31}" font-size="{band.get("size",20)}" '
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
            f'fontSize={band.get("size",20)};fontStyle=1;align=left;spacingLeft=18;" vertex="1" parent="1">'
            f'<mxGeometry x="{band["x"]}" y="{band["y"]}" width="{band["w"]}" '
            f'height="{band["h"]}" as="geometry"/></mxCell>'
        )
    for item in scene["nodes"]:
        if scene.get("rich_text"):
            lines = item["lines"]
            compact = bool(lines) and item["h"] < 100
            title_size = min(item.get("title_size", 22), 19) if compact else item.get("title_size", 22)
            line_size = min(item.get("line_size", 16), 14) if compact else item.get("line_size", 16)
            value = (
                f"<span style='font-size:{title_size}px;font-weight:700'>"
                f"{escape(item['title'])}</span>"
            )
            if lines:
                value += "<br>" + "<br>".join(
                    f"<span style='font-size:{line_size}px'>{escape(line)}</span>"
                    for line in lines
                )
            value = value.replace("<", "&lt;").replace(">", "&gt;")
        else:
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
        rounding = "rounded=0;curved=0;" if scene.get("rich_text") else "rounded=1;curved=1;"
        waypoints = "".join(
            f'<mxPoint x="{x}" y="{y}"/>' for x, y in line["points"][1:-1]
        )
        waypoint_xml = f'<Array as="points">{waypoints}</Array>' if waypoints else ""
        cells.append(
            f'<mxCell id="{line["id"]}" value="{value}" '
            f'style="edgeStyle=orthogonalEdgeStyle;{rounding}html=1;'
            f'endArrow=block;strokeColor={color(line["stroke"])};strokeWidth={line.get("width",3)};'
            f'{dash}fontFamily=Microsoft YaHei;fontSize=16;" edge="1" parent="1" '
            f'source="{line["source"]}" target="{line["target"]}">'
            f'<mxGeometry relative="1" as="geometry">{waypoint_xml}</mxGeometry></mxCell>'
        )
    for idx, item in enumerate(scene.get("labels", [])):
        label_width = item.get(
            "w",
            max(400, min(1500, int(len(item["text"]) * item.get("size", 18) * 1.2))),
        )
        label_height = item.get("h", max(44, int(item.get("size", 18) * 1.8)))
        cells.append(
            f'<mxCell id="label_{idx}" value="{escape(item["text"], {chr(34): "&quot;"})}" '
            f'style="text;html=1;align=center;verticalAlign=middle;fontColor={color(item.get("fill","ink"))};'
            f'fontSize={item.get("size",18)};fontStyle={1 if item.get("bold") else 0};" '
            f'vertex="1" parent="1"><mxGeometry x="{item["xy"][0] - label_width / 2}" '
            f'y="{item["xy"][1] - label_height / 2}" width="{label_width}" '
            f'height="{label_height}" as="geometry"/></mxCell>'
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
        f'<mxfile host="app.diagrams.net" modified="{scene.get("modified", "2026-11-08T09:00:00.000Z")}" '
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


def _legacy_architecture_scene() -> dict:
    nodes = [
        node("user", 110, 165, 330, 72, "学生用户", ["统一提问 · 查看引用 · 补充信息"], "white", "blue"),
        node("maintainer", 490, 165, 330, 72, "知识库维护者", ["登记资料 · 核验元数据 · 重建索引"], "white", "blue"),
        node("sources", 870, 165, 390, 72, "学校 / 学院官方网站", ["通知 · 办法 · 附件 · 培养方案"], "white", "blue"),
        node("tavily", 1310, 165, 450, 72, "Tavily 联网工具（候选）", ["按需核验官方公开信息 · 非首版硬依赖"], "white", "blue"),
        node("web", 110, 325, 330, 78, "Web 用户入口", ["HTML / CSS / JavaScript", "提问、追问与引用展示"], "white", "cyan"),
        node("api", 490, 325, 330, 78, "FastAPI 后端", ["POST /api/ask", "校验 / 异常映射 / 统一响应"], "white", "cyan"),
        node("poc", 870, 325, 390, 78, "现有原型与离线 PoC", ["Figma 原型已有", "9 项测试通过 · 非真实模型联调"], "orange_soft", "orange"),
        node("reserved", 1310, 325, 450, 78, "响应与追踪", ["requestId / citations", "answerStatus / limitations"], "white", "cyan"),
        node("classify", 100, 500, 290, 115, "任务识别", ["v1.0：事务 / 机会查询", "规划路由=后续预留"], "white", "purple"),
        node("route", 430, 500, 290, 115, "策略选择与路由", ["覆盖五大业务方向", "前四优先 / 第五后续"], "white", "purple"),
        node("clarify", 760, 500, 290, 115, "主动追问", ["缺关键信息时返回前端", "用户补充后重新提交"], "red_soft", "red"),
        node("agent", 1090, 500, 350, 115, "Agent 编排器", ["组织问题、证据与工具调用", "控制完整回答流程"], "white", "purple"),
        node("composer", 1480, 500, 335, 115, "回答组织", ["解释 / 引用 / 下一步建议", "冲突与不确定性提示"], "white", "purple"),
        node("hybrid", 95, 720, 290, 115, "混合检索", ["本地资料优先 · Top-K", "关键词与语义召回"], "white", "green"),
        node("chroma", 425, 720, 280, 115, "Chroma 向量索引", ["Embedding 语义召回", "返回候选分块"], "white", "green"),
        node("bm25", 745, 720, 260, 115, "BM25 索引", ["规则名称 / 文号 / 年度", "返回关键词候选"], "white", "green"),
        node("rrf", 1045, 720, 270, 115, "RRF 融合排序", ["融合两路候选", "去重并保留召回依据"], "white", "green"),
        node("verify", 1330, 720, 250, 115, "生成前证据核验", ["来源 / 日期 / 适用范围 / 时效", "无依据或冲突时拒绝"], "white", "green"),
        node("answerVerifier", 1590, 720, 220, 115, "生成后回答复核", ["回答 / 引用 / 状态一致性", "复核不通过则不返回"], "white", "red"),
        node("local", 95, 935, 370, 115, "本地知识资产", ["原始资料 + 中文整理稿", "CSV 索引 / 状态 / 页码定位"], "white", "orange"),
        node("embedding", 505, 935, 280, 115, "Embedding 组件", ["文本分块向量化", "索引可重建"], "white", "orange"),
        node("qwen", 825, 935, 280, 115, "Qwen API", ["接收问题 + 证据", "返回回答草稿"], "white", "orange"),
        node("tavilyTool", 1145, 935, 285, 115, "Tavily（可选）", ["接收查询请求", "返回核验结果"], "white", "orange"),
        node("eval", 1470, 935, 345, 115, "离线 PoC 与评测", ["来源追溯 / 事实正确性", "任务适应 / 无依据处理"], "white", "orange"),
        node("ops1", 95, 1128, 520, 42, "离线测试 · 失败降级 · 调用日志", [], "white", "line", title_size=17),
        node("ops2", 655, 1128, 520, 42, "不采集成绩、密码或统一认证凭据", [], "white", "line", title_size=17),
        node("ops3", 1215, 1128, 600, 42, "数据库首版范围待数据库负责人确认", [], "white", "line", title_size=17),
    ]
    flows = [
        message("a01", "user", "web", [(250, 237), (250, 325)], "blue", "1 提问", (300, 250)),
        message("a02", "maintainer", "local", [(490, 200), (460, 200), (460, 430), (60, 430), (60, 900), (335, 900)], "orange", "资料维护", (720, 650)),
        message("a03", "sources", "local", [(1065, 237), (1065, 275), (1860, 275), (1860, 880), (280, 880), (280, 935)], "blue", "官方原文", (760, 890)),
        message("a04", "web", "api", [(440, 364), (490, 364)], "cyan", "2 请求", (465, 430)),
        message("a05", "api", "classify", [(655, 403), (655, 500)], "purple", "3 分类", (700, 420)),
        message("a06", "classify", "route", [(390, 557), (430, 557)], "purple", "4", (410, 539)),
        message("a07", "route", "clarify", [(720, 557), (760, 557)], "red", "4a 缺信息", (740, 480), dashed=True),
        message("a08", "clarify", "api", [(805, 500), (805, 465), (655, 465), (655, 403)], "red", "4b 返回 FastAPI", (720, 445), dashed=True),
        message("a09", "api", "web", [(570, 403), (570, 380), (465, 380), (440, 364)], "red", "4c 返回 Frontend", (570, 438), dashed=True),
        message("a10", "web", "user", [(220, 325), (220, 237)], "red", "4d 展示追问", (170, 282), dashed=True),
        message("a11", "user", "web", [(320, 237), (320, 325)], "blue", "5 补充信息", (360, 280)),
        message("a12", "web", "api", [(430, 394), (490, 394)], "cyan", "5.1 重新提交", (445, 465)),
        message("a13", "route", "agent", [(575, 615), (575, 650), (1265, 650), (1265, 615)], "purple", "6 路由", (920, 668)),
        message("a14", "agent", "hybrid", [(1120, 615), (240, 720)], "green", "7 检索计划", (730, 676)),
        message("a15", "hybrid", "chroma", [(385, 777), (425, 777)], "green", "7.1a", (405, 865)),
        message("a16", "hybrid", "bm25", [(240, 835), (240, 860), (875, 860), (875, 835)], "green", "7.1b", (650, 878)),
        message("a17", "chroma", "rrf", [(565, 720), (565, 700), (1180, 700), (1180, 720)], "green", "7.2a 候选", (820, 688)),
        message("a18", "bm25", "rrf", [(1005, 720), (1005, 705), (1045, 705), (1045, 720)], "green", "7.2b 候选", (940, 850)),
        message("a19", "rrf", "verify", [(1315, 777), (1330, 777)], "green", "8 融合结果", (1322, 865)),
        message("a20", "verify", "tavilyTool", [(1470, 835), (1288, 935)], "orange", "8.1 查询请求", (1450, 910), dashed=True),
        message("a21", "tavilyTool", "verify", [(1310, 935), (1480, 835)], "orange", "8.2 返回结果", (1440, 885), dashed=True),
        message("a22", "verify", "agent", [(1390, 720), (1390, 650), (1265, 650), (1265, 615)], "green", "9 核验证据返回", (1370, 670)),
        message("a23", "agent", "qwen", [(1140, 590), (1140, 650), (1030, 650), (1030, 900), (965, 935)], "purple", "10 问题 + 验证证据", (1015, 875)),
        message("a24", "qwen", "answerVerifier", [(965, 1050), (965, 1085), (1835, 1085), (1835, 835), (1810, 835)], "purple", "10.1 回答草稿", (1500, 1095)),
        message("a25", "answerVerifier", "composer", [(1700, 720), (1700, 615)], "red", "11 复核后结果", (1750, 668)),
        message("a26", "composer", "api", [(1550, 500), (1460, 500), (1460, 440), (820, 440), (820, 403)], "cyan", "12 响应", (1200, 440)),
        message("a27", "api", "web", [(490, 346), (440, 346)], "cyan", "13 返回 Frontend", (500, 270)),
        message("a28", "web", "user", [(310, 325), (310, 237)], "blue", "14 展示回答", (400, 310)),
        message("a29", "local", "embedding", [(465, 992), (505, 992)], "orange", "建立向量索引", (485, 1085)),
        message("a30", "embedding", "chroma", [(645, 935), (565, 835)], "orange", "写向量", (560, 890)),
        message("a31", "local", "bm25", [(465, 1005), (465, 1090), (805, 1090), (805, 835), (875, 835)], "orange", "建立关键词索引", (900, 1085)),
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
            {"x": 50, "y": 1105, "w": 1820, "h": 85, "label": "06  可信性、离线评测与运行日志", "fill": "gray_soft"},
        ],
        "nodes": nodes,
        "messages": flows,
        "labels": [
            {"xy": (960, 34), "text": "CodeMind-FZU 系统技术架构图", "size": 34, "bold": True},
            {"xy": (960, 75), "text": "基于 2026-10-24 开题答辩方案 · 本地知识优先 · 可追溯回答", "size": 20, "fill": "muted"},
            {"xy": (960, 1203), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  Draw.io / SVG / PNG 由同一场景模型生成", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (1410, 24), "w": 410, "h": 130, "title": "业务范围", "lines": [
                "1 政策事务 · 2 升学就业",
                "3 竞赛科研 · 4 学院资源",
                "5 成长规划：后续迭代",
                "测试任务数量 ≠ 业务方向数量",
            ]},
        ],
    }


def architecture_scene() -> dict:
    nodes = [
        node("student", 150, 185, 300, 60, "学生用户",
             ["自然语言提问 / 查看引用"], "blue_soft", "blue"),
        node("maintainer", 550, 185, 320, 60, "知识库维护者",
             ["登记资料 / 审核 / 发布"], "blue_soft", "blue"),
        node("sources", 950, 185, 540, 60, "福大官方来源",
             ["学校与学院通知 / 办法 / 附件"], "blue_soft", "blue"),
        node("web", 150, 350, 350, 75, "Web 前端",
             ["学生端 / 后台入口", "统一问答、引用与说明展示"], "cyan_soft", "cyan"),
        node("api", 650, 350, 450, 75, "FastAPI 服务层",
             ["POST /api/ask", "参数校验 / 异常映射 / 统一响应"], "cyan_soft", "cyan"),
        node("task", 100, 505, 320, 85, "任务识别与主动追问",
             ["TaskRouter · Clarifier", "缺字段时经 FastAPI 返回补充"], "purple_soft", "purple"),
        node("agent", 500, 505, 700, 85, "AgentOrchestrator",
             ["统一流程编排 / 策略路由", "受控调用检索、核验与外部模型"], "purple_soft", "purple"),
        node("answer", 1300, 505, 400, 85, "回答复核与组织",
             ["AnswerVerifier → AnswerComposer", "引用 / 政策状态 / 限制校验"], "red_soft", "red"),
        node("hybrid", 100, 780, 450, 100, "HybridRetriever",
             ["Chroma 语义召回 + BM25 关键词召回", "RRF 融合 / 去重 / versionId"],
             "green_soft", "green"),
        node("verify", 750, 780, 400, 100, "EvidenceVerifier",
             ["来源 / 日期 / 适用范围 / 时效", "verifiedEvidence / citationIds / policyStatus"],
             "green_soft", "green"),
        node("local", 100, 1010, 400, 100, "本地知识资产",
             ["原始资料 + CSV 索引 + 元数据", "项目内可审计的事实来源"], "orange_soft", "orange"),
        node("qwen", 900, 1010, 400, 100, "Qwen API（外部服务）",
             ["基于已核验证据生成回答草稿"], "orange_soft", "orange"),
        node("tavily", 1320, 1010, 380, 100, "Tavily（可选外部服务）",
             ["按需核验官方公开信息", "非首版硬依赖"], "orange_soft", "orange"),
        node("version", 100, 1240, 350, 60, "VersionRegistry",
             ["Chroma / BM25 统一 versionId · 原子切换"], "white", "purple", title_size=18),
        node("tests", 500, 1240, 340, 60, "离线 PoC 与固定验收用例",
             [], "white", "green", title_size=17),
        node("ops", 900, 1240, 700, 60, "日志、审计与失败降级：保留上一可用版本",
             [], "white", "line", title_size=17),
    ]
    flows = [
        message("f01", "student", "web", [(400, 245), (400, 350)],
                "blue", "访问", (450, 265)),
        message("f02", "sources", "maintainer", [(950, 215), (870, 215)],
                "blue", "收录", (910, 196)),
        message("f03", "web", "api", [(500, 387), (650, 387)],
                "cyan", "API", (575, 367)),
        message("f04", "api", "agent",
                [(875, 425), (875, 505)],
                "purple", "任务请求", (930, 455)),
        message("f05", "task", "agent", [(420, 547), (500, 547)],
                "purple", "任务 / 缺项", (460, 487)),
        message("f06", "agent", "hybrid",
                [(650, 590), (650, 800), (550, 800)],
                "green", "检索", (700, 680)),
        message("f07", "hybrid", "verify", [(550, 830), (750, 830)],
                "green", "候选", (650, 810)),
        message("f08", "verify", "agent", [(950, 780), (950, 590)],
                "green", "已核验证据", (1000, 685)),
        message("f09", "agent", "qwen", [(1200, 590), (1200, 1010)],
                "purple", "问题 + 证据", (1250, 900)),
        message("f10", "local", "hybrid", [(450, 1010), (450, 880)],
                "orange", "读取", (500, 945)),
        message("f12", "qwen", "answer",
                [(1100, 1110), (1100, 1140), (1730, 1140),
                 (1730, 547), (1700, 547)],
                "purple", "回答草稿", (1740, 900)),
        message("f13", "answer", "api",
                [(1500, 505), (1500, 425), (1100, 425), (1100, 387)],
                "cyan", "最终响应", (1300, 440)),
    ]
    return {
        "kind": "architecture",
        "title": "CodeMind-FZU 系统技术架构图",
        "drawio_name": "系统技术架构图_赵紫龙_v1.drawio",
        "width": 1800, "height": 1400, "bg": "bg",
        "modified": "2026-11-09T13:00:00.000Z",
        "rich_text": True,
        "bands": [
            {"x": 50, "y": 120, "w": 1700, "h": 140,
             "label": "01  用户与官方资料来源", "fill": "blue_soft"},
            {"x": 50, "y": 280, "w": 1700, "h": 140,
             "label": "02  Web 前端与 FastAPI 服务层", "fill": "cyan_soft"},
            {"x": 50, "y": 450, "w": 1700, "h": 220,
             "label": "03  Agent 编排与回答复核", "fill": "purple_soft"},
            {"x": 50, "y": 700, "w": 1700, "h": 220,
             "label": "04  混合检索与生成前证据核验", "fill": "green_soft"},
            {"x": 50, "y": 950, "w": 1700, "h": 220,
             "label": "05  知识资产与外部服务边界", "fill": "orange_soft"},
            {"x": 50, "y": 1180, "w": 1700, "h": 160,
             "label": "06  版本、测试与可靠性支撑", "fill": "gray_soft"},
        ],
        "nodes": nodes,
        "messages": flows,
        "labels": [
            {"xy": (700, 30), "text": "CodeMind-FZU 系统技术架构图",
             "size": 34, "bold": True},
            {"xy": (700, 70),
             "text": "分层依赖视图 · 主链路：Web → FastAPI → Agent → 检索/证据核验 → Qwen → 回答复核",
             "size": 19, "fill": "muted"},
            {"xy": (700, 1370),
             "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-09  |  Draw.io / SVG / PNG 同源导出",
             "size": 15, "fill": "muted"},
        ],
        "legends": [
            {"xy": (1300, 22), "w": 430, "h": 90, "title": "边界说明", "lines": [
                "内部：Web / FastAPI / Agent / 检索 / 数据",
                "外部：Qwen API；Tavily 可选",
                "支撑：版本、测试和日志不混入主链路",
            ]},
        ],
    }


def comm_qa_scene() -> dict:
    nodes = [
        node("browser", 90, 245, 260, 100, "学生浏览器", ["Browser"], "blue_soft", "blue"),
        node("frontend", 410, 225, 300, 110, "Web 用户入口", ["Frontend"], "cyan_soft", "cyan"),
        node("api", 760, 520, 300, 110, "FastAPI 后端", ["AskController"], "cyan_soft", "cyan"),
        node("router", 1130, 210, 280, 110, "任务识别", ["TaskRouter"], "purple_soft", "purple"),
        node("clarify", 1500, 210, 280, 100, "主动追问", ["Clarifier"], "red_soft", "red"),
        node("agent", 1130, 470, 300, 120, "Agent 编排器", ["AgentOrchestrator"], "purple_soft", "purple"),
        node("composer", 1780, 380, 300, 110, "回答组织", ["AnswerComposer"], "cyan_soft", "cyan"),
        node("retriever", 760, 820, 300, 110, "混合检索器", ["HybridRetriever"], "green_soft", "green"),
        node("chroma", 300, 840, 260, 100, "Chroma 向量索引", ["ChromaIndex"], "orange_soft", "orange"),
        node("bm25", 300, 1080, 260, 100, "BM25 索引", ["BM25Index"], "orange_soft", "orange"),
        node("rrf", 760, 1080, 300, 100, "RRF 融合", ["RRFRanker"], "green_soft", "green"),
        node("verify", 1180, 835, 300, 110, "生成前证据核验", ["EvidenceVerifier"], "green_soft", "green"),
        node("tavily", 1600, 1000, 260, 100, "Tavily（可选）", ["OnlineCheck"], "orange_soft", "orange"),
        node("qwen", 1600, 760, 260, 100, "Qwen API", ["LLMAdapter"], "purple_soft", "purple"),
        node("answerVerifier", 1180, 1080, 300, 110, "生成后回答复核", ["AnswerVerifier"], "red_soft", "red"),
    ]
    flows = [
        message("q01", "browser", "frontend", [(350, 295), (410, 270)], "blue", "1 提交", (380, 250)),
        message("q02", "frontend", "api", [(655, 335), (820, 520)], "cyan", "2 / 5.1 提交", (770, 410)),
        message("q03", "api", "router", [(1060, 550), (1130, 290)], "cyan", "3 校验分类", (1090, 410)),
        message("q04", "router", "clarify", [(1410, 250), (1500, 250)], "red", "4a 缺信息", (1455, 228), dashed=True),
        message("q05", "clarify", "api", [(1500, 240), (1430, 240), (1430, 640), (1060, 640)], "red", "4b 追问请求", (1260, 625), dashed=True),
        message("q06", "api", "frontend", [(760, 550), (700, 550), (700, 330), (710, 300)], "red", "4c 返回追问", (650, 460), dashed=True),
        message("q07", "frontend", "browser", [(410, 245), (360, 200), (230, 200), (230, 245)], "red", "4d 展示追问", (310, 183), dashed=True),
        message("q08", "browser", "frontend", [(350, 330), (420, 350)], "blue", "5 补充重提", (385, 375)),
        message("q09", "router", "agent", [(1270, 320), (1270, 470)], "purple", "6 路由", (1320, 395)),
        message("q10", "agent", "retriever", [(1180, 590), (950, 820)], "green", "7 检索", (1065, 730)),
        message("q11", "retriever", "chroma", [(760, 870), (560, 890)], "orange", "7.1a 语义", (660, 850)),
        message("q12", "retriever", "bm25", [(760, 900), (560, 1110)], "orange", "7.1b 关键词", (650, 1010)),
        message("q13", "chroma", "rrf", [(560, 890), (760, 1100)], "green", "7.2a 候选", (660, 1055)),
        message("q14", "bm25", "rrf", [(560, 1130), (760, 1130)], "green", "7.2b 候选", (660, 1110)),
        message("q15", "rrf", "verify", [(1060, 1110), (1260, 945)], "green", "8 融合证据", (1160, 1020)),
        message("q16", "verify", "tavily", [(1480, 890), (1600, 1040)], "orange", "8.1 查询请求", (1540, 940), dashed=True),
        message("q17", "tavily", "verify", [(1600, 1020), (1480, 915)], "orange", "8.2 返回结果", (1540, 1090), dashed=True),
        message("q18", "verify", "agent", [(1190, 835), (1190, 650), (1265, 650), (1265, 590)], "green", "9 核验证据返回", (1110, 650)),
        message("q19", "agent", "qwen", [(1430, 570), (1670, 760)], "purple", "10 问题 + 验证证据", (1450, 620)),
        message("q20", "qwen", "answerVerifier", [(1600, 800), (1520, 800), (1520, 1135), (1480, 1135)], "purple", "10.1 回答草稿", (1550, 980)),
        message("q21", "answerVerifier", "composer", [(1480, 1135), (1550, 1135), (1550, 620), (1780, 620), (1780, 490)], "red", "11 复核后结果", (1620, 660)),
        message("q22", "composer", "api", [(1780, 405), (1720, 405), (1720, 640), (1060, 640)], "cyan", "12 最终响应", (1540, 590)),
        message("q23", "api", "frontend", [(760, 535), (690, 535), (690, 335)], "cyan", "13 返回前端", (610, 360)),
        message("q24", "frontend", "browser", [(410, 290), (350, 315)], "blue", "14 展示结果", (320, 415), dashed=True),
    ]
    scene = {
        "kind": "communication",
        "title": "UML 通信图 · 官方资料问答",
        "drawio_name": "UML通信图_智能问答_赵紫龙_v1.drawio",
        "width": 2300, "height": 1420, "bg": "bg",
        "bands": [
            {"x": 50, "y": 150, "w": 2200, "h": 510, "label": "交互、请求分类与 Agent 编排", "fill": "blue_soft"},
            {"x": 50, "y": 700, "w": 2200, "h": 640, "label": "混合检索、可选联网、证据核验与回答", "fill": "green_soft"},
            {"x": 50, "y": 1365, "w": 2200, "h": 35, "label": "消息 4a—4d 保证追问闭环；8.1/8.2 保证 Tavily 双向；13/14 保证最终响应返回浏览器", "fill": "white", "text": "muted", "size": 16},
        ],
        "nodes": nodes, "messages": flows,
        "labels": [
            {"xy": (1150, 35), "text": "UML 通信图 · 官方资料问答", "size": 34, "bold": True},
            {"xy": (1150, 76), "text": "标准路径：任务识别 → 混合检索 → 证据核验 → Qwen 草稿 → 证据复核 → 返回", "size": 20, "fill": "muted"},
            {"xy": (1150, 1345), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  消息编号与通信设计说明逐项一致", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (70, 85), "w": 650, "h": 100, "title": "关键约束", "lines": [
                "4a—4d：追问返回浏览器；5/5.1：用户补充后重新提交",
                "8.1/8.2：Tavily 双向；9：证据返回 Agent",
                "10.1：Qwen 草稿进入回答复核；13/14：返回浏览器",
            ]},
        ],
    }
    shift_content(scene, 70)
    scene["labels"][2]["xy"] = (1150, 1415)
    return scene


def comm_ingestion_scene() -> dict:
    nodes = [
        node("maintainer", 70, 240, 250, 95, "知识库维护者", ["Maintainer"], "blue_soft", "blue"),
        node("entry", 360, 210, 280, 100, "维护脚本 / 管理端", ["IngestionEntry"], "cyan_soft", "cyan"),
        node("metadata", 360, 600, 280, 100, "元数据与哈希检查", ["MetadataGate"], "cyan_soft", "cyan"),
        node("parser", 720, 190, 280, 100, "解析与 OCR", ["ParserOCR"], "purple_soft", "purple"),
        node("local", 720, 450, 280, 110, "本地知识资产", ["LocalKnowledge"], "orange_soft", "orange"),
        node("chunks", 720, 720, 280, 100, "分块与定位", ["ChunkBuilder"], "green_soft", "green"),
        node("csv", 1100, 185, 260, 95, "CSV 元数据索引", ["IndexCSV"], "orange_soft", "orange"),
        node("chroma", 1100, 420, 260, 100, "Chroma 向量库", ["ChromaBuilder"], "purple_soft", "purple"),
        node("bm25", 1100, 665, 260, 100, "BM25 索引", ["BM25Builder"], "orange_soft", "orange"),
        node("quality", 1080, 930, 300, 120, "质量与发布闸门", ["QualityGate", "双索引 PASS + 人工审核"], "green_soft", "green"),
        node("tests", 1450, 650, 270, 100, "离线评测", ["PoCTestSuite"], "green_soft", "green"),
        node("publisher", 1450, 930, 270, 100, "索引发布器", ["IndexPublisher"], "purple_soft", "purple"),
        node("versionRegistry", 1450, 1080, 270, 80, "活动版本注册表", ["VersionRegistry", "统一 versionId"], "purple_soft", "purple"),
        node("agentGateway", 1740, 930, 270, 100, "Agent 查询入口", ["AgentQueryGateway", "只读已完整发布版本"], "green_soft", "green"),
        node("agent", 1740, 650, 270, 100, "Agent", ["Orchestrator"], "blue_soft", "blue"),
        node("report", 1740, 1130, 270, 85, "更新报告", ["MaintenanceReport"], "cyan_soft", "cyan"),
    ]
    flows = [
        message("i01", "maintainer", "entry", [(320, 287), (360, 260)], "blue", "1 登记资料", (340, 360)),
        message("i02", "entry", "metadata", [(500, 310), (500, 600)], "cyan", "2 元数据/来源检查", (555, 455)),
        message("i03", "metadata", "parser", [(640, 610), (720, 240)], "cyan", "3 解析", (685, 420)),
        message("i04", "parser", "local", [(860, 290), (860, 450)], "purple", "4 保存", (910, 370)),
        message("i05", "local", "csv", [(1000, 485), (1100, 235)], "orange", "5 更新 CSV", (1050, 360)),
        message("i06", "local", "chunks", [(860, 560), (860, 720)], "green", "6 分块", (910, 640)),
        message("i07", "chunks", "chroma", [(1000, 750), (1100, 470)], "purple", "7a 构建", (1050, 610)),
        message("i08", "chunks", "bm25", [(1000, 770), (1100, 715)], "orange", "7b 构建", (1050, 730)),
        message("i09", "chroma", "quality", [(1360, 470), (1380, 470), (1380, 800), (1230, 800), (1230, 930)], "green", "8a 索引状态", (1300, 780)),
        message("i10", "bm25", "quality", [(1230, 765), (1230, 930)], "green", "8b 索引状态", (1150, 790)),
        message("i11", "csv", "quality", [(1100, 235), (1040, 235), (1040, 970), (1080, 970)], "orange", "8c 元数据状态", (1035, 410)),
        message("i12", "quality", "tests", [(1380, 960), (1450, 750)], "green", "9 两项 PASS 后测试", (1380, 830)),
        message("i13", "tests", "quality", [(1450, 725), (1380, 950)], "green", "9.1 测试结果", (1540, 780), dashed=True),
        message("i14", "quality", "publisher", [(1380, 990), (1450, 990)], "green", "10 审核+测试通过", (1370, 900)),
        message("i15", "publisher", "versionRegistry", [(1585, 1030), (1585, 1080)], "purple", "10.1 写入完整 vN", (1530, 1055)),
        message("i16", "versionRegistry", "chroma", [(1450, 1090), (1420, 1090), (1420, 450), (1360, 470)], "purple", "10.2 Chroma=vN", (1200, 880), dashed=True),
        message("i17", "versionRegistry", "bm25", [(1450, 1110), (1430, 1110), (1430, 750), (1360, 715)], "orange", "10.3 BM25=vN", (1540, 860), dashed=True),
        message("i18", "versionRegistry", "agentGateway", [(1720, 1120), (1730, 1120), (1730, 980), (1740, 980)], "purple", "10.4 切换 activity=vN", (1770, 1050)),
        message("i19", "agentGateway", "agent", [(1875, 930), (1875, 750)], "green", "10.5 Agent 只读 vN", (1925, 840)),
        message("i20", "versionRegistry", "report", [(1720, 1120), (1730, 1120), (1730, 1145), (1740, 1145)], "cyan", "10.6 发布结果", (1600, 1185)),
        message("i21", "report", "entry", [(1875, 1215), (2050, 1215), (2050, 310), (640, 310)], "cyan", "10.7 状态反馈", (2010, 500), dashed=True),
    ]
    scene = {
        "kind": "communication",
        "title": "UML 通信图 · 知识资料维护与索引更新",
        "drawio_name": "UML通信图_知识入库_赵紫龙_v1.drawio",
        "width": 2100, "height": 1250, "bg": "bg",
        "bands": [
            {"x": 50, "y": 155, "w": 2000, "h": 550, "label": "资料登记、人工核验、正文提取与本地资产更新", "fill": "blue_soft"},
            {"x": 50, "y": 735, "w": 2000, "h": 490, "label": "双索引构建、质量闸门、发布与 Agent 可用性", "fill": "green_soft"},
        ],
        "nodes": nodes, "messages": flows,
        "labels": [
            {"xy": (1050, 35), "text": "UML 通信图 · 知识资料维护与索引更新", "size": 34, "bold": True},
            {"xy": (1050, 76), "text": "资料审核 → CSV/Chroma/BM25 → 双索引闸门 → 测试 → IndexPublisher → Agent", "size": 20, "fill": "muted"},
            {"xy": (1050, 1215), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  项目基准 44 条；当前仓库 CSV 31 条仅表示现有索引记录", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (70, 85), "w": 680, "h": 110, "title": "发布规则", "lines": [
                "人工审核 + Chroma PASS + BM25 PASS + 测试通过",
                "两个索引统一使用 versionId=vN",
                "IndexPublisher 原子切换活动版本指针",
                "任一步失败：不发布，继续保留上一可用版本",
            ]},
        ],
    }
    shift_content(scene, 70)
    scene["labels"][2]["xy"] = (1050, 1285)
    return scene


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
