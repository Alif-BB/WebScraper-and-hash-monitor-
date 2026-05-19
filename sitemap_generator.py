"""
sitemap_generator.py
A lightweight Python sitemap generator that crawls a website and outputs sitemap.xml.

Dependencies:
    pip install requests beautifulsoup4

Usage:
    python sitemap_generator.py https://example.com
    python sitemap_generator.py https://example.com --output my-sitemap.xml --max-pages 200
"""

import argparse
import xml.etree.ElementTree as ET
import monitor
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_MAX_PAGES = 1000
REQUEST_TIMEOUT = 10        # seconds per request
HEADERS = {"User-Agent": "SitemapBot/1.0 (+https://github.com/your/repo)"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(url: str) -> str:
    """Strip fragment and trailing slash so we don't double-visit URLs."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(fragment="", path=path, query=parsed.query).geturl()


def is_same_domain(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def is_crawlable(url: str) -> bool:
    """Skip non-HTML assets."""
    skip_exts = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
        ".pdf", ".zip", ".mp4", ".mp3", ".ico", ".css", ".js",
        ".woff", ".woff2", ".ttf", ".eot",
    }
    path = urlparse(url).path.lower()
    return not any(path.endswith(ext) for ext in skip_exts)


# ── Crawler ───────────────────────────────────────────────────────────────────

def crawl(start_url: str, max_pages: int) -> list[dict]:
    """
    BFS crawl starting from `start_url`.
    Returns a list of dicts: {loc, lastmod, status}
    """
    base = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    visited: set[str] = set()
    queue: deque[str] = deque([normalize(start_url)])
    results: list[dict] = []

    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"🔍 Crawling {start_url} (max {max_pages} pages)…\n")

    while queue and len(results) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        except requests.RequestException as e:
            print(f"  ⚠  Skip  {url}  ({e})")
            continue

        # Follow redirect — add final URL too
        final_url = normalize(resp.url)
        if final_url != url:
            if final_url in visited:
                continue
            visited.add(final_url)
            url = final_url

        status = resp.status_code
        content_type = resp.headers.get("Content-Type", "")

        if status != 200 or "text/html" not in content_type:
            print(f"  ✗  {status}  {url}")
            continue

        lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        results.append({"loc": url, "lastmod": lastmod, "status": status})
        print(f"  ✓  {status}  {url}")

        # Parse links
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_url = normalize(urljoin(url, href))
            if (
                is_same_domain(abs_url, base)
                and abs_url not in visited
                and is_crawlable(abs_url)
            ):
                queue.append(abs_url)

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
        ET.SubElement(url_el, "loc").text = page["loc"]
        ET.SubElement(url_el, "lastmod").text = page["lastmod"]
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.8"

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")  # Pretty-print (Python 3.9+)

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
    parser.add_argument(
        "--output", "-o",
        default="sitemap.xml",
        help="Output file path (default: sitemap.xml)",
    )
    parser.add_argument(
        "--max-pages", "-m",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Max pages to crawl (default: {DEFAULT_MAX_PAGES})",
    )
    args = parser.parse_args()

    # Ensure scheme
    start = args.url if args.url.startswith("http") else f"https://{args.url}"

    pages = crawl(start, args.max_pages)

    if not pages:
        print("❌ No pages crawled. Check the URL or network.")
        return

    build_sitemap(pages, args.output)

    print("─" * 50)
    print("🔎 Starting monitor...\n")
    monitor.run(sitemap_path=args.output, db_path="monitor.db")


if __name__ == "__main__":
    main()