"""
detect_dynamic.py
Fetches a URL twice and compares the parsed text to find which parts change
between requests. Helps identify dynamic content causing false hash changes.

Dependencies: requests, beautifulsoup4

Usage:
    python detect_dynamic.py "https://example.com/page"
    python detect_dynamic.py "https://example.com/page" --runs 3
"""

import argparse
import time
import requests
from bs4 import BeautifulSoup, Tag

HEADERS = {"User-Agent": "SitemapMonitor/1.0"}
TIMEOUT = 15


def fetch_and_parse(url: str) -> tuple[str, dict]:
    """Fetch URL and return (full_text, tag_texts dict keyed by tag identity)."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove scripts/styles like the monitor does
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    # Collect text per tag with a stable key: "tag_name[index]"
    tag_counts: dict[str, int] = {}
    tag_texts:  dict[str, str] = {}

    for tag in soup.find_all(True):
        name = tag.name
        tag_counts[name] = tag_counts.get(name, 0) + 1
        key = f"{name}[{tag_counts[name]}]"
        tag_texts[key] = tag.get_text(" ", strip=True)

    full_text = " ".join(soup.get_text().split())
    return full_text, tag_texts


def compare(url: str, runs: int) -> None:
    print(f"🔍 Fetching '{url}' {runs} times...\n")

    results = []
    for i in range(runs):
        print(f"  Fetch {i + 1}/{runs}...")
        text, tags = fetch_and_parse(url)
        results.append((text, tags))
        if i < runs - 1:
            time.sleep(1)  # polite delay

    # Compare full text hashes
    import hashlib
    hashes = [hashlib.sha256(r[0].encode()).hexdigest()[:16] for r in results]
    print(f"\n{'─' * 60}")
    print("FULL TEXT HASHES:")
    for i, h in enumerate(hashes):
        print(f"  Run {i+1}: {h}")

    all_same = len(set(hashes)) == 1
    print(f"  → {'✅ Stable' if all_same else '🔴 DYNAMIC — content changes between requests'}")

    if all_same:
        print("\n✅ Page appears stable. No dynamic text detected.")
        return

    # Find which tags differ between run 1 and run 2
    print(f"\n{'─' * 60}")
    print("CHANGED TAGS (Run 1 vs Run 2):\n")

    tags1 = results[0][1]
    tags2 = results[1][1]

    all_keys = set(tags1.keys()) | set(tags2.keys())
    changed = []

    for key in sorted(all_keys):
        t1 = tags1.get(key, "")
        t2 = tags2.get(key, "")
        if t1 != t2 and (t1.strip() or t2.strip()):
            changed.append((key, t1, t2))

    if not changed:
        print("  No individual tag differences found (may be whitespace-level change).")
    else:
        print(f"  Found {len(changed)} changed tag(s):\n")
        for key, t1, t2 in changed[:20]:  # show first 20
            print(f"  Tag: {key}")
            print(f"    Run 1: {t1[:120]!r}")
            print(f"    Run 2: {t2[:120]!r}")
            print()

    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more. Run with --runs flag to see all.\n")

    # Summary of likely dynamic elements
    print(f"{'─' * 60}")
    print("LIKELY DYNAMIC ELEMENTS:")
    dynamic_hints = []
    for key, t1, t2 in changed:
        tag_name = key.split("[")[0]
        if tag_name in ("time", "span", "div", "p", "a"):
            # Look for timestamps, counters, tokens
            for val in [t1, t2]:
                if any(word in val.lower() for word in ["ago", "just now", "minute", "second", "hour", "today"]):
                    dynamic_hints.append(f"  ⏱  Timestamp in <{tag_name}>: {val[:80]!r}")
                if any(c.isdigit() for c in val) and len(val) < 30:
                    dynamic_hints.append(f"  🔢 Counter/token in <{tag_name}>: {val[:80]!r}")

    if dynamic_hints:
        for h in dict.fromkeys(dynamic_hints):  # deduplicate
            print(h)
    else:
        print("  Could not auto-classify. Review the changed tags above manually.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect dynamic content in a webpage")
    parser.add_argument("url", help="URL to test")
    parser.add_argument("--runs", type=int, default=2,
                        help="Number of times to fetch the page (default: 2)")
    args = parser.parse_args()
    compare(args.url, args.runs)


if __name__ == "__main__":
    main()