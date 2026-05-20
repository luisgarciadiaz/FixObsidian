#!/usr/bin/env python3
"""Fix Obsidian MD Notes — repair and improve Vortexy-generated markdown notes.

Uses Postgres author_genre_map (enriched by tools/enrich_author_genres.py) for
genre routing. Falls back to title/category keyword matching.
"""

import os
import sys
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE_DIR)

from core.vortexy_config import load_config
from core.vortexy_obsidian import (
    sanitize_filename, make_obsidian_content, find_subfolder, DEFAULT_SUBFOLDER_MAP
)
from core.vortexy_parsers import (
    parse_frontmatter, extract_heading, extract_original_name, extract_series
)
from core.vortexy_library import build_library_index
from core.vortexy_resolver import resolve_author_title
from core.vortexy_db import load_author_genre_map
from core.vortexy_enricher import MetadataEnricher


def fix_notes(vault_path, library_path, dry_run, limit, start_at, organize, cfg, enrich=True, clear_cache=False):
    t0 = time.time()
    print(f"=== FixObsidian starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} ===")
    print(f"    Vault: {vault_path}")
    if library_path:
        print(f"    Library: {library_path}")
    print()

    if not os.path.exists(vault_path):
        print(f"Vault path not found: {vault_path}")
        sys.exit(1)

    import itertools

    t1 = time.time()
    md_entries = (e.name for e in os.scandir(vault_path) if e.name.endswith(".md") and not e.is_dir())
    if start_at:
        md_entries = itertools.islice(md_entries, start_at, None)
    all_items = sorted(itertools.islice(md_entries, limit or None))
    if not all_items:
        print("No .md files found in vault.")
        return
    print(f"[{(time.time()-t1):.1f}s] Vault scan: {len(all_items)} .md files queued.")

    t1 = time.time()
    print("Building library index...")
    lib_index = build_library_index(library_path)
    print(f"[{(time.time()-t1):.1f}s] Library index: {len(lib_index)} files.")

    t1 = time.time()
    author_genre_map = load_author_genre_map(cfg)
    if author_genre_map:
        print(f"[{(time.time()-t1):.1f}s] Author-genre map: {len(author_genre_map)} authors.")

    subfolder_map = cfg.get("subfolder_map", DEFAULT_SUBFOLDER_MAP)

    t1 = time.time()
    enricher = None
    if enrich and cfg.get("isbn_enrichment", True):
        enricher = MetadataEnricher(subfolder_map, dry_run=dry_run)
        if clear_cache:
            enricher.clear_cache()
            print("Metadata cache cleared.")
        print(f"[{(time.time()-t1):.1f}s] Enrichment: {'cache-only (dry-run)' if dry_run else 'ENABLED'}")
    print()

    BATCH = 100
    total = len(all_items)
    batch_count = (total + BATCH - 1) // BATCH
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'} | Organize: {'ON' if organize else 'OFF'} | Total: {total} notes in {batch_count} batches of {BATCH}")
    print()

    stats = {"fixed": 0, "renamed": 0, "moved": 0, "skipped": 0, "created": 0}

    for batch_idx in range(batch_count):
        batch_items = all_items[batch_idx * BATCH : (batch_idx + 1) * BATCH]
        b_start = batch_idx * BATCH + 1 + (start_at or 0)
        b_end = b_start + len(batch_items) - 1
        t_batch = time.time()
        batch_fixed = 0

        for idx, fname in enumerate(batch_items):
            filepath = os.path.join(vault_path, fname)
            global_idx = batch_idx * BATCH + idx + 1

            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception as e:
                print(f"  [{global_idx}] [!] Error reading {fname}: {e}")
                stats["skipped"] += 1
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

            author, title, file_uri, chapter, bracket_year = resolve_author_title(
                filepath, fm, body, existing_author, existing_title,
                lib_index, original_name
            )
            chapter = chapter or existing_chapter

            if author == "Unknown Author" and not title:
                stats["skipped"] += 1
                continue

            enriched = {}
            if enricher and (existing_isbn or author != "Unknown Author"):
                enriched = enricher.enrich(existing_isbn, title, author, year=bracket_year)

            correct_name = sanitize_filename(title if title.lower().startswith(author.lower()) else f"{author} - {title}")
            correct_filename = f"{correct_name}.md"

            target_subfolder = None
            if organize:
                valid_folders = set(subfolder_map.keys())
                author_key = author.lower().strip()
                db_subfolder = author_genre_map.get(author_key)
                enrich_sf = enriched.get("suggested_category", "")

                if db_subfolder and db_subfolder != "00 General Fiction" and db_subfolder in valid_folders:
                    target_subfolder = db_subfolder
                elif enrich_sf and enrich_sf != "00 General Fiction" and enrich_sf in valid_folders:
                    target_subfolder = enrich_sf
                else:
                    genre_sf = find_subfolder(title, subfolder_map)
                    if genre_sf and genre_sf != "00 General Fiction":
                        target_subfolder = genre_sf
                    elif db_subfolder and db_subfolder in valid_folders:
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
            publish_date = enriched.get("publish_date", "") or bracket_year or ""
            synopsis = enriched.get("synopsis", "")

            new_content = make_obsidian_content(
                author=author, title=title, category=use_category,
                isbn=existing_isbn, original_name=original_name,
                file_uri=file_uri, series=existing_series, volume=existing_volume,
                chapter=chapter, publisher=publisher, publish_date=publish_date,
                synopsis=synopsis
            )

            if dry_run:
                ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                msg = f"  {ts} [{global_idx}] {fname}"
                if needs_rename:
                    sub_info = f" [{target_subfolder}/]" if target_subfolder else ""
                    msg += f"\n          -> {sub_info}{correct_filename}"
                msg += " (rewrite content)"
                if author == "Unknown Author":
                    msg += " [author: Unknown Author]"
                print(msg)
                stats["fixed"] += 1
                batch_fixed += 1
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
                    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    print(f"  {ts} [{global_idx}] {fname} ->{sub_info}{correct_filename}")
                else:
                    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    print(f"  {ts} [{global_idx}] {fname} (rewritten)")

                stats["fixed"] += 1
                batch_fixed += 1
                if target_subfolder and os.path.dirname(filepath) != target_dir:
                    stats["moved"] += 1

            except Exception as e:
                print(f"  [{global_idx}] [!] Error writing {correct_filename}: {e}")
                stats["skipped"] += 1

        print(f"  Batch {batch_idx+1}/{batch_count} ({b_start}-{b_end}): {batch_fixed} fixed, {(time.time()-t_batch):.1f}s, running total: {stats['fixed']} fixed")

    if enricher:
        enricher.flush()

    print("\n" + "=" * 50)
    print(f"  Fixed:     {stats['fixed']}")
    print(f"  Renamed:   {stats['renamed']}")
    print(f"  Moved:     {stats['moved']}")
    print(f"  Created:   {stats['created']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Total time: {(time.time()-t0):.1f}s")
    print("=" * 50)


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Fix Obsidian MD Notes from Vortexy")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--limit", type=int, default=0, help="Process only N notes (default: process all in batches of 100)")
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
