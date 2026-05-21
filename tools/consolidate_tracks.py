#!/usr/bin/env python3
"""Consolidate audiobook track notes and multipart section notes into single per-book notes."""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE_DIR)

from core.vortexy_parsers import parse_frontmatter


TRACK_RE = re.compile(r'^(.+?)\s*-\s*Disc\s+(\d+)\s+Track\s+(\d+)', re.IGNORECASE)
SECTION_RE = re.compile(r'^(.+)\s+(\d{2,})$')
PREFIX_SECTION_RE = re.compile(r'^(\d{2,})\s*[- ]\s*(.+)$')


def _book_author_key(name):
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
    m = PREFIX_SECTION_RE.match(stem)
    if m:
        sec = int(m.group(1))
        base = m.group(2).strip()
        if sec < 100:
            base = re.sub(r'\s+CD\d+$', '', base, flags=re.IGNORECASE).strip()
            return base, 'section', sec, None
    return None, None, None, None


def consolidate_tracks(vault_path, dry_run=False):
    groups = {}

    for entry in os.scandir(vault_path):
        if not entry.is_file() or not entry.name.endswith('.md'):
            continue
        key, kind, a, b = _book_author_key(entry.name)
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
