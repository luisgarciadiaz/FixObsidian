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
import urllib.parse
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


def consolidate_tracks(vault_path, dry_run=False):
    """Merge audiobook track notes and multipart section notes into single per-book notes."""
    import re
    from pathlib import Path

    TRACK_RE = re.compile(r'^(.+?)\s*-\s*Disc\s+(\d+)\s+Track\s+(\d+)', re.IGNORECASE)
    SECTION_RE = re.compile(r'^(.+)\s+(\d{2,})$')
    groups = {}  # key -> {'tracks': [(path, disc, track)], 'sections': [(path, section_num)]}

    def book_author_key(name):
        """Return (book_key, kind, a, b) or (None, None, None, None) for no match."""
        stem = Path(name).stem
        m = TRACK_RE.match(stem)
        if m:
            key = m.group(1).strip()
            key = re.sub(r'\s+CD\d+$', '', key, flags=re.IGNORECASE).strip()
            return key, 'track', int(m.group(2)), int(m.group(3))
        m = SECTION_RE.match(stem)
        if m:
            base = m.group(1).strip()
            sec = int(m.group(2))
            if sec < 100:
                base = re.sub(r'\s+CD\d+$', '', base, flags=re.IGNORECASE).strip()
                return base, 'section', sec, None
        return None, None, None, None

    for entry in os.scandir(vault_path):
        if not entry.is_file() or not entry.name.endswith('.md'):
            continue
        key, kind, a, b = book_author_key(entry.name)
        if not key:
            continue
        if key not in groups:
            groups[key] = {'tracks': [], 'sections': [], 'author': None}
        if kind == 'track':
            groups[key]['tracks'].append((entry.path, a, b))
        else:
            groups[key]['sections'].append((entry.path, a))

    if not groups:
        print("   No track/section notes found to consolidate.")
        return 0

    count = 0
    for book_key, data in groups.items():
        all_items = data['tracks'] + [(p, None, None) for p, _ in data['sections']]
        if len(all_items) < 2:
            continue

        book_author = data['author']
        base_key = book_key

        sep = ' - '
        if sep in book_key:
            parts = book_key.split(sep, 1)
            candidate = parts[0].strip()
            if len(candidate.split()) <= 6 and not candidate[0].isdigit():
                book_author = book_author or candidate
                book_key = parts[1].strip()

        for filepath, _, _ in all_items:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue
            from core.vortexy_parsers import parse_frontmatter
            fm, _ = parse_frontmatter(content)
            fm_author = fm.get("author", "").strip("[]").strip()
            if fm_author and fm_author.lower() not in ("unknown", "unknown author", "unknown auto", base_key.lower()):
                book_author = fm_author

        if not book_author or not book_key or book_key.strip() in ('', '-', '.') or len(book_key.strip()) < 3:
            continue
        book_key = book_key.strip().rstrip('-').strip()
        if len(book_key) < 3 or re.match(r'^\d', book_key):
            continue
        if re.match(r'^[A-Za-z]\d?$', book_key):
            continue
        if book_key.lower() in ('track', 'chapter', 'page', 'section', 'capitulo', 'capítulo'):
            continue
        if ' - ' in book_key:
            parts = book_key.split(' - ')
            if len(parts) >= 2 and parts[0].strip().lower() == parts[-1].strip().lower():
                continue

        from core.vortexy_obsidian import sanitize_filename, make_category_tag, slugify_category
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cat = "00 General Fiction"

        lines = []
        lines.append("---")
        lines.append(f'title: "{book_key}"')
        lines.append(f'author: "[[{book_author}]]"')
        lines.append(f"category: {cat}")
        lines.append(f"tags: [vortexy, {slugify_category(cat)}]")
        lines.append('isbn: ""')
        lines.append(f"date_organized: {date_str}")
        lines.append("vortexy_version: v1.5.0")
        lines.append("---")
        lines.append("")
        lines.append(f"# {book_key}")
        lines.append("")
        lines.append(f"- **Author:** [[{book_author}]]")
        lines.append(f"- **Category:** {make_category_tag(cat)}")
        lines.append("")

        tracks_by_disc = {}
        for filepath, disc, tracknum in data['tracks']:
            if disc not in tracks_by_disc:
                tracks_by_disc[disc] = []
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue
            link_m = re.search(r'\[Open Local File\]\(([^)]+)\)', content)
            orig_m = re.search(r'Original Name:\*\*\s*`([^`]+)`', content)
            tracks_by_disc[disc].append((tracknum, link_m.group(1) if link_m else "", orig_m.group(1) if orig_m else ""))

        sections = []
        for filepath, secnum in data['sections']:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue
            link_m = re.search(r'\[Open Local File\]\(([^)]+)\)', content)
            orig_m = re.search(r'Original Name:\*\*\s*`([^`]+)`', content)
            sections.append((secnum, link_m.group(1) if link_m else "", orig_m.group(1) if orig_m else ""))

        if tracks_by_disc:
            for disc in sorted(tracks_by_disc.keys()):
                lines.append(f"> [!abstract] Disc {disc}")
                for tracknum, link, orig in sorted(tracks_by_disc[disc]):
                    label = orig or f"Disc {disc} Track {tracknum:02d}"
                    lines.append(f"> - Track {tracknum:02d} — [{label}]({link})")
                lines.append("")

        if sections:
            sections.sort()
            lines.append("> [!abstract] Sections")
            for secnum, link, orig in sections:
                label = orig or f"Section {secnum:02d}"
                lines.append(f"> - {secnum:02d} — [{label}]({link})")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by Vortexy Graph Architect*")

        new_content = "\n".join(lines) + "\n"
        correct_name = sanitize_filename(f"{book_author} - {book_key}")
        target_path = os.path.join(vault_path, f"{correct_name}.md")

        if dry_run:
            print(f"   [consolidate] Would create: {correct_name}.md ({len(all_items)} parts)")
            count += 1
            continue

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        for filepath, _, _ in all_items:
            try:
                os.remove(filepath)
            except Exception:
                pass

        print(f"   [consolidate] {book_author} - {book_key} ({len(all_items)} parts)")
        count += 1

    return count


def merge_extension_duplicates(vault_path, dry_run=False):
    """Merge duplicate files where one has an embedded file extension (e.g. .txt.md).
    Collects all unique file links from both and writes a single merged note."""
    import re
    from collections import defaultdict

    EXT_PATTERN = re.compile(r'^(.*)\.(txt|epub|mobi|azw3|pdf|djvu|mp3|m4a|wma|wav|flac|ogg)\.md$', re.IGNORECASE)
    LINK_RE = re.compile(r'\[Open Local File\]\(([^)]+)\)')

    entries = {}
    for entry in os.scandir(vault_path):
        if not entry.is_file() or not entry.name.endswith('.md'):
            continue
        m = EXT_PATTERN.match(entry.name)
        if m:
            base = m.group(1).strip()
            ext = m.group(2).lower()
            entries.setdefault(base, {})[f'.{ext}.md'] = entry.path
        else:
            entries.setdefault(entry.name[:-3], {})['.md'] = entry.path

    count = 0
    for base_key, variants in entries.items():
        ext_md = [k for k in variants if k != '.md']
        if not ext_md or '.md' not in variants:
            continue
        clean_path = variants['.md']

        all_links = []
        all_titles = []
        authors = set()
        categories = set()
        isbns = set()
        original_names = set()
        all_bodies = []

        for variant_key, variant_path in variants.items():
            try:
                with open(variant_path, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except Exception:
                continue
            fm, body = parse_frontmatter(text)
            all_links.extend(LINK_RE.findall(body))
            heading = extract_heading(body)
            if heading:
                all_titles.append(heading)
            if fm.get('author'):
                authors.add(fm['author'].strip('[]').strip())
            if fm.get('category'):
                categories.add(fm['category'])
            if fm.get('isbn'):
                isbns.add(fm['isbn'])
            orig = extract_original_name(body)
            if orig:
                original_names.add(orig)
            all_bodies.append(body)

        if len(all_links) < 2:
            continue

        unique_links = list(dict.fromkeys(all_links))
        best_title = max(all_titles, key=len) if all_titles else max(variants.keys(), key=len)
        best_title = re.sub(r'\.(txt|epub|mobi|azw3|pdf|djvu)$', '', best_title, flags=re.IGNORECASE).strip()
        author = next((a for a in authors if a not in ('Unknown', 'Unknown Author')), 'Unknown Author')
        category = next((c for c in categories if c != 'Uncategorized'), '00 General Fiction')
        isbn = next((i for i in isbns if i), '')

        from core.vortexy_obsidian import sanitize_filename, make_category_tag, slugify_category
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cat_tag = make_category_tag(category)
        cat_slug = slugify_category(category)
        original_name_str = '; '.join(sorted(original_names)) if original_names else ''

        lines = []
        lines.append("---")
        lines.append(f'title: "{best_title}"')
        lines.append(f'author: "[[{author}]]"')
        lines.append(f"category: {category}")
        lines.append(f"tags: [vortexy, {cat_slug}]")
        lines.append(f'isbn: "{isbn}"')
        lines.append(f"date_organized: {date_str}")
        lines.append("vortexy_version: v1.5.0")
        lines.append("---")
        lines.append("")
        lines.append(f"# {best_title}")
        lines.append("")
        lines.append(f"- **Author:** [[{author}]]")
        lines.append(f"- **Category:** {cat_tag}")
        if original_name_str:
            lines.append(f"- **Original Name:** `{original_name_str}`")
        for link in unique_links:
            safe_uri = "file:///" + urllib.parse.quote(str(link).replace("\\", "/"))
            lines.append(f"> [!abstract] File Link")
            lines.append(f"> [Open Local File]({safe_uri})")
            lines.append("")
        lines.append("---")
        lines.append("*Generated by Vortexy Graph Architect*")

        new_content = "\n".join(lines) + "\n"
        correct_name = sanitize_filename(f"{author} - {best_title}")
        target_path = os.path.join(vault_path, f"{correct_name}.md")

        if dry_run:
            print(f"   [merge-ext] Would merge: {correct_name}.md ({len(variants)} files, {len(unique_links)} links)")
            count += 1
            continue

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        for variant_key, variant_path in variants.items():
            if os.path.normpath(variant_path) != os.path.normpath(target_path) and os.path.exists(variant_path):
                try:
                    os.remove(variant_path)
                except Exception:
                    pass
        print(f"   [merge-ext] {correct_name} ({len(variants)} files, {len(unique_links)} links)")
        count += 1

    return count


def merge_fuzzy_duplicates(vault_path, dry_run=False):
    """Merge notes with same author and near-identical titles (article/case/accent diffs)."""
    import re
    from collections import defaultdict

    ARTICLES = {'le', 'la', 'les', 'el', 'los', 'las', 'il', 'lo', 'gli', 'der', 'die', 'das'}

    def norm_title(t):
        t = t.lower().strip()
        t = re.sub(r'[^\w\s]', '', t)
        words = [w for w in t.split() if w not in ARTICLES]
        return ' '.join(words)

    groups = defaultdict(list)

    for entry in os.scandir(vault_path):
        if not entry.is_file() or not entry.name.endswith('.md'):
            continue
        try:
            with open(entry.path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except Exception:
            continue
        fm, body = parse_frontmatter(text)
        author = fm.get("author", "").strip("[]").strip()
        title = extract_heading(body) or ""
        if not author or not title or author in ("Unknown", "Unknown Author"):
            continue
        nk = (author.lower().strip(), norm_title(title))
        groups[nk].append((entry.path, title))

    count = 0
    for (author_key, _), files in groups.items():
        if len(files) < 2:
            continue
        best_title = max(set(t for _, t in files), key=len)
        links = []
        seen_links = set()
        for filepath, _ in files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue
            for m in re.finditer(r'\[Open Local File\]\(([^)]+)\)', content):
                if m.group(1) not in seen_links:
                    seen_links.add(m.group(1))
                    links.append(m.group(1))
        if len(links) < 2:
            continue

        from core.vortexy_obsidian import sanitize_filename, make_category_tag, slugify_category
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cat = "00 General Fiction"

        lines = []
        lines.append("---")
        lines.append(f'title: "{best_title}"')
        lines.append(f'author: "[[{files[0][1]}]]"')
        lines.append(f"category: {cat}")
        lines.append(f"tags: [vortexy, {slugify_category(cat)}]")
        lines.append('isbn: ""')
        lines.append(f"date_organized: {date_str}")
        lines.append("vortexy_version: v1.5.0")
        lines.append("---")
        lines.append("")
        lines.append(f"# {best_title}")
        lines.append("")
        lines.append(f"- **Author:** [[{files[0][1]}]]")
        lines.append(f"- **Category:** {make_category_tag(cat)}")
        lines.append("")
        for link in links:
            lines.append(f"> [!abstract] File Link")
            lines.append(f"> [Open Local File]({link})")
            lines.append("")
        lines.append("---")
        lines.append("*Generated by Vortexy Graph Architect*")

        new_content = "\n".join(lines) + "\n"
        correct_name = sanitize_filename(f"{files[0][1]} - {best_title}")
        target_path = os.path.join(vault_path, f"{correct_name}.md")

        if dry_run:
            print(f"   [fuzzy-merge] Would merge: {correct_name}.md ({len(files)} files, {len(links)} links)")
            count += 1
            continue

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        for filepath, _ in files:
            try:
                os.remove(filepath)
            except Exception:
                pass
        print(f"   [fuzzy-merge] {correct_name} ({len(files)} files, {len(links)} links)")
        count += 1

    return count


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

    consolidated = consolidate_tracks(vault_path, dry_run=dry_run)
    if consolidated:
        print(f"   Merged {consolidated} audiobook(s)")
        print()

    merged_ext = merge_extension_duplicates(vault_path, dry_run=dry_run)
    if merged_ext:
        print(f"   Merged {merged_ext} extension-duplicate note(s)")
        print()

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
    workers = cfg.get("threads", 2)
    verbose = cfg.get("verbose", True)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'} | Organize: {'ON' if organize else 'OFF'} | Threads: {workers} | Verbose: {'ON' if verbose else 'OFF'} | Total: {total} notes in {batch_count} batches of {BATCH}")
    print()

    stats = {"fixed": 0, "renamed": 0, "moved": 0, "skipped": 0, "created": 0}
    print_lock = threading.Lock()
    valid_folders = set(subfolder_map.keys()) if organize else set()

    if organize and not dry_run:
        for folder in valid_folders:
            os.makedirs(os.path.join(vault_path, folder), exist_ok=True)
        print("   Pre-created subfolders.")

    def process_one(global_idx, fname):
        result = {"fixed": 0, "renamed": 0, "moved": 0, "skipped": 0}
        filepath = os.path.join(vault_path, fname)
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            with print_lock:
                print(f"  [{global_idx}] [!] Error reading {fname}: {e}")
            result["skipped"] += 1
            return result

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

        if author != "Unknown Author" and title:
            author_lower = author.lower().strip()
            title_lower = title.lower().strip()
            if title_lower in author_genre_map and author_lower not in author_genre_map:
                author, title = title, author

        if author == "Unknown Author" and not title:
            result["skipped"] += 1
            return result

        enriched = {}
        if enricher and (existing_isbn or author != "Unknown Author"):
            enriched = enricher.enrich(existing_isbn, title, author, year=bracket_year)

        correct_name = sanitize_filename(title if title.lower().startswith(author.lower()) else f"{author} - {title}")
        correct_filename = f"{correct_name}.md"

        target_subfolder = None
        if organize:
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
            if verbose:
                ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                msg = f"  {ts} [{global_idx}] {fname}"
                if needs_rename:
                    sub_info = f" [{target_subfolder}/]" if target_subfolder else ""
                    msg += f"\n          -> {sub_info}{correct_filename}"
                msg += " (rewrite content)"
                if author == "Unknown Author":
                    msg += " [author: Unknown Author]"
                with print_lock:
                    print(msg)
            result["fixed"] += 1
            return result

        try:
            if target_subfolder:
                os.makedirs(target_dir, exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            if needs_rename and os.path.normpath(filepath) != os.path.normpath(target_path):
                if os.path.exists(filepath):
                    os.remove(filepath)
                result["renamed"] += 1
                if verbose:
                    sub_info = f" [{target_subfolder}/]" if target_subfolder else ""
                    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    with print_lock:
                        print(f"  {ts} [{global_idx}] {fname} ->{sub_info}{correct_filename}")
            else:
                if verbose:
                    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    with print_lock:
                        print(f"  {ts} [{global_idx}] {fname} (rewritten)")

            result["fixed"] += 1
            if target_subfolder and os.path.dirname(filepath) != target_dir:
                result["moved"] += 1

        except Exception as e:
            with print_lock:
                print(f"  [{global_idx}] [!] Error writing {correct_filename}: {e}")
            result["skipped"] += 1

        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks = [(idx + 1, fname) for idx, fname in enumerate(all_items)]
        t_batch = time.time()

        for batch_start in range(0, len(tasks), BATCH):
            chunk = tasks[batch_start:batch_start + BATCH]
            before_fixed = stats["fixed"]
            futures = [pool.submit(process_one, idx, fname) for idx, fname in chunk]

            for f in as_completed(futures):
                try:
                    r = f.result()
                    if r:
                        for k in ("fixed", "renamed", "moved", "skipped"):
                            stats[k] += r.get(k, 0)
                except Exception as e:
                    pass

            b_start = batch_start + 1
            b_end = batch_start + len(chunk)
            batch_fixed = stats["fixed"] - before_fixed
            print(f"  Batch {batch_start//BATCH + 1}/{batch_count} ({b_start}-{b_end}): {batch_fixed} fixed, {(time.time()-t_batch):.1f}s, running total: {stats['fixed']} fixed")
            t_batch = time.time()

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
