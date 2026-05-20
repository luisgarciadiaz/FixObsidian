#!/usr/bin/env python3
"""Fix Obsidian MD Notes — repair and improve Vortexy-generated markdown notes.

Uses Postgres author_genre_map (enriched by tools/enrich_author_genres.py) for
genre routing. Falls back to title/category keyword matching.
"""

import os
import sys
import argparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.stdout.reconfigure(encoding='utf-8')

CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE_DIR)

from core.vortexy_config import load_config
from core.vortexy_obsidian import (
    sanitize_filename, make_obsidian_content, find_subfolder, DEFAULT_SUBFOLDER_MAP
)
from core.vortexy_parsers import (
    parse_frontmatter, extract_heading, extract_original_name, extract_series, is_vortexy_note
)
from core.vortexy_library import build_library_index
from core.vortexy_resolver import resolve_author_title
from core.vortexy_db import load_author_genre_map
from core.vortexy_enricher import MetadataEnricher


def fix_notes(vault_path, library_path, dry_run, limit, start_at, organize, cfg, enrich=True, clear_cache=False):
    if not os.path.exists(vault_path):
        print(f"Vault path not found: {vault_path}")
        sys.exit(1)

    all_items = sorted(f for f in os.listdir(vault_path) if f.endswith(".md") and not os.path.isdir(os.path.join(vault_path, f)))
    if not all_items:
        print("No .md files found in vault.")
        return

    print("Building library index (one-time walk)...")
    lib_index = build_library_index(library_path)
    print(f"Library index built: {len(lib_index)} files indexed.\n")
    author_genre_map = load_author_genre_map(cfg)
    if author_genre_map:
        print(f"Author-genre map loaded: {len(author_genre_map)} authors mapped.\n")

    subfolder_map = cfg.get("subfolder_map", DEFAULT_SUBFOLDER_MAP)

    enricher = None
    if enrich and cfg.get("isbn_enrichment", True):
        enricher = MetadataEnricher(subfolder_map, dry_run=dry_run)
        if clear_cache:
            enricher.clear_cache()
            print("Metadata cache cleared.\n")
        print(f"ISBN enrichment: {'cache-only (dry-run)' if dry_run else 'ENABLED'}\n")

    vault_subfolders = {}

    if organize:
        for item in os.listdir(vault_path):
            item_path = os.path.join(vault_path, item)
            if os.path.isdir(item_path):
                vault_subfolders[item] = item_path

    total = len(all_items)
    print(f"Found {total} .md files in vault.")
    if start_at:
        all_items = all_items[start_at:]
    if limit:
        all_items = all_items[:limit]
    if start_at or limit:
        start_msg = f"notes {start_at or 0}+" if start_at else f"first {limit}"
        print(f"Processing {start_msg}...")

    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE'}")
    if organize:
        print(f"Subfolder organization: ENABLED ({len(vault_subfolders)} folders found)")

    stats = {"fixed": 0, "renamed": 0, "moved": 0, "skipped": 0, "orphaned": 0, "created": 0}

    for idx, fname in enumerate(all_items):
        filepath = os.path.join(vault_path, fname)

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"  [{idx+1}] [!] Error reading {fname}: {e}")
            stats["skipped"] += 1
            continue

        if not is_vortexy_note(text):
            stats["orphaned"] += 1
            continue

        fm, body = parse_frontmatter(text)
        existing_author = fm.get("author", "").strip("[]").strip()
        existing_category = fm.get("category", "Uncategorized")
        existing_isbn = fm.get("isbn", "")
        existing_title = extract_heading(body) or ""
        existing_series = fm.get("series", "")
        existing_volume = fm.get("volume", "")
        existing_chapter = fm.get("chapter", "")
        original_name = extract_original_name(body) or ""

        author, title, file_uri, chapter = resolve_author_title(
            filepath, fm, body, existing_author, existing_title,
            lib_index, original_name
        )
        chapter = chapter or existing_chapter

        if author == "Unknown Auto" and not title:
            stats["skipped"] += 1
            continue

        enriched = {}
        if enricher:
            enriched = enricher.enrich(existing_isbn, title, author)

        correct_name = sanitize_filename(title if title.lower().startswith(author.lower()) else f"{author} - {title}")
        correct_filename = f"{correct_name}.md"

        target_subfolder = None
        if organize:
            author_key = author.lower().strip()
            db_subfolder = author_genre_map.get(author_key)
            enrich_sf = enriched.get("suggested_category", "")

            if db_subfolder and db_subfolder != "00 General Fiction":
                target_subfolder = db_subfolder
            elif enrich_sf and enrich_sf != "00 General Fiction":
                target_subfolder = enrich_sf
            else:
                genre_sf = find_subfolder(title, subfolder_map)
                if genre_sf and genre_sf != "00 General Fiction":
                    target_subfolder = genre_sf
                elif db_subfolder:
                    target_subfolder = db_subfolder
                else:
                    sf = find_subfolder(existing_category, subfolder_map)
                    if sf:
                        target_subfolder = sf

        target_dir = vault_path
        if target_subfolder:
            target_dir = os.path.join(vault_path, target_subfolder)
        target_path = os.path.join(target_dir, correct_filename)

        needs_rename = (os.path.normpath(filepath) != os.path.normpath(target_path))

        use_category = enriched.get("suggested_category") or existing_category
        publisher = enriched.get("publisher", "")
        publish_date = enriched.get("publish_date", "")
        synopsis = enriched.get("synopsis", "")

        new_content = make_obsidian_content(
            author=author, title=title, category=use_category,
            isbn=existing_isbn, original_name=original_name,
            file_uri=file_uri, series=existing_series, volume=existing_volume,
            chapter=chapter, publisher=publisher, publish_date=publish_date,
            synopsis=synopsis
        )

        if dry_run:
            msg = f"  [{idx+1}] {fname}"
            if needs_rename:
                sub_info = f" [{target_subfolder}/]" if target_subfolder else ""
                msg += f"\n          -> {sub_info}{correct_filename}"
            msg += " (rewrite content)"
            if author == "Unknown Auto":
                msg += " [author: Unknown Auto]"
            print(msg)
            stats["fixed"] += 1
            continue

        try:
            if target_subfolder:
                os.makedirs(target_dir, exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            if needs_rename and os.path.normpath(filepath) != os.path.normpath(target_path):
                if os.path.exists(filepath):
                    os.remove(filepath)
                stats["renamed"] += 1
                sub_info = f" [{target_subfolder}/]" if target_subfolder else ""
                print(f"  [{idx+1}] {fname} ->{sub_info}{correct_filename}")
            else:
                print(f"  [{idx+1}] {fname} (rewritten)")

            stats["fixed"] += 1
            if target_subfolder and os.path.dirname(filepath) != target_dir:
                stats["moved"] += 1

        except Exception as e:
            print(f"  [{idx+1}] [!] Error writing {correct_filename}: {e}")
            stats["skipped"] += 1

    print("\n" + "=" * 50)
    print(f"  Fixed:     {stats['fixed']}")
    print(f"  Renamed:   {stats['renamed']}")
    print(f"  Moved:     {stats['moved']}")
    print(f"  Created:   {stats['created']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Orphaned:  {stats['orphaned']} (non-Vortexy notes)")
    print("=" * 50)


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Fix Obsidian MD Notes from Vortexy")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N notes")
    parser.add_argument("--start-at", type=int, default=0, help="Skip first N notes before processing")
    parser.add_argument("--vault", default=cfg.get("vault_path", ""), help="Obsidian vault path")
    parser.add_argument("--library", default=cfg.get("library_path", ""), help="PDF library path")
    parser.add_argument("--organize", action="store_true", default=cfg.get("organize", True), help="Move notes into subfolders by category")
    parser.add_argument("--no-organize", action="store_false", dest="organize", help="Don't move notes into subfolders")
    parser.add_argument("--enrich", action="store_true", default=True, help="Fetch book metadata from Open Library API (default)")
    parser.add_argument("--no-enrich", action="store_false", dest="enrich", help="Disable metadata enrichment")
    parser.add_argument("--clear-cache", action="store_true", default=False, help="Clear metadata cache before processing")
    args = parser.parse_args()
    fix_notes(args.vault, args.library, args.dry_run, args.limit, args.start_at, args.organize, cfg, enrich=args.enrich, clear_cache=args.clear_cache)
