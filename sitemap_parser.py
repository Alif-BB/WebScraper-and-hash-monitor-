
"""
sitemap_bfs_parser.py
Reads sitemap.xml and prints pages as a BFS tree using parent-child relationships.
Uses an iterative stack instead of recursion to handle deep trees without hitting
Python's recursion limit.
 
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
        loc_el    = url_el.find(f"{{{SITEMAP_NS}}}loc")
        parent_el = url_el.find(f"{{{SITEMAP_NS}}}parent")
 
        if loc_el is None or loc_el.text is None:
            continue
 
        loc    = loc_el.text.strip()
        parent = (
            parent_el.text.strip()
            if parent_el is not None and parent_el.text and parent_el.text.strip()
            else None
        )
        children[parent].append(loc)
 
    if not children:
        print("❌ No URLs found. Make sure the sitemap was generated with the updated sitemap_generator.py.")
        return
 
    roots = children.get(None, [])
    if not roots:
        print("❌ No root pages found.")
        return
 
    total = sum(len(v) for v in children.values())
    print(f"🌐 BFS Site Tree — {total} pages\n")
 
    # ── Iterative tree printer (no recursion) ─────────────────────────────────
    # Stack stores: (url, indent, is_last, seen_set)
    # seen_set tracks visited URLs per path to detect cycles
    seen_globally: set[str] = set()
 
    # Push roots onto stack in reverse order so first root prints first
    stack = []
    for i, root_url in enumerate(reversed(roots)):
        is_last = (i == 0)  # reversed, so index 0 = last original
        stack.append((root_url, "", is_last))
 
    while stack:
        url, indent, is_last = stack.pop()
 
        if url in seen_globally:
            connector = "└── " if is_last else "├── "
            print(f"{indent}{connector}{url}  ⚠ (cycle detected, skipping)")
            continue
        seen_globally.add(url)
 
        kids      = children.get(url, [])
        connector = "└── " if is_last else "├── "
        suffix    = f"  ({len(kids)} links)" if kids else ""
        print(f"{indent}{connector}{url}{suffix}")
 
        new_indent = indent + ("    " if is_last else "│   ")
 
        # Push children in reverse so they print in correct order
        for i, child in enumerate(reversed(kids)):
            child_is_last = (i == 0)  # reversed, so index 0 = last original
            stack.append((child, new_indent, child_is_last))
 
 
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