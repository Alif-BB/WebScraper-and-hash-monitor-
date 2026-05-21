"""
monitor.py
Hashes each page from sitemap.xml and stores/compares in SQLite.

Dependencies: none (stdlib only — sqlite3, hashlib, urllib)

Usage:
    python monitor.py                          # first run: snapshot all pages
    python monitor.py                          # later runs: detect changes
    python monitor.py --report                 # view database contents
    python monitor.py --db custom.db
    python monitor.py --sitemap my-sitemap.xml
"""

import argparse
import hashlib
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_DB      = "monitor.db"
DEFAULT_SITEMAP = "sitemap.xml"
SITEMAP_NS      = "http://www.sitemaps.org/schemas/sitemap/0.9"
REQUEST_TIMEOUT = 10
HEADERS         = {"User-Agent": "SitemapMonitor/1.0"}


# ── Database ──────────────────────────────────────────────────────────────────

def get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            url         TEXT PRIMARY KEY,
            hash        TEXT NOT NULL,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            last_change TEXT,
            check_count INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL,
            old_hash    TEXT NOT NULL,
            new_hash    TEXT NOT NULL,
            detected_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


# ── Hashing ───────────────────────────────────────────────────────────────────

def fetch_and_hash(url: str) -> str | None:
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            content = resp.read()

        # Parse and extract stable content only
        soup = BeautifulSoup(content, "html.parser")

        # Remove known dynamic elements
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()

        # Get normalized text (strips whitespace differences too)
        text = " ".join(soup.get_text().split())

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    except URLError as e:
        print(f"  ⚠  Fetch error  {url}  ({e.reason})")
        return None


# ── Sitemap reader ────────────────────────────────────────────────────────────

def read_urls(sitemap_path: str) -> list[str]:
    tree = ET.parse(sitemap_path)
    root = tree.getroot()
    # handle both namespaced and plain <loc> tags
    urls = [el.text.strip() for el in root.findall(f".//{{{SITEMAP_NS}}}loc") if el.text]
    if not urls:
        urls = [el.text.strip() for el in root.findall(".//loc") if el.text]
    return urls


# ── Core logic ────────────────────────────────────────────────────────────────

def run(sitemap_path: str, db_path: str) -> None:
    urls = read_urls(sitemap_path)
    if not urls:
        print("❌ No URLs found in sitemap.")
        return

    conn = get_db(db_path)
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_count     = 0
    changed_count = 0
    unchanged     = 0
    error_count   = 0

    print(f"🔍 Checking {len(urls)} URLs from {sitemap_path}\n")

    for url in urls:
        new_hash = fetch_and_hash(url)

        if new_hash is None:
            error_count += 1
            continue

        row = conn.execute(
            "SELECT hash FROM pages WHERE url = ?", (url,)
        ).fetchone()

        if row is None:
            conn.execute(
                """INSERT INTO pages
                   (url, hash, first_seen, last_seen, last_change, check_count)
                   VALUES (?, ?, ?, ?, NULL, 1)""",
                (url, new_hash, now, now),
            )
            print(f"  ➕ New      {url}")
            new_count += 1

        elif row[0] != new_hash:
            old_hash = row[0]
            conn.execute(
                """INSERT INTO changes (url, old_hash, new_hash, detected_at)
                   VALUES (?, ?, ?, ?)""",
                (url, old_hash, new_hash, now),
            )
            conn.execute(
                """UPDATE pages
                   SET hash = ?, last_seen = ?, last_change = ?,
                       check_count = check_count + 1
                   WHERE url = ?""",
                (new_hash, now, now, url),
            )
            print(f"  🔴 Changed  {url}")
            print(f"             old: {old_hash[:16]}...")
            print(f"             new: {new_hash[:16]}...")
            changed_count += 1

        else:
            conn.execute(
                """UPDATE pages
                   SET last_seen = ?, check_count = check_count + 1
                   WHERE url = ?""",
                (now, url),
            )
            print(f"  ✅ OK       {url}")
            unchanged += 1

    conn.commit()
    conn.close()

    print(f"""
{'─' * 50}
  New pages   : {new_count}
  Changed     : {changed_count}
  Unchanged   : {unchanged}
  Errors      : {error_count}
  DB          : {db_path}
{'─' * 50}
""")

    if changed_count:
        print(f"⚠️  {changed_count} page(s) changed since last run.")
    else:
        print("✅ No changes detected.")


# ── Report ────────────────────────────────────────────────────────────────────

def report(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    pages   = conn.execute("SELECT * FROM pages ORDER BY last_seen DESC").fetchall()
    changes = conn.execute("SELECT * FROM changes ORDER BY detected_at DESC").fetchall()
    conn.close()

    print(f"\n{'─' * 70}")
    print(f"  PAGES ({len(pages)} total)")
    print(f"{'─' * 70}")
    for p in pages:
        status = "🔴 changed" if p["last_change"] else "✅ ok"
        print(f"  {status}  [{p['check_count']}x]  {p['url']}")
        print(f"          hash      : {p['hash'][:24]}...")
        print(f"          first seen: {p['first_seen']}")
        print(f"          last seen : {p['last_seen']}")
        if p["last_change"]:
            print(f"          changed at: {p['last_change']}")
        print()

    print(f"{'─' * 70}")
    print(f"  CHANGE LOG ({len(changes)} total)")
    print(f"{'─' * 70}")
    if not changes:
        print("  No changes recorded yet.\n")
    for c in changes:
        print(f"  🔴 {c['detected_at']}  {c['url']}")
        print(f"     old: {c['old_hash'][:24]}...")
        print(f"     new: {c['new_hash'][:24]}...")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor webpage changes via hashing")
    parser.add_argument("--sitemap", default=DEFAULT_SITEMAP,
                        help=f"Sitemap XML path (default: {DEFAULT_SITEMAP})")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help=f"SQLite database path (default: {DEFAULT_DB})")
    parser.add_argument("--report", action="store_true",
                        help="Print a summary of the database without crawling")
    args = parser.parse_args()

    if args.report:
        report(args.db)
    else:
        run(args.sitemap, args.db)


if __name__ == "__main__":
    main()