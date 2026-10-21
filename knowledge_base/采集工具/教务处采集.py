"""定向采集教务处公开资料。先扫描列表，再按人工审核的清单收录正文。"""

import argparse
import csv
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString

ROOT = Path(__file__).resolve().parents[1] / "政策资料"
BASE = "https://jwch.fzu.edu.cn/"
TODAY = "2026-10-21"
LOG = ROOT / "采集记录" / TODAY
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "CodeMind-FZU-KnowledgeCollector/1.0 (public academic notices)"


def fetch(url):
    """不进入统一认证，不携带账号或浏览器会话。"""
    for _ in range(6):
        if urlparse(url).hostname != "jwch.fzu.edu.cn":
            raise ValueError("需要登录或跳转站外：" + url)
        response = SESSION.get(url, timeout=30, allow_redirects=False)
        time.sleep(0.4)
        if response.is_redirect:
            url = urljoin(url, response.headers["Location"])
            continue
        response.raise_for_status()
        return response
    raise ValueError("跳转次数过多")


def soup_of(response):
    return BeautifulSoup(response.content.decode("utf-8-sig"), "html.parser")


def discover(cached=False):
    LOG.mkdir(parents=True, exist_ok=True)
    pages = ["index.htm", "jxtz.htm", "jxtz/215.htm", "jxtz/214.htm",
             "jxtz/jxyx.htm", "jxtz/jxyx/86.htm", "jxtz/jhk.htm",
             "jxwj/xssc/a2025n.htm", "bszn.htm", "jxwj/jxsc.htm"]
    records = {}
    errors = []
    for page in pages:
        try:
            snapshot = LOG / (page.replace("/", "_") + ".html")
            if cached and snapshot.exists():
                response = requests.Response()
                response._content = snapshot.read_bytes()
                response.url = urljoin(BASE, page)
            else:
                response = fetch(urljoin(BASE, page))
            soup = soup_of(response)
            (LOG / (page.replace("/", "_") + ".html")).write_bytes(response.content)
            nodes = soup.select("ul.list-gl li")
            for node in nodes:
                anchor = node.find("a", href=True)
                if not anchor:
                    continue
                url = urljoin(response.url, anchor["href"])
                title = anchor.get("title") or anchor.get_text(" ", strip=True)
                stamp = re.search(r"20\d{2}-\d{2}-\d{2}", node.get_text(" ", strip=True))
                record = records.setdefault(url, {"标题": title, "发布日期": stamp[0] if stamp else "", "网址": url, "发现栏目": []})
                if stamp:
                    record["发布日期"] = stamp[0]
                if page not in record["发现栏目"]:
                    record["发现栏目"].append(page)
            if page == "index.htm":
                for anchor in soup.select("a[href]"):
                    if re.search(r"info/\d+/\d+\.htm|wbnewsid=\d+", anchor["href"]):
                        url = urljoin(response.url, anchor["href"])
                        records.setdefault(url, {"标题": anchor.get("title") or anchor.get_text(" ", strip=True), "发布日期": "", "网址": url, "发现栏目": [page]})
            print(json.dumps({"栏目": page, "列表条数": len(nodes)}, ensure_ascii=False), flush=True)
        except Exception as exc:
            errors.append({"栏目": page, "错误": str(exc)})
    ordered = sorted(records.values(), key=lambda item: item["发布日期"], reverse=True)
    (LOG / "发现清单.json").write_text(json.dumps({"扫描日期": TODAY, "说明": "仅覆盖列出的页面；发布日期为空的条目须打开正文核验。", "资料": ordered, "错误": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"去重条数": len(ordered), "发现清单": str(LOG / "发现清单.json")}, ensure_ascii=False))
    print(json.dumps({"扫描错误": errors}, ensure_ascii=False))


def markdown(node, base):
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return str(node).replace("\xa0", " ")
    if node.name in {"script", "style", "noscript"}:
        return ""
    if node.name == "table":
        grid = {}
        source_rows = node.find_all("tr")
        for r, row in enumerate(source_rows):
            c = 0
            for cell in row.find_all(["th", "td"], recursive=False):
                while (r, c) in grid:
                    c += 1
                value = re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).replace("|", "\\|")
                height = max(1, int(cell.get("rowspan", 1)))
                width = max(1, int(cell.get("colspan", 1)))
                for dr in range(height):
                    for dc in range(width):
                        grid[r + dr, c + dc] = value
                c += width
        if not grid:
            return ""
        width = max(c for r, c in grid) + 1
        rows = [[grid.get((r, c), "") for c in range(width)] for r in range(len(source_rows))]
        lines = ["| " + " | ".join(row) + " |" for row in rows]
        lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
        return "\n\n" + "\n".join(lines) + "\n\n"
    if node.name == "img":
        return "\n[原文图片（未下载或识别）](" + urljoin(base, node.get("src", "")) + ")\n"
    if node.name == "br":
        return "\n"
    inner = "".join(markdown(child, base) for child in node.children)
    if node.name == "a" and node.get("href") and not node["href"].startswith("javascript:"):
        return "[" + inner.strip() + "](" + urljoin(base, node["href"]) + ")"
    if node.name in {"p", "div", "section"}:
        return "\n\n" + inner.strip() + "\n\n"
    if node.name == "li":
        return "\n- " + inner.strip() + "\n"
    return inner


def collect(selection, rebuild=False):
    data = json.loads(Path(selection).read_text(encoding="utf-8-sig"))
    index = ROOT / "知识库索引.csv"
    with index.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        records = list(reader)
    for field in ("截止日期", "文件成文日期"):
        if field not in fields:
            fields.append(field)
    existing = {record["来源网址"] for record in records}
    positions = {record["来源网址"]: i for i, record in enumerate(records)}
    results = []
    for item in data:
        if item["网址"] in existing and not rebuild:
            results.append({"标题": item["标题"], "结果": "已收录，跳过"})
            continue
        try:
            if rebuild:
                old = records[positions[item["网址"]]]
                response = requests.Response()
                response._content = (ROOT / old["原始文件"]).read_bytes()
                response.url = old["来源网址"]
            else:
                response = fetch(item["网址"])
            soup = soup_of(response)
            body = soup.select_one(".v_news_content") or soup.select_one("#vsb_content")
            if not body or len(body.get_text(strip=True)) < 60:
                raise ValueError("没有取得完整正文；未收录为成功资料")
            text = markdown(body, response.url)
            text = re.sub(r"\n[ \t]+", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            stamp = re.search(r"发布时间[：:]\s*(20\d{2}-\d{2}-\d{2})", soup.get_text(" ", strip=True))
            published = stamp[1] if stamp else item.get("发布日期", "")
            raw = ROOT / "原始资料" / "学校" / (item["文件名"] + ".html")
            clean = ROOT / "整理资料" / "学校" / (item["文件名"] + ".md")
            if not rebuild and (raw.exists() or clean.exists()):
                raise ValueError("文件名已存在，请核对后改名，未覆盖")
            attachments = []
            for anchor in soup.select("a[href]"):
                href = anchor["href"]
                if "/download.jsp" in href or re.search(r"\.(pdf|docx?|xlsx?|zip|rar)(?:\?|$)", href, re.I):
                    attachments.append({"名称": anchor.get_text(" ", strip=True), "网址": urljoin(response.url, href)})
            row = {field: "" for field in fields}
            row.update({"记录编号": item["记录编号"], "标题": item["标题"], "发布单位": "福州大学教务处", "负责部门": item.get("负责部门", "教务处"), "文号": item.get("文号", ""), "资料类型": item["资料类型"], "发布日期": published, "生效日期": item.get("生效日期", ""), "适用年级": item.get("适用年级", "大一至大三及其他适用本科生"), "适用专业": "按通知或培养方案适用", "适用对象": item.get("适用对象", "本科生"), "状态": item["状态"], "来源网址": item["网址"], "原始文件": raw.relative_to(ROOT).as_posix(), "最后核验日期": TODAY, "内容哈希": hashlib.sha256(response.content).hexdigest()})
            row["截止日期"] = item.get("截止日期", "")
            row["文件成文日期"] = item.get("文件成文日期", "")
            metadata = "\n".join(key + ": " + json.dumps(row[key], ensure_ascii=False) for key in fields if key != "内容哈希")
            content = "---\n" + metadata + "\n---\n\n# " + item["标题"] + "\n\n## 主要内容\n\n" + item["摘要"] + "\n\n## 时效与使用说明\n\n" + item["说明"] + "\n\n## 官网正文提取\n\n" + text + "\n"
            if attachments:
                content += "\n## 官网附件入口（本轮未下载或解析）\n\n" + "\n".join("- [" + (a["名称"] or "附件") + "](" + a["网址"] + ")" for a in attachments) + "\n"
            if not rebuild:
                raw.write_bytes(response.content)
            clean.write_text(content, encoding="utf-8")
            if rebuild:
                records[positions[item["网址"]]] = row
            else:
                records.append(row)
            existing.add(item["网址"])
            result = {"标题": item["标题"], "结果": "已保存HTML和中文正文", "发布日期": published, "正文字符数": len(text), "附件入口": attachments, "整理文件": clean.relative_to(ROOT).as_posix()}
        except Exception as exc:
            result = {"标题": item["标题"], "结果": "未收录", "原因": str(exc)}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    with index.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    LOG.mkdir(parents=True, exist_ok=True)
    (LOG / "收录结果.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"索引记录总数": len(records), "本轮成功": sum(r["结果"] == "已保存HTML和中文正文" for r in results)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--cached", action="store_true", help="仅重新解析已下载列表")
    parser.add_argument("--collect", metavar="审核清单JSON")
    parser.add_argument("--rebuild", action="store_true", help="从本地原始网页重新提取，保留合并表格关系")
    args = parser.parse_args()
    if args.discover:
        discover(args.cached)
    elif args.collect:
        collect(args.collect, args.rebuild)
    else:
        parser.error("请选择 --discover 或 --collect")
