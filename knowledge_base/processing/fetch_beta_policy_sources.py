"""Bounded official-source refresh for the 2026-11-23 Beta review batch.

No login credentials, crawling, approval or index writes. A login page is never
saved as policy正文. Existing approved/ and Alpha evidence are not overwritten.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "knowledge_base/processing/policy-review/2026-11-23"
OLD = ROOT / "knowledge_base/processing/policy-review/2026-11-19"


def digest(raw):
    return sha256(raw).hexdigest()


def fetch(item):
    result = dict(item, checked_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        with urlopen(Request(item["url"], headers={"User-Agent": "CodeMind-FZU academic policy review"}), timeout=25) as response:
            final = response.geturl()
            raw = response.read(12 * 1024 * 1024 + 1)
            if len(raw) > 12 * 1024 * 1024:
                raise ValueError("source exceeds review download limit")
            result.update(http_status=response.status, final_url=final, content_type=response.headers.get("Content-Type"),
                          bytes=len(raw), sha256=digest(raw))
        host = urlparse(final).hostname or ""
        if host == "sso.fzu.edu.cn" or "cas/login" in final:
            result.update(fetch_status="login_required", storage_key=None)
            return result, None
        if not (host == "fzu.edu.cn" or host.endswith(".fzu.edu.cn")):
            raise ValueError("unexpected non-official redirect")
        if item["name"].endswith((".xlsx", ".docx")) and not raw.startswith(b"PK"):
            raise ValueError("attachment response is not an OOXML archive")
        if item["name"].endswith(".pdf") and not raw.startswith(b"%PDF"):
            raise ValueError("attachment response is not a PDF")
        result.update(fetch_status="downloaded", storage_key=(REVIEW.relative_to(ROOT) / item["name"]).as_posix())
        return result, raw
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        result.update(fetch_status="unavailable", error_type=type(error).__name__, storage_key=None)
        return result, None


def refresh():
    from lxml import html
    REVIEW.mkdir(parents=True, exist_ok=True)
    old = json.loads((OLD / "source-fetch.json").read_text(encoding="utf-8"))
    items = [{"name": Path(r["storage_key"]).name, "url": r["url"], "purpose": "existing-policy-refresh"}
             for r in old if r.get("storage_key")]
    # Competition login failures have no retained storage_key in old fetches.
    if not any(i["name"] == "competition.html" for i in items):
        items.append({"name": "competition.html", "url": "https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbnewsid=14534&wbtreeid=1039", "purpose": "existing-policy-refresh"})
    items += [
        {"name": "innovation.html", "url": "https://jwch.fzu.edu.cn/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1095&wbnewsid=12993", "purpose": "innovation-credit-policy"},
        {"name": "retest.html", "url": "https://ccds.fzu.edu.cn/info/1138/11961.htm", "purpose": "2027-receiving-retest-policy"},
        {"name": "qinghe.html", "url": "https://ccds.fzu.edu.cn/info/1160/12008.htm", "purpose": "2026-2027-lab-notice"},
        {"name": "college-notices.html", "url": "https://ccds.fzu.edu.cn/xsgz/tzgg.htm", "purpose": "bounded-new-version-search"},
        {"name": "college-teaching.html", "url": "https://ccds.fzu.edu.cn/rcpy/jwgs.htm", "purpose": "bounded-new-version-search"},
        {"name": "student-regulations.html", "url": "https://stuic.fzu.edu.cn/xsgl/gzzd.htm", "purpose": "bounded-new-version-search"},
    ]
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloaded = list(pool.map(fetch, items))
    for record, raw in downloaded:
        if raw is not None:
            (ROOT / record["storage_key"]).write_bytes(raw)
        records.append(record)
    qinghe = next(r for r in records if r["name"] == "qinghe.html")
    attachments = []
    if qinghe.get("storage_key"):
        page = html.fromstring((ROOT / qinghe["storage_key"]).read_bytes())
        for anchor in page.xpath("//a[@href]"):
            label = anchor.text_content().strip()
            if ".xlsx" in label or ".docx" in label:
                attachments.append({"name": "qinghe-labs.xlsx" if ".xlsx" in label else "qinghe-registration.docx",
                                    "original_name": label.removeprefix("附件1：").removeprefix("附件2："),
                                    "url": urljoin(qinghe["url"], anchor.get("href")),
                                    "parent_url": qinghe["url"], "purpose": "qinghe-original-attachment"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        downloaded = list(pool.map(fetch, attachments))
    for record, raw in downloaded:
        if raw is not None:
            (ROOT / record["storage_key"]).write_bytes(raw)
            pattern = "*实验室需求一览表.xlsx" if record["name"].endswith("xlsx") else "*青禾计划*报名表.docx"
            archived = list((ROOT / "knowledge_base/政策资料/原始资料").rglob(pattern))
            record["matches_existing_archive"] = len(archived) == 1 and digest(archived[0].read_bytes()) == record["sha256"]
        records.append(record)
    (REVIEW / "source-fetch.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: r.get(k) for k in ("name", "fetch_status", "bytes", "matches_existing_archive")} for r in records], ensure_ascii=False))


def refresh_policy_attachments():
    """Refresh exact source-linked attachments, without downloading personal forms."""
    records = json.loads((REVIEW / "source-fetch.json").read_text(encoding="utf-8"))
    old = json.loads((OLD / "attachment-fetch.json").read_text(encoding="utf-8"))
    items = [{"name": Path(r["storage_key"]).name, "url": r["url"], "purpose": "policy-attachment-refresh"}
             for r in old if r.get("storage_key") and r["storage_key"].endswith((".docx", ".pdf"))]
    text = (REVIEW / "retest.html").read_text(encoding="utf-8")
    paths = re.findall(r'showVsbpdfIframe\("([^"\n]+\.pdf)"', text)
    if len(paths) != 1:
        raise ValueError("Expected one official retest embedded PDF URL")
    items.append({"name": "retest.pdf", "url": urljoin("https://ccds.fzu.edu.cn/", paths[0]),
                  "parent_url": "https://ccds.fzu.edu.cn/info/1138/11961.htm", "purpose": "retest-embedded-policy"})
    with ThreadPoolExecutor(max_workers=3) as pool:
        downloaded = list(pool.map(fetch, items))
    for record, raw in downloaded:
        if raw is not None:
            (ROOT / record["storage_key"]).write_bytes(raw)
            archived = OLD / record["name"]
            if archived.exists():
                record["matches_alpha_attachment"] = digest(archived.read_bytes()) == record["sha256"]
        records = [r for r in records if r["name"] != record["name"]] + [record]
    (REVIEW / "source-fetch.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: r.get(k) for k in ("name", "fetch_status", "bytes", "matches_alpha_attachment")} for r, _ in downloaded], ensure_ascii=False))


if __name__ == "__main__":
    import sys
    refresh_policy_attachments() if "--attachments" in sys.argv else refresh()
