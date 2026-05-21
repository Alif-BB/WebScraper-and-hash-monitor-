"""
sitemap_bfs_parser.py
Reads sitemap.xml and prints pages as a BFS tree using parent-child relationships.

Usage:
    python sitemap_bfs_parser.py
    python sitemap_bfs_parser.py --sitemap my-sitemap.xml
"""

import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def parse_bfs_tree(xml_file: str) -> None:
    try:
        tree = ET.parse(xml_file)
    except FileNotFoundError:
        print(f"❌ Error: '{xml_file}' not found.")
        return

    root = tree.getroot()

    # Build parent → children map
    children: dict[str | None, list[str]] = defaultdict(list)

    for url_el in root.findall(f"{{{SITEMAP_NS}}}url"):
        loc_el = url_el.find(f"{{{SITEMAP_NS}}}loc")
        parent_el = url_el.find(f"{{{SITEMAP_NS}}}parent")

        if loc_el is None or loc_el.text is None:
            continue

        loc = loc_el.text.strip()
        parent = parent_el.text.strip() if parent_el is not None and parent_el.text and parent_el.text.strip() else None

        children[parent].append(loc)

    if not children:
        print("❌ No URLs found. Make sure the sitemap was generated with the updated sitemap_generator.py.")
        return

    # ── Tree printer ──────────────────────────────────────────────────────────

    def print_tree(url: str, indent: str = "", is_last: bool = True) -> None:
        connector = "└── " if is_last else "├── "
        kids = children.get(url, [])
        has_children = len(kids) > 0
        suffix = f"  ({len(kids)} links)" if has_children else ""
        print(f"{indent}{connector}{url}{suffix}")

        new_indent = indent + ("    " if is_last else "│   ")
        for i, child in enumerate(kids):
            print_tree(child, new_indent, is_last=(i == len(kids) - 1))

    # ── Print roots (pages with no parent) ───────────────────────────────────

    roots = children.get(None, [])

    if not roots:
        print("❌ No root pages found.")
        return

    total = sum(len(v) for v in children.values())
    print(f"🌐 BFS Site Tree — {total} pages\n")

    for i, root_url in enumerate(roots):
        is_last = (i == len(roots) - 1)
        connector = "└── " if is_last else "├── "
        kids = children.get(root_url, [])
        suffix = f"  ({len(kids)} links)" if kids else ""
        print(f"{connector}{root_url}{suffix}")

        new_indent = "    " if is_last else "│   "
        for j, child in enumerate(kids):
            print_tree(child, new_indent, is_last=(j == len(kids) - 1))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Print sitemap as a BFS tree")
    parser.add_argument(
        "--sitemap", "-s",
        default="sitemap.xml",
        help="Path to sitemap XML file (default: sitemap.xml)",
    )
    args = parser.parse_args()

    print(f"📄 Parsing {args.sitemap}...\n")
    parse_bfs_tree(args.sitemap)


if __name__ == "__main__":
    main()