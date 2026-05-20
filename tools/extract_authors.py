#!/usr/bin/env python3
"""
Extract unique resolved authors from the vault to help seed author_genre_map.json.
Outputs authors sorted by frequency, with their current category routing.
"""
import os, sys, json, argparse

CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE_DIR)

# Local copy of parse_frontmatter (same as fix_obsidian_notes.py)
def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw = parts[1]
    body = parts[2]
    fm = {}
    for line in raw.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            fm[key] = val
    return fm, body

CONFIG_PATH = os.path.join(CORE_DIR, "config.json")
MAP_PATH = os.path.join(CORE_DIR, "data", "author_genre_map.json")


def main():
    if not os.path.exists(CONFIG_PATH):
        print("config.json not found")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    vault_path = cfg.get("vault_path", "")
    if not os.path.exists(vault_path):
        print(f"Vault not found: {vault_path}")
        sys.exit(1)

    # Load existing map
    existing_map = {}
    if os.path.exists(MAP_PATH):
        with open(MAP_PATH, "r", encoding="utf-8") as f:
            existing_map = json.load(f).get("authors", {})

    author_counts = {}
    author_categories = {}

    for fname in os.listdir(vault_path):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(vault_path, fname)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue

        fm, _ = parse_frontmatter(text)
        author = fm.get("author", "").strip("[]").strip()
        category = fm.get("category", "").strip()
        if not author or author.lower() in ("unknown", "desconocido", "unknown auto", ""):
            continue

        author_counts[author] = author_counts.get(author, 0) + 1
        if author not in author_categories:
            author_categories[author] = category

    print(f"Unique resolved authors: {len(author_counts)}")
    print(f"Already mapped: {len(existing_map)}")
    print()

    unmapped = {a: c for a, c in author_counts.items() if a not in existing_map}
    print(f"Unmapped authors: {len(unmapped)}")
    print()

    print("Top 50 unmapped authors (by count):")
    for author, count in sorted(unmapped.items(), key=lambda x: -x[1])[:50]:
        cat = author_categories.get(author, "?")
        print(f"  {count:>5}  {author:<40}  [{cat}]")

    print()
    print("To add an author to the map, edit data/author_genre_map.json and add:")
    print('  "author name": "Subfolder Name"')
    print(f"Available subfolders: {', '.join(cfg.get('subfolder_map', {}).keys())}")


if __name__ == "__main__":
    main()
