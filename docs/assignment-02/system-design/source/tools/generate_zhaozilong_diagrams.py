#!/usr/bin/env python3
"""Generate architecture and UML communication diagrams aligned with the opening deck."""

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


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def color(value: str) -> str:
    return P.get(value, value)


def box(x: int, y: int, w: int, h: int, title: str,
        lines: list[str] | None = None, fill: str = "white",
        stroke: str = "line", **kwargs) -> dict:
    return {
        "x": x, "y": y, "w": w, "h": h, "title": title,
        "lines": lines or [], "fill": fill, "stroke": stroke, **kwargs,
    }


def edge(points: list[tuple[int, int]], stroke: str = "line",
         label: str | None = None, label_xy: tuple[int, int] | None = None,
         *, dashed: bool = False, arrow: bool = True, width: int = 3,
         messages: list[tuple[int, int]] | None = None) -> dict:
    return {
        "points": points, "stroke": stroke, "label": label,
        "label_xy": label_xy or points[len(points) // 2],
        "dashed": dashed, "arrow": arrow, "width": width,
        "messages": messages or [],
    }


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
         fill: str, bold: bool = False, anchor: str = "mm") -> None:
    draw.text(xy, value, font=font(size, bold), fill=color(fill), anchor=anchor)


def head(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: str,
         width: int) -> None:
    start, end = points[-2], points[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 15
    left = (
        end[0] - length * math.cos(angle - math.pi / 7),
        end[1] - length * math.sin(angle - math.pi / 7),
    )
    right = (
        end[0] - length * math.cos(angle + math.pi / 7),
        end[1] - length * math.sin(angle + math.pi / 7),
    )
    draw.polygon([end, left, right], fill=color(fill))


def render(scene: dict, svg_path: Path, png_path: Path) -> None:
    width, height = scene["width"], scene["height"]
    image = Image.new("RGB", (width, height), color(scene.get("bg", "bg")))
    draw = ImageDraw.Draw(image)

    for band in scene.get("bands", []):
        x, y, w, h = band["x"], band["y"], band["w"], band["h"]
        draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=band.get("radius", 22),
            fill=color(band.get("fill", "white")),
            outline=color(band.get("stroke", "gray_soft")), width=2,
        )
        text(draw, (x + 22, y + 23), band["label"], band.get("size", 20),
             band.get("text", "blue"), bold=True, anchor="lm")

    for line in scene.get("edges", []):
        pts = line["points"]
        stroke = color(line.get("stroke", "line"))
        if line.get("dashed"):
            for start, end in zip(pts, pts[1:]):
                length = math.dist(start, end)
                steps = max(1, int(length // 12))
                for i in range(0, steps, 2):
                    a = i / steps
                    b = min((i + 1) / steps, 1)
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
        if line.get("arrow", True):
            head(draw, pts, stroke, line.get("width", 3))
        for point in line.get("messages", []):
            draw.ellipse(
                (point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6),
                fill=color(scene.get("bg", "bg")), outline=stroke, width=2,
            )
        label = line.get("label")
        if label:
            lx, ly = line["label_xy"]
            bbox = draw.textbbox((lx, ly), label, font=font(16, True), anchor="mm")
            draw.rounded_rectangle(
                (bbox[0] - 6, bbox[1] - 3, bbox[2] + 6, bbox[3] + 3),
                radius=5, fill=color(scene.get("bg", "bg")),
            )
            text(draw, (lx, ly), label, 16, stroke, bold=True)

    for item in scene["boxes"]:
        x, y, w, h = item["x"], item["y"], item["w"], item["h"]
        draw.rounded_rectangle(
            (x, y, x + w, y + h), radius=item.get("radius", 16),
            fill=color(item.get("fill", "white")),
            outline=color(item.get("stroke", "line")),
            width=item.get("width", 2),
        )
        title_size = item.get("title_size", 23)
        line_size = item.get("line_size", 17)
        center = x + w // 2
        lines = item.get("lines", [])
        if lines:
            compact = h < 100
            if compact:
                title_size = min(title_size, 19)
                line_size = min(line_size, 14)
            text(draw, (center, y + (23 if compact else 31)), item["title"],
                 title_size, "ink", True)
            start_y = y + (45 if compact else 62)
            spacing = (
                min(17, max(14, (h - 48) // max(1, len(lines))))
                if compact
                else min(27, max(20, (h - 65) // max(1, len(lines))))
            )
            for idx, line in enumerate(lines):
                text(draw, (center, start_y + idx * spacing), line, line_size, "muted")
        else:
            text(draw, (center, y + h // 2), item["title"], title_size, "ink", True)

    for item in scene.get("labels", []):
        text(
            draw, item["xy"], item["text"], item.get("size", 18),
            item.get("fill", "ink"), item.get("bold", False),
            item.get("anchor", "mm"),
        )

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


def write_svg(scene: dict, path: Path) -> None:
    width, height = scene["width"], scene["height"]
    bg = color(scene.get("bg", "bg"))
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<style>text{font-family:'Microsoft YaHei',sans-serif}</style>",
        '<defs><marker id="a" markerWidth="10" markerHeight="10" refX="9" refY="5" '
        'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#617089"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="{bg}"/>',
    ]
    for item in scene.get("bands", []):
        out.append(
            f'<rect x="{item["x"]}" y="{item["y"]}" width="{item["w"]}" '
            f'height="{item["h"]}" rx="22" fill="{color(item.get("fill","white"))}" '
            f'stroke="{color(item.get("stroke","gray_soft"))}" stroke-width="2"/>'
        )
        out.append(
            f'<text x="{item["x"] + 22}" y="{item["y"] + 31}" font-size="20" '
            f'font-weight="700" fill="{color(item.get("text","blue"))}">'
            f'{escape(item["label"])}</text>'
        )
    for line in scene.get("edges", []):
        points = " ".join(f"{x},{y}" for x, y in line["points"])
        dash = ' stroke-dasharray="8 6"' if line.get("dashed") else ""
        marker = ' marker-end="url(#a)"' if line.get("arrow", True) else ""
        out.append(
            f'<polyline points="{points}" fill="none" stroke="{color(line.get("stroke","line"))}" '
            f'stroke-width="{line.get("width",3)}"{dash}{marker}/>'
        )
        for px, py in line.get("messages", []):
            out.append(
                f'<circle cx="{px}" cy="{py}" r="6" fill="{bg}" '
                f'stroke="{color(line.get("stroke","line"))}" stroke-width="2"/>'
            )
        if line.get("label"):
            x, y = line["label_xy"]
            out.append(
                f'<text x="{x}" y="{y + 6}" text-anchor="middle" font-size="16" '
                f'font-weight="700" fill="{color(line.get("stroke","line"))}">'
                f'{escape(line["label"])}</text>'
            )
    for item in scene["boxes"]:
        out.append(
            f'<rect x="{item["x"]}" y="{item["y"]}" width="{item["w"]}" '
            f'height="{item["h"]}" rx="16" fill="{color(item.get("fill","white"))}" '
            f'stroke="{color(item.get("stroke","line"))}" stroke-width="2"/>'
        )
        center = item["x"] + item["w"] / 2
        lines = item.get("lines", [])
        compact = bool(lines) and item["h"] < 100
        title_size = item.get("title_size", 23)
        line_size = item.get("line_size", 17)
        if compact:
            title_size = min(title_size, 19)
            line_size = min(line_size, 14)
        title_y = item["y"] + (
            (34 if compact else 43) if lines else item["h"] / 2 + 8
        )
        out.append(
            f'<text x="{center}" y="{title_y}" text-anchor="middle" '
            f'font-size="{title_size}" font-weight="700" '
            f'fill="{P["ink"]}">{escape(item["title"])}</text>'
        )
        if lines:
            start_y = item["y"] + (55 if compact else 75)
            spacing = (
                min(17, max(14, (item["h"] - 48) // max(1, len(lines))))
                if compact
                else min(27, max(20, (item["h"] - 65) // max(1, len(lines))))
            )
            for idx, line in enumerate(lines):
                out.append(
                    f'<text x="{center}" y="{start_y + idx * spacing}" '
                    f'text-anchor="middle" font-size="{line_size}" '
                    f'fill="{P["muted"]}">{escape(line)}</text>'
                )
    for item in scene.get("labels", []):
        out.append(
            f'<text x="{item["xy"][0]}" y="{item["xy"][1] + 6}" '
            f'text-anchor="{item.get("anchor","middle") if item.get("anchor") != "mm" else "middle"}" '
            f'font-size="{item.get("size",18)}" '
            f'font-weight="{700 if item.get("bold") else 400}" '
            f'fill="{color(item.get("fill","ink"))}">{escape(item["text"])}</text>'
        )
    for legend in scene.get("legends", []):
        x, y = legend["xy"]
        out.append(
            f'<rect x="{x}" y="{y}" width="{legend["w"]}" height="{legend["h"]}" '
            f'rx="12" fill="#FFFFFF" stroke="{P["gray_soft"]}" stroke-width="2"/>'
        )
        out.append(
            f'<text x="{x+16}" y="{y+27}" font-size="17" font-weight="700" '
            f'fill="{P["ink"]}">{escape(legend["title"])}</text>'
        )
        for idx, line in enumerate(legend["lines"]):
            out.append(
                f'<text x="{x+16}" y="{y+53+idx*21}" font-size="14" '
                f'fill="{P["muted"]}">{escape(line)}</text>'
            )
    out.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")


def architecture_scene() -> dict:
    return {
        "width": 1920, "height": 1220, "bg": "bg",
        "bands": [
            {"x": 50, "y": 125, "w": 1820, "h": 140, "label": "01  用户、入口与资料来源", "fill": "blue_soft"},
            {"x": 50, "y": 295, "w": 1820, "h": 135, "label": "02  v1.0 Web 入口与 FastAPI 服务", "fill": "cyan_soft"},
            {"x": 50, "y": 460, "w": 1820, "h": 190, "label": "03  Agent 任务理解、策略选择与编排", "fill": "purple_soft"},
            {"x": 50, "y": 680, "w": 1820, "h": 190, "label": "04  本地知识、混合检索与证据核验", "fill": "green_soft"},
            {"x": 50, "y": 900, "w": 1820, "h": 190, "label": "05  外部模型、可选联网工具与验证资产", "fill": "orange_soft"},
            {"x": 50, "y": 1120, "w": 1820, "h": 60, "label": "06  可信性、离线评测与运行日志", "fill": "gray_soft"},
        ],
        "boxes": [
            box(110, 165, 330, 72, "学生用户", ["Web 统一提问 · 查看引用 · 继续追问"], "white", "blue"),
            box(490, 165, 330, 72, "知识库维护者", ["登记资料 · 核验元数据 · 重建索引"], "white", "blue"),
            box(870, 165, 390, 72, "学校 / 学院官方网站", ["通知 · 办法 · 附件 · 培养方案"], "white", "blue"),
            box(1310, 165, 450, 72, "Tavily 联网工具（候选）", ["仅核验官方公开信息 · 非首版硬依赖"], "white", "blue"),
            box(110, 325, 330, 78, "Web 用户入口", ["HTML / CSS / JavaScript", "统一提问、来源与不确定性展示"], "white", "cyan"),
            box(490, 325, 330, 78, "FastAPI 后端", ["统一接口 / 参数校验", "异常处理 / 结果返回"], "white", "cyan"),
            box(870, 325, 390, 78, "Ask API 与响应层", ["POST /api/ask", "答案 + citations + status"], "white", "cyan"),
            box(1310, 325, 450, 78, "现有原型与离线 PoC", ["Figma 原型已有", "9 项测试通过 · 非真实模型联调"], "orange_soft", "orange"),
            box(100, 500, 300, 115, "任务识别", ["任务类型 / 用户对象", "竞赛、年份、用途等实体"], "white", "purple"),
            box(435, 500, 300, 115, "策略选择与路由", ["事务 / 机会 / 规划", "v1.0 聚焦官方依据查询"], "white", "purple"),
            box(770, 500, 300, 115, "主动追问", ["缺年级、事项、年份或用途", "信息不足时不猜测结论"], "white", "purple"),
            box(1105, 500, 350, 115, "Agent 编排器", ["选择检索、核验与回答步骤", "受控调用本地与外部工具"], "white", "purple"),
            box(1490, 500, 325, 115, "回答组织", ["结论解释 / 引用 / 下一步", "旧通知与冲突显式提示"], "white", "purple"),
            box(95, 720, 300, 115, "混合检索", ["本地资料优先 · Top-K", "关键词与语义召回"], "white", "green"),
            box(430, 720, 285, 115, "Chroma 向量索引", ["Embedding 生成", "语义近邻检索"], "white", "green"),
            box(750, 720, 265, 115, "BM25 索引", ["关键词精确匹配", "规则名称 / 文号 / 年度"], "white", "green"),
            box(1050, 720, 285, 115, "RRF 融合排序", ["融合两路候选", "去重并保留召回依据"], "white", "green"),
            box(1370, 720, 445, 115, "证据核验", ["来源 / 日期 / 适用范围 / 时效", "无依据或冲突时拒绝确定结论"], "white", "green"),
            box(95, 935, 390, 115, "本地知识资产", ["原始资料 + 中文整理稿", "CSV 索引 / 状态 / 页码定位"], "white", "orange"),
            box(520, 935, 300, 115, "Embedding 组件", ["文本分块向量化", "索引可重建"], "white", "orange"),
            box(855, 935, 280, 115, "Qwen API", ["理解问题", "基于证据组织回答"], "white", "orange"),
            box(1170, 935, 290, 115, "Tavily（可选）", ["候选联网核验", "失败时不生成无依据结论"], "white", "orange"),
            box(1495, 935, 320, 115, "离线 PoC 与评测", ["来源追溯 / 事实正确性", "任务适应 / 无依据处理"], "white", "orange"),
            box(95, 1142, 550, 32, "离线测试、失败降级、调用日志与资料更新记录", [], "white", "line", title_size=18),
            box(680, 1142, 540, 32, "不采集成绩、密码、统本身份凭据或无关个人数据", [], "white", "line", title_size=18),
            box(1255, 1142, 565, 32, "当前状态：资料已登记，真实 Agent 与混合检索尚未完成联调", [], "white", "line", title_size=18),
        ],
        "edges": [
            edge([(275, 237), (275, 325)], "blue", "提问", (325, 282)),
            edge([(655, 237), (335, 935)], "orange", "维护资料", (495, 750)),
            edge([(1065, 237), (280, 935)], "blue", "官方原文", (650, 890)),
            edge([(440, 364), (490, 364)], "cyan", "请求", (465, 346)),
            edge([(820, 364), (870, 364)], "cyan", "/api/ask", (845, 346)),
            edge([(1065, 403), (1070, 500)], "purple", "任务", (1125, 457)),
            edge([(400, 557), (435, 557)], "purple", "分类", (417, 539)),
            edge([(735, 557), (770, 557)], "purple", "缺信息", (752, 539)),
            edge([(1070, 557), (1105, 557)], "purple", "路由", (1087, 539)),
            edge([(1160, 615), (260, 720)], "green", "检索计划", (750, 680)),
            edge([(395, 777), (430, 777)], "green", "语义", (412, 759)),
            edge([(715, 777), (750, 777)], "green", "关键词", (732, 759)),
            edge([(1015, 777), (1050, 777)], "green", "候选", (1032, 759)),
            edge([(1335, 777), (1370, 777)], "green", "融合", (1352, 759)),
            edge([(1590, 720), (1590, 615)], "green", "可信证据", (1655, 665)),
            edge([(485, 935), (620, 835)], "orange", "构建索引", (555, 885)),
            edge([(309, 935), (309, 835)], "orange", "分块/元数据", (370, 890)),
            edge([(995, 935), (1240, 615)], "orange", "证据上下文", (1215, 780)),
            edge([(1315, 935), (1510, 835)], "orange", "按需核验", (1445, 890)),
            edge([(1815, 557), (1220, 365)], "cyan", "响应", (1490, 455)),
            edge([(870, 364), (440, 364)], "cyan", "最终结果", (650, 455)),
            edge([(275, 325), (275, 237)], "blue", "来源展示", (225, 282)),
            edge([(770, 575), (1490, 575)], "red", "信息缺失 → 先追问", (1120, 625), dashed=True),
        ],
        "labels": [
            {"xy": (960, 34), "text": "CodeMind-FZU 系统技术架构图", "size": 34, "bold": True},
            {"xy": (960, 75), "text": "基于 2026-10-24 开题答辩方案 · 本地知识优先 · 可追溯回答", "size": 20, "fill": "muted"},
            {"xy": (960, 1203), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  数据库、独立管理端与正式部署为后续设计", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (1440, 32), "w": 380, "h": 98, "title": "版本边界", "lines": [
                "v1.0：四类官方资料查询与引用",
                "候选：Tavily 联网核验，非硬依赖",
                "后续：管理端、持久化、个性化推荐",
            ]},
        ],
    }


def comm_qa_scene() -> dict:
    return {
        "width": 1860, "height": 1180, "bg": "bg",
        "boxes": [
            box(75, 245, 230, 90, ":学生浏览器", ["Browser"], "blue_soft", "blue"),
            box(365, 210, 235, 95, ":Web 用户入口", ["Frontend"], "cyan_soft", "cyan"),
            box(365, 560, 235, 95, ":FastAPI 后端", ["AskController"], "cyan_soft", "cyan"),
            box(690, 210, 250, 95, ":任务识别", ["TaskRouter"], "purple_soft", "purple"),
            box(690, 520, 270, 105, ":Agent 编排器", ["AgentOrchestrator"], "purple_soft", "purple"),
            box(690, 780, 270, 100, ":混合检索器", ["HybridRetriever"], "green_soft", "green"),
            box(365, 845, 230, 85, ":Chroma 向量索引", ["ChromaIndex"], "orange_soft", "orange"),
            box(365, 1000, 230, 85, ":BM25 索引", ["BM25Index"], "orange_soft", "orange"),
            box(690, 995, 270, 90, ":RRF 融合", ["RRFRanker"], "green_soft", "green"),
            box(1010, 835, 270, 100, ":证据核验", ["EvidenceVerifier"], "green_soft", "green"),
            box(1340, 760, 245, 90, ":Tavily（可选）", ["OnlineCheck"], "orange_soft", "orange"),
            box(1300, 1010, 255, 95, ":Qwen API", ["LLMAdapter"], "purple_soft", "purple"),
            box(1300, 280, 260, 95, ":回答组织", ["AnswerComposer"], "cyan_soft", "cyan"),
            box(1320, 540, 250, 95, ":主动追问", ["Clarifier"], "red_soft", "red"),
        ],
        "edges": [
            edge([(305, 290), (365, 255)], "blue", "1", (332, 252), messages=[(335, 273)]),
            edge([(482, 305), (482, 560)], "cyan", "2 / 10", (532, 435)),
            edge([(600, 590), (690, 255)], "cyan", "3", (645, 420)),
            edge([(815, 305), (815, 520)], "purple", "4", (865, 420)),
            edge([(790, 520), (790, 210)], "red", "4a 缺信息", (700, 405), dashed=True),
            edge([(960, 570), (960, 280)], "red", "4b 追问", (1040, 420), dashed=True),
            edge([(825, 625), (825, 780)], "green", "5", (875, 705)),
            edge([(690, 830), (595, 877)], "orange", "5.1a", (630, 815)),
            edge([(690, 865), (595, 1040)], "orange", "5.1b", (650, 925)),
            edge([(595, 1040), (690, 1040)], "green", "5.2", (642, 1020)),
            edge([(960, 830), (1010, 885)], "green", "6", (985, 840)),
            edge([(1145, 835), (1340, 805)], "orange", "6.1 按需", (1245, 790), dashed=True),
            edge([(1145, 885), (1300, 550)], "purple", "7 证据请求", (1215, 710)),
            edge([(1300, 1055), (1145, 935)], "purple", "7.1 草稿", (1215, 1000)),
            edge([(1115, 835), (1300, 340)], "green", "8 校验", (1235, 580)),
            edge([(1300, 325), (600, 610)], "cyan", "9 最终响应", (940, 420)),
            edge([(365, 255), (305, 290)], "blue", "10 引用与状态", (275, 355), dashed=True),
        ],
        "labels": [
            {"xy": (930, 35), "text": "UML 通信图 · 官方资料问答", "size": 34, "bold": True},
            {"xy": (930, 76), "text": "v1.0 主路径：识别任务 → 混合检索 → 证据核验 → Qwen 组织回答 → 引用输出", "size": 20, "fill": "muted"},
            {"xy": (1510, 205), "text": "目标：有依据才回答", "size": 18, "bold": True, "fill": "green"},
            {"xy": (1510, 230), "text": "无依据则说明无法确认", "size": 16, "fill": "muted"},
            {"xy": (930, 1138), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  当前尚无真实 Qwen 联调与会话持久化", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (75, 70), "w": 525, "h": 112, "title": "消息与边界", "lines": [
                "1—10：v1.0 问答主路径",
                "4a/4b：信息不足时先追问，不进入检索",
                "6.1：Tavily 仅按需核验官方公开信息",
            ]},
        ],
    }


def comm_ingestion_scene() -> dict:
    return {
        "width": 1860, "height": 1180, "bg": "bg",
        "boxes": [
            box(70, 240, 235, 95, ":知识库维护者", ["Maintainer"], "blue_soft", "blue"),
            box(365, 215, 260, 100, ":维护脚本 / 管理端", ["IngestionEntry"], "cyan_soft", "cyan"),
            box(365, 610, 260, 100, ":元数据与哈希检查", ["MetadataGate"], "cyan_soft", "cyan"),
            box(715, 195, 270, 100, ":解析与 OCR", ["ParserOCR"], "purple_soft", "purple"),
            box(715, 460, 270, 110, ":本地知识资产", ["LocalKnowledge"], "orange_soft", "orange"),
            box(715, 735, 270, 100, ":分块与定位", ["ChunkBuilder"], "green_soft", "green"),
            box(1080, 180, 250, 95, ":CSV 元数据索引", ["IndexCSV"], "orange_soft", "orange"),
            box(1080, 445, 250, 100, ":Chroma 向量库", ["ChromaBuilder"], "purple_soft", "purple"),
            box(1080, 710, 250, 100, ":BM25 索引", ["BM25Builder"], "orange_soft", "orange"),
            box(1080, 940, 250, 100, ":质量与时效核验", ["QualityGate"], "green_soft", "green"),
            box(1400, 445, 275, 105, ":离线评测", ["PoCTestSuite"], "green_soft", "green"),
            box(1400, 715, 275, 105, ":更新报告", ["MaintenanceReport"], "cyan_soft", "cyan"),
        ],
        "edges": [
            edge([(305, 287), (365, 265)], "blue", "1", (334, 250), messages=[(335, 275)]),
            edge([(495, 315), (495, 610)], "cyan", "2", (545, 462)),
            edge([(625, 645), (715, 250)], "cyan", "3", (675, 410)),
            edge([(850, 295), (850, 460)], "purple", "4", (900, 380)),
            edge([(985, 500), (1080, 227)], "orange", "5", (1032, 365)),
            edge([(850, 570), (850, 735)], "green", "6", (900, 650)),
            edge([(985, 785), (1080, 490)], "purple", "7 分块", (1032, 625)),
            edge([(985, 800), (1080, 760)], "orange", "7b 关键词", (1032, 750)),
            edge([(850, 735), (1080, 990)], "green", "8 检查", (975, 875)),
            edge([(1205, 445), (1205, 280)], "orange", "5.1 状态", (1260, 360)),
            edge([(1330, 985), (1400, 500)], "green", "9 运行测试", (1370, 745)),
            edge([(1330, 995), (1400, 770)], "cyan", "10 报告", (1370, 900)),
            edge([(1537, 715), (495, 710)], "cyan", "10.1 状态与待核项", (1015, 675), dashed=True),
        ],
        "labels": [
            {"xy": (930, 35), "text": "UML 通信图 · 知识资料维护与索引更新", "size": 34, "bold": True},
            {"xy": (930, 76), "text": "首版使用本地资料、CSV 索引和可重建索引；正式 Web 管理端属于后续设计", "size": 20, "fill": "muted"},
            {"xy": (1510, 160), "text": "资料先核验，再进入问答", "size": 18, "bold": True, "fill": "green"},
            {"xy": (1510, 185), "text": "正文提取 ≠ 向量化 ≠ 联网复核", "size": 16, "fill": "muted"},
            {"xy": (930, 1125), "text": "编制：赵紫龙  |  版本：v1.0  |  日期：2026-11-08  |  开题稿记录 44 条资料、43 条已提取正文、1 条待 OCR", "size": 16, "fill": "muted"},
        ],
        "legends": [
            {"xy": (70, 70), "w": 540, "h": 112, "title": "落地方式", "lines": [
                "v1.0：维护者运行入库脚本并重建索引",
                "v1.1：可增加 Web 管理端与审核状态",
                "任意步骤失败：不更新问答可见索引",
            ]},
        ],
    }


def drawio_box(id_: str, label: str, x: int, y: int, w: int, h: int,
               fill: str, stroke: str) -> str:
    value = escape(label, {'"': "&quot;"})
    style = (
        "rounded=1;whiteSpace=wrap;html=1;arcSize=12;"
        f"fillColor={fill};strokeColor={stroke};strokeWidth=2;"
        "fontFamily=Microsoft YaHei;fontSize=16;"
    )
    return (
        f'<mxCell id="{id_}" value="{value}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        "</mxCell>"
    )


def drawio_edge(id_: str, source: str, target: str, label: str = "") -> str:
    return (
        f'<mxCell id="{id_}" value="{escape(label)}" style="endArrow=block;html=1;'
        "rounded=0;orthogonalLoop=1;jettySize=auto;strokeColor=#617089;strokeWidth=2;"
        'fontFamily=Microsoft YaHei;fontSize=14;" edge="1" parent="1" '
        f'source="{source}" target="{target}"><mxGeometry relative="1" as="geometry"/>'
        "</mxCell>"
    )


def write_drawio(name: str, filename: str, cells: list[str],
                 width: int = 1600, height: int = 950) -> None:
    body = "\n".join("        " + cell for cell in cells)
    value = (
        '<mxfile host="app.diagrams.net" modified="2026-11-08T08:00:00.000Z" '
        'agent="CodeMind-FZU" version="24.0.0">\n'
        f'  <diagram name="{escape(name)}" id="{Path(filename).stem}">\n'
        f'    <mxGraphModel dx="{width}" dy="{height}" grid="1" gridSize="10" '
        'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" '
        f'pageScale="1" pageWidth="{width}" pageHeight="{height}" math="0" shadow="0">\n'
        '      <root>\n        <mxCell id="0"/>\n        <mxCell id="1" parent="0"/>\n'
        f"{body}\n      </root>\n    </mxGraphModel>\n  </diagram>\n</mxfile>\n"
    )
    target = ARCH_DIR if filename.startswith("系统") else COMM_DIR
    (target / filename).write_text(value, encoding="utf-8")


def write_drawio_files() -> None:
    write_drawio(
        "系统技术架构图", "系统技术架构图_赵紫龙_v1.drawio",
        [
            drawio_box("title", "CodeMind-FZU 系统技术架构图\nWeb + FastAPI + 本地混合检索 + Qwen + 证据核验",
                       300, 20, 1000, 66, "#F5F8FC", "#F5F8FC"),
            drawio_box("student", "学生用户\nWeb 统一提问 / 查看引用", 80, 120, 260, 65, "#EAF0FF", "#1F5EFF"),
            drawio_box("maintainer", "知识库维护者\n登记资料 / 核验 / 重建索引", 380, 120, 290, 65, "#EAF0FF", "#1F5EFF"),
            drawio_box("sources", "学校 / 学院官方网站\n通知 / 办法 / 附件 / 培养方案", 710, 120, 360, 65, "#EAF0FF", "#1F5EFF"),
            drawio_box("tavily", "Tavily 联网工具（候选）\n仅按需核验官方公开信息", 1110, 120, 390, 65, "#EAF0FF", "#1F5EFF"),
            drawio_box("web", "Web 用户入口\nHTML / CSS / JavaScript", 80, 245, 270, 70, "#E4F7FA", "#0D91A8"),
            drawio_box("api", "FastAPI 后端\n接口校验 / 异常处理", 390, 245, 270, 70, "#E4F7FA", "#0D91A8"),
            drawio_box("response", "Ask API 与响应\n答案 + citations + status", 700, 245, 300, 70, "#E4F7FA", "#0D91A8"),
            drawio_box("poc", "现有原型与离线 PoC\nFigma 原型 / 9 项测试", 1040, 245, 460, 70, "#FFF1DF", "#C46A12"),
            drawio_box("classify", "任务识别\n任务 / 用户 / 实体", 80, 390, 250, 85, "#F0EAFF", "#7448D8"),
            drawio_box("router", "策略选择与路由\nv1.0 聚焦官方依据查询", 370, 390, 260, 85, "#F0EAFF", "#7448D8"),
            drawio_box("clarify", "主动追问\n信息不足不猜测", 670, 390, 250, 85, "#FCEBEF", "#B93C4F"),
            drawio_box("agent", "Agent 编排器\n受控选择工具与步骤", 960, 390, 270, 85, "#F0EAFF", "#7448D8"),
            drawio_box("compose", "回答组织\n引用 / 不确定性 / 下一步", 1270, 390, 230, 85, "#FCEBEF", "#B93C4F"),
            drawio_box("hybrid", "混合检索\n本地资料优先 / Top-K", 80, 565, 250, 90, "#E6F6EF", "#16845B"),
            drawio_box("chroma", "Chroma 向量索引\nEmbedding + 近邻", 365, 565, 250, 90, "#E6F6EF", "#16845B"),
            drawio_box("bm25", "BM25 索引\n关键词 / 文号 / 年度", 650, 565, 250, 90, "#E6F6EF", "#16845B"),
            drawio_box("rrf", "RRF 融合排序\n去重与候选融合", 935, 565, 250, 90, "#E6F6EF", "#16845B"),
            drawio_box("verify", "证据核验\n来源 / 日期 / 范围 / 时效", 1220, 565, 280, 90, "#E6F6EF", "#16845B"),
            drawio_box("local", "本地知识资产\n原始资料 + Markdown + CSV", 80, 750, 300, 90, "#FFF1DF", "#C46A12"),
            drawio_box("embed", "Embedding 组件\n分块向量化", 415, 750, 240, 90, "#FFF1DF", "#C46A12"),
            drawio_box("qwen", "Qwen API\n理解问题 / 组织回答", 690, 750, 260, 90, "#FFF1DF", "#C46A12"),
            drawio_box("online", "Tavily（可选）\n失败时不作无依据结论", 985, 750, 285, 90, "#FFF1DF", "#C46A12"),
            drawio_box("eval", "离线 PoC 与评测\n9 项测试 / 来源可追溯", 1305, 750, 195, 90, "#FFF1DF", "#C46A12"),
            drawio_edge("a1", "student", "web", "提问"),
            drawio_edge("a2", "web", "api", "请求"),
            drawio_edge("a3", "api", "classify", "任务"),
            drawio_edge("a4", "classify", "router", "分类"),
            drawio_edge("a5", "router", "clarify", "缺信息"),
            drawio_edge("a6", "router", "agent", "路由"),
            drawio_edge("a7", "agent", "hybrid", "检索计划"),
            drawio_edge("a8", "hybrid", "chroma", "语义"),
            drawio_edge("a9", "hybrid", "bm25", "关键词"),
            drawio_edge("a10", "chroma", "rrf", "候选"),
            drawio_edge("a11", "bm25", "rrf", "候选"),
            drawio_edge("a12", "rrf", "verify", "融合"),
            drawio_edge("a13", "verify", "compose", "可信证据"),
            drawio_edge("a14", "local", "embed", "索引素材"),
            drawio_edge("a15", "embed", "chroma", "向量"),
            drawio_edge("a16", "qwen", "verify", "证据上下文"),
            drawio_edge("a17", "online", "verify", "按需核验"),
            drawio_edge("a18", "compose", "response", "最终结果"),
            drawio_edge("a19", "response", "web", "返回"),
            drawio_edge("a20", "web", "student", "来源展示"),
            drawio_box("bottom", "首版不包含数据库、独立管理端和正式部署；Tavily 为候选工具，Qwen 真实联调待验证",
                       80, 870, 1420, 44, "#EDF1F6", "#617089"),
        ],
    )

    write_drawio(
        "UML通信图_官方资料问答", "UML通信图_智能问答_赵紫龙_v1.drawio",
        [
            drawio_box("title", "UML 通信图 · 官方资料问答\n识别任务 → 混合检索 → 证据核验 → Qwen 回答 → 引用输出",
                       270, 20, 1060, 66, "#F5F8FC", "#F5F8FC"),
            drawio_box("browser", ":学生浏览器\nBrowser", 70, 220, 210, 70, "#EAF0FF", "#1F5EFF"),
            drawio_box("web", ":Web 用户入口\nFrontend", 330, 190, 220, 70, "#E4F7FA", "#0D91A8"),
            drawio_box("api", ":FastAPI 后端\nAskController", 350, 520, 220, 70, "#E4F7FA", "#0D91A8"),
            drawio_box("router", ":任务识别\nTaskRouter", 640, 180, 220, 70, "#F0EAFF", "#7448D8"),
            drawio_box("agent", ":Agent 编排器\nAgentOrchestrator", 650, 430, 250, 80, "#F0EAFF", "#7448D8"),
            drawio_box("retriever", ":混合检索器\nHybridRetriever", 650, 670, 250, 80, "#E6F6EF", "#16845B"),
            drawio_box("chroma", ":Chroma 向量索引\nChromaIndex", 350, 740, 220, 70, "#FFF1DF", "#C46A12"),
            drawio_box("bm25", ":BM25 索引\nBM25Index", 350, 850, 220, 70, "#FFF1DF", "#C46A12"),
            drawio_box("rrf", ":RRF 融合\nRRFRanker", 650, 850, 230, 75, "#E6F6EF", "#16845B"),
            drawio_box("verify", ":证据核验\nEvidenceVerifier", 960, 720, 230, 75, "#E6F6EF", "#16845B"),
            drawio_box("online", ":Tavily（可选）\nOnlineCheck", 1260, 660, 220, 70, "#FFF1DF", "#C46A12"),
            drawio_box("qwen", ":Qwen API\nLLMAdapter", 1220, 850, 220, 70, "#F0EAFF", "#7448D8"),
            drawio_box("compose", ":回答组织\nAnswerComposer", 1220, 310, 220, 70, "#E4F7FA", "#0D91A8"),
            drawio_box("clarify", ":主动追问\nClarifier", 1240, 450, 210, 70, "#FCEBEF", "#B93C4F"),
            drawio_edge("q1", "browser", "web", "1"),
            drawio_edge("q2", "web", "api", "2 / 10"),
            drawio_edge("q3", "api", "router", "3"),
            drawio_edge("q4", "router", "agent", "4"),
            drawio_edge("q5", "router", "clarify", "4a/4b"),
            drawio_edge("q6", "agent", "retriever", "5"),
            drawio_edge("q7", "retriever", "chroma", "5.1a"),
            drawio_edge("q8", "retriever", "bm25", "5.1b"),
            drawio_edge("q9", "chroma", "rrf", "候选"),
            drawio_edge("q10", "bm25", "rrf", "候选"),
            drawio_edge("q11", "rrf", "verify", "6"),
            drawio_edge("q12", "verify", "online", "6.1 按需"),
            drawio_edge("q13", "verify", "qwen", "7 证据请求"),
            drawio_edge("q14", "qwen", "verify", "7.1 草稿"),
            drawio_edge("q15", "verify", "compose", "8 校验"),
            drawio_edge("q16", "compose", "api", "9 最终响应"),
            drawio_edge("q17", "api", "browser", "10 引用与状态"),
        ],
    )

    write_drawio(
        "UML通信图_知识维护", "UML通信图_知识入库_赵紫龙_v1.drawio",
        [
            drawio_box("title", "UML 通信图 · 知识资料维护与索引更新\n首版使用本地资料、CSV 索引和可重建索引",
                       270, 20, 1060, 66, "#F5F8FC", "#F5F8FC"),
            drawio_box("maintainer", ":知识库维护者\nMaintainer", 70, 220, 210, 70, "#EAF0FF", "#1F5EFF"),
            drawio_box("entry", ":维护脚本 / 管理端\nIngestionEntry", 340, 190, 220, 75, "#E4F7FA", "#0D91A8"),
            drawio_box("metadata", ":元数据与哈希检查\nMetadataGate", 340, 550, 220, 75, "#E4F7FA", "#0D91A8"),
            drawio_box("parser", ":解析与 OCR\nParserOCR", 650, 175, 230, 75, "#F0EAFF", "#7448D8"),
            drawio_box("local", ":本地知识资产\nLocalKnowledge", 650, 400, 230, 80, "#FFF1DF", "#C46A12"),
            drawio_box("chunks", ":分块与定位\nChunkBuilder", 650, 660, 230, 75, "#E6F6EF", "#16845B"),
            drawio_box("csv", ":CSV 元数据索引\nIndexCSV", 980, 165, 220, 70, "#FFF1DF", "#C46A12"),
            drawio_box("chroma", ":Chroma 向量库\nChromaBuilder", 980, 390, 220, 75, "#F0EAFF", "#7448D8"),
            drawio_box("bm25", ":BM25 索引\nBM25Builder", 980, 620, 220, 75, "#FFF1DF", "#C46A12"),
            drawio_box("quality", ":质量与时效核验\nQualityGate", 980, 815, 220, 75, "#E6F6EF", "#16845B"),
            drawio_box("tests", ":离线评测\nPoCTestSuite", 1290, 390, 220, 75, "#E6F6EF", "#16845B"),
            drawio_box("report", ":更新报告\nMaintenanceReport", 1290, 620, 220, 75, "#E4F7FA", "#0D91A8"),
            drawio_edge("i1", "maintainer", "entry", "1"),
            drawio_edge("i2", "entry", "metadata", "2"),
            drawio_edge("i3", "metadata", "parser", "3"),
            drawio_edge("i4", "parser", "local", "4"),
            drawio_edge("i5", "local", "csv", "5"),
            drawio_edge("i6", "local", "chunks", "6"),
            drawio_edge("i7", "chunks", "chroma", "7 向量"),
            drawio_edge("i8", "chunks", "bm25", "7b 关键词"),
            drawio_edge("i9", "quality", "tests", "9"),
            drawio_edge("i10", "quality", "report", "10"),
            drawio_edge("i11", "report", "entry", "10.1 待核项"),
        ],
    )


def main() -> None:
    render(
        architecture_scene(),
        ARCH_DIR / "系统技术架构图_赵紫龙_v1.svg",
        ARCH_DIR / "系统技术架构图_赵紫龙_v1.png",
    )
    render(
        comm_qa_scene(),
        COMM_DIR / "UML通信图_智能问答_赵紫龙_v1.svg",
        COMM_DIR / "UML通信图_智能问答_赵紫龙_v1.png",
    )
    render(
        comm_ingestion_scene(),
        COMM_DIR / "UML通信图_知识入库_赵紫龙_v1.svg",
        COMM_DIR / "UML通信图_知识入库_赵紫龙_v1.png",
    )
    write_drawio_files()


if __name__ == "__main__":
    main()
