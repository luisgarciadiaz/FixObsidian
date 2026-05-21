"""Vault statistics collector — scans vault and prints a summary dashboard."""

import json
import os
import sys
import time
from collections import defaultdict

CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE_DIR)

from core.vortexy_parsers import parse_frontmatter, extract_heading
from core.vortexy_obsidian import DEFAULT_SUBFOLDER_MAP


def collect_stats(vault_path, limit=None, start_at=None):
    if not os.path.exists(vault_path):
        return {"error": f"Vault path not found: {vault_path}"}

    md_entries = [e.name for e in os.scandir(vault_path) if e.name.endswith(".md") and not e.is_dir()]
    if start_at:
        md_entries = md_entries[start_at:]
    if limit:
        md_entries = md_entries[:limit]
    total = len(md_entries)

    categories = {}
    authors = {}
    no_author = 0
    no_isbn = 0
    no_title = 0
    no_category = 0
    would_skip = 0

    subfolder_counts = {}
    from core.vortexy_obsidian import DEFAULT_SUBFOLDER_MAP
    for folder in DEFAULT_SUBFOLDER_MAP:
        sf_path = os.path.join(vault_path, folder)
        if os.path.isdir(sf_path):
            subfolder_counts[folder] = sum(1 for e in os.scandir(sf_path) if e.name.endswith(".md"))
        else:
            subfolder_counts[folder] = 0

    for fname in md_entries:
        filepath = os.path.join(vault_path, fname)
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        fm, body = parse_frontmatter(text)
        existing_author = fm.get("author", "").strip("[]").strip()
        existing_category = fm.get("category", "Uncategorized")
        existing_isbn = fm.get("isbn", "").strip()
        existing_title = extract_heading(body) or ""

        cat = existing_category or "Uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
        if not existing_category or existing_category == "Uncategorized":
            no_category += 1

        author_key = existing_author.lower() if existing_author else "unknown"
        if author_key in ("", "unknown", "unknown author", "unknown auto"):
            no_author += 1
            author_key = "unknown"
        authors[author_key] = authors.get(author_key, 0) + 1

        if not existing_isbn:
            no_isbn += 1
        if not existing_title:
            no_title += 1
        if (not existing_author or author_key == "unknown") and not existing_title:
            would_skip += 1

    top_authors = sorted(authors.items(), key=lambda x: -x[1])[:10]

    cache_path = os.path.join(CORE_DIR, "data", "metadata_cache.json")
    cache_stats = None
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        cache_stats = {
            "entries": len(cache),
            "empty": sum(1 for v in cache.values() if not v or v == {}),
            "size_kb": os.path.getsize(cache_path) / 1024,
        }

    return {
        "total": total,
        "categories": categories,
        "authors": authors,
        "top_authors": top_authors,
        "no_author": no_author,
        "no_isbn": no_isbn,
        "no_title": no_title,
        "no_category": no_category,
        "would_skip": would_skip,
        "subfolder_counts": subfolder_counts,
        "cache_stats": cache_stats,
        "sample_size": f"{start_at or 0}-{start_at + total if start_at else total}",
    }


def run_stats_only(vault_path, cfg=None, limit=None, start_at=None):
    t0 = time.time()
    result = collect_stats(vault_path, limit=limit, start_at=start_at)
    if "error" in result:
        print(result["error"])
        sys.exit(1)

    print(f"=== FixObsidian STATS-ONLY ===")
    print(f"    Vault: {vault_path}")
    print()

    print(f"   Scanned: {result['sample_size']} of {result['total']} .md files")
    print()

    print("=== Subfolder Distribution ===")
    for folder in sorted(result["subfolder_counts"].keys()):
        print(f"  {folder}: {result['subfolder_counts'][folder]}")

    print()
    print("=== Category Frontmatter ===")
    for cat, cnt in sorted(result["categories"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")

    print()
    print("=== Health Metrics ===")
    print(f"  Total notes scanned:   {result['total']}")
    print(f"  No author:             {result['no_author']}")
    print(f"  No ISBN:               {result['no_isbn']}")
    print(f"  No title heading:      {result['no_title']}")
    print(f"  No category:           {result['no_category']}")
    print(f"  Would be skipped:      {result['would_skip']}")

    print()
    print("=== Top 10 Authors ===")
    for author_name, cnt in result["top_authors"]:
        print(f"  {author_name}: {cnt}")

    cs = result["cache_stats"]
    if cs:
        print()
        print("=== Metadata Cache ===")
        print(f"  Total entries: {cs['entries']}")
        print(f"  Empty entries: {cs['empty']}")
        print(f"  Cache size:    {cs['size_kb']:.1f} KB")

    print(f"\n  Time: {(time.time()-t0):.1f}s")
    print("=" * 50)
