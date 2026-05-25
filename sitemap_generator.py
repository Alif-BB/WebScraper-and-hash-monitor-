"""
sitemap_generator.py
A lightweight Python sitemap generator that crawls a website and outputs sitemap.xml.
Tracks parent-child relationships for BFS tree visualization.
Uses concurrent requests within each BFS level for speed.
Includes per-domain rate limiting to avoid overwhelming servers.

Dependencies:
    pip install requests beautifulsoup4

Usage:
    python sitemap_generator.py https://example.com
    python sitemap_generator.py https://example.com --output my-sitemap.xml --max-pages 200
"""

import argparse
import threading
import time
import xml.etree.ElementTree as ET
import monitor
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_MAX_PAGES  = 1500
REQUEST_TIMEOUT    = 10    # seconds per request
MAX_WORKERS        = 10    # concurrent requests per BFS level
DELAY_PER_DOMAIN   = 0.5  # minimum seconds between requests to the same domain
HEADERS = {"User-Agent": "SitemapBot/1.0 (+https://github.com/your/repo)"}
DOC_EXTS  = {".pdf", ".pptx", ".xlsx", ".xls", ".wmv", ".mp4", ".avi", ".mov", ".docx", ".doc", ".zip"}
DOC_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "video/x-ms-wmv",
}


# ── Per-domain rate limiter ───────────────────────────────────────────────────

class DomainRateLimiter:
    """
    Ensures a minimum delay between consecutive requests to the same domain.
    Thread-safe — uses one lock per domain.
    """
    def __init__(self, delay: float):
        self.delay      = delay
        self._locks:      dict[str, threading.Lock]  = defaultdict(threading.Lock)
        self._last_req:   dict[str, float]            = defaultdict(float)
        self._meta_lock   = threading.Lock()

    def _get_lock(self, domain: str) -> threading.Lock:
        with self._meta_lock:
            return self._locks[domain]

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        lock   = self._get_lock(domain)
        with lock:
            elapsed = time.monotonic() - self._last_req[domain]
            wait_for = self.delay - elapsed
            if wait_for > 0:
                time.sleep(wait_for)
            self._last_req[domain] = time.monotonic()


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(url: str) -> str:
    """Strip fragment and trailing slash so we don't double-visit URLs."""
    parsed = urlparse(url)
    path   = parsed.path.rstrip("/") or "/"
    return parsed._replace(fragment="", path=path, query=parsed.query).geturl()


def is_same_domain(url: str, base: str) -> bool:
    url_host  = urlparse(url).netloc
    base_host = urlparse(base).netloc
    base_root = base_host.removeprefix("www.")
    return url_host == base_host or url_host.endswith("." + base_root)


def is_crawlable(url: str) -> bool:
    """Allow HTML pages and whitelisted documents. Skip all other assets."""
    skip_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
        ".ico", ".css", ".js",
        ".woff", ".woff2", ".ttf", ".eot",
    }
    path = urlparse(url).path.lower()
    return not any(path.endswith(ext) for ext in skip_exts)


def is_document(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DOC_EXTS)


# ── Single page fetcher ───────────────────────────────────────────────────────

def fetch_page(
    session:     requests.Session,
    url:         str,
    parent:      str | None,
    base:        str,
    rate_limiter: DomainRateLimiter,
) -> dict:
    """
    Fetch a single URL with rate limiting.
    Returns a result dict with: url, parent, status, content_type, links, error
    """
    rate_limiter.wait(url)  # enforce per-domain delay

    use_head = is_document(url)
    try:
        if use_head:
            resp = session.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        else:
            resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        return {"url": url, "parent": parent, "error": str(e), "links": []}

    final_url    = normalize(resp.url)
    status       = resp.status_code
    content_type = resp.headers.get("Content-Type", "")

    # Document — include in sitemap, no link extraction
    if status == 200 and any(ct in content_type for ct in DOC_TYPES):
        return {"url": final_url, "parent": parent, "status": status,
                "content_type": content_type, "is_doc": True, "links": [], "error": None}

    # Non-200 or non-HTML — skip
    if status != 200 or "text/html" not in content_type:
        return {"url": final_url, "parent": parent, "status": status,
                "content_type": content_type, "skip": True, "links": [], "error": None}

    # HTML page — extract links
    soup  = BeautifulSoup(resp.text, "html.parser")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = normalize(urljoin(final_url, href))
        if is_same_domain(abs_url, base) and is_crawlable(abs_url):
            links.append(abs_url)

    return {"url": final_url, "parent": parent, "status": status,
            "content_type": content_type, "is_doc": False, "links": links, "error": None}


# ── Crawler ───────────────────────────────────────────────────────────────────

def crawl(start_url: str, max_pages: int, workers: int, delay: float) -> list[dict]:
    """
    Level-by-level BFS crawl. Each level is fetched concurrently.
    Per-domain rate limiting prevents overwhelming any single server.
    Returns a list of dicts: {loc, lastmod, status, parent}
    """
    base         = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    visited:       set[str]    = set()
    results:       list[dict]  = []
    rate_limiter = DomainRateLimiter(delay)

    session = requests.Session()
    session.headers.update(HEADERS)

    current_level = [(normalize(start_url), None)]
    visited.add(normalize(start_url))

    print(f"🔍 Crawling {start_url} (max {max_pages} pages, {workers} workers, {delay}s delay/domain)…\n")

    while current_level and len(results) < max_pages:
        next_level: list[tuple[str, str | None]] = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fetch_page, session, url, parent, base, rate_limiter): (url, parent)
                for url, parent in current_level
            }
            for future in as_completed(futures):
                res    = future.result()
                url    = res["url"]
                parent = res["parent"]

                if res.get("error"):
                    print(f"  ⚠  Skip  {url}  ({res['error']})")
                    continue

                if res.get("skip"):
                    print(f"  ✗  {res['status']}  {url}")
                    continue

                if len(results) >= max_pages:
                    continue

                lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                if res.get("is_doc"):
                    results.append({"loc": url, "lastmod": lastmod, "status": res["status"], "parent": parent})
                    print(f"  📄  {res['status']}  {url}  (document)")
                else:
                    results.append({"loc": url, "lastmod": lastmod, "status": res["status"], "parent": parent})
                    print(f"  ✓  {res['status']}  {url}  (parent: {parent or 'root'})")

                    for link in res["links"]:
                        if link not in visited:
                            visited.add(link)
                            next_level.append((link, url))

        current_level = next_level

    print(f"\n✅ Done — {len(results)} pages found.\n")
    return results


# ── Sitemap builder ───────────────────────────────────────────────────────────

def build_sitemap(pages: list[dict], output_path: str) -> None:
    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")

    root = ET.Element(
        "urlset",
        attrib={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"},
    )

    for page in pages:
        url_el = ET.SubElement(root, "url")
        ET.SubElement(url_el, "loc").text       = page["loc"]
        ET.SubElement(url_el, "lastmod").text   = page["lastmod"]
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text  = "0.8"
        ET.SubElement(url_el, "parent").text    = page["parent"] or ""

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    with open(output_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False)

    print(f"📄 Sitemap saved → {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lightweight Python sitemap generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", help="Root URL to crawl (e.g. https://example.com)")
    parser.add_argument("--output", "-o", default="sitemap.xml",
                        help="Output file path (default: sitemap.xml)")
    parser.add_argument("--max-pages", "-m", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"Max pages to crawl (default: {DEFAULT_MAX_PAGES})")
    parser.add_argument("--workers", "-w", type=int, default=MAX_WORKERS,
                        help=f"Concurrent workers per BFS level (default: {MAX_WORKERS})")
    parser.add_argument("--delay", "-d", type=float, default=DELAY_PER_DOMAIN,
                        help=f"Delay in seconds between requests to same domain (default: {DELAY_PER_DOMAIN})")
    args = parser.parse_args()

    start = args.url if args.url.startswith("http") else f"https://{args.url}"

    pages = crawl(start, args.max_pages, args.workers, args.delay)

    if not pages:
        print("❌ No pages crawled. Check the URL or network.")
        return

    build_sitemap(pages, args.output)

    print("─" * 50)
    print("🔎 Starting monitor...\n")
    monitor.run(sitemap_path=args.output, db_path="monitor.db")


if __name__ == "__main__":
    main()