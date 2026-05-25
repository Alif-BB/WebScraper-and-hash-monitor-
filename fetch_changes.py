"""
fetch_changes.py
Downloads the current HTML content of changed pages from the changes table
and stores it in a new `html` column in the same table.
Only fetches changes from the most recent run.

Dependencies: requests

Usage:
    python fetch_changes.py
    python fetch_changes.py --db custom.db
"""

import argparse
import sqlite3
import time
import requests
from urllib.parse import urlparse
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_DB      = "monitor.db"
REQUEST_TIMEOUT = 15
HEADERS         = {"User-Agent": "SitemapMonitor/1.0"}


# ── Database ──────────────────────────────────────────────────────────────────

def get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)

    # Add html column to changes table if it doesn't exist yet
    existing = [
        row[1]
        for row in conn.execute("PRAGMA table_info(changes)").fetchall()
    ]
    if "html" not in existing:
        conn.execute("ALTER TABLE changes ADD COLUMN html TEXT")
        conn.commit()
        print("✅ Added 'html' column to changes table.\n")

    return conn


# ── Fetcher ───────────────────────────────────────────────────────────────────

# ── Per-domain rate limiter ───────────────────────────────────────────────────

_last_req: dict[str, float] = defaultdict(float)
DELAY = 1.0  # seconds between requests to same domain

def _wait(url: str) -> None:
    domain  = urlparse(url).netloc
    elapsed = time.monotonic() - _last_req[domain]
    wait_for = DELAY - elapsed
    if wait_for > 0:
        time.sleep(wait_for)
    _last_req[domain] = time.monotonic()


def fetch_html(url: str) -> str | None:
    _wait(url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return resp.text
    except Exception as e:
        print(f"  ⚠  Fetch error  {url}  ({e})")
        return None


# ── Core logic ────────────────────────────────────────────────────────────────

def run(db_path: str) -> None:
    conn = get_db(db_path)

    # Get the most recent detected_at timestamp
    latest = conn.execute(
        "SELECT MAX(detected_at) FROM changes"
    ).fetchone()[0]

    if not latest:
        print("✅ No changes in database.")
        conn.close()
        return

    # Only fetch changes from the most recent run that don't have html yet
    rows = conn.execute(
        "SELECT id, url FROM changes WHERE detected_at = ? AND html IS NULL",
        (latest,)
    ).fetchall()

    if not rows:
        print("✅ No pending changes to fetch HTML for.")
        conn.close()
        return

    print(f"🔍 Fetching HTML for {len(rows)} changed page(s) from latest run ({latest})...\n")

    success = 0
    errors  = 0

    for change_id, url in rows:
        html = fetch_html(url)

        if html is None:
            errors += 1
            continue

        conn.execute(
            "UPDATE changes SET html = ? WHERE id = ?",
            (html, change_id),
        )
        conn.commit()
        print(f"  ✅ Saved  {url}  ({len(html):,} chars)")
        success += 1

    conn.close()

    print(f"""
{'─' * 50}
  Saved   : {success}
  Errors  : {errors}
  DB      : {db_path}
{'─' * 50}
""")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download HTML for changed pages and store in changes table"
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB})"
    )
    args = parser.parse_args()

    run(args.db)


if __name__ == "__main__":
    main()