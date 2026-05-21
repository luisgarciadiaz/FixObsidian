#!/usr/bin/env python3
"""Prune useless entries from the metadata cache."""

import json
import os
import sys
import time
import argparse

CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE_DIR)

from core.vortexy_config import load_config

CACHE_PATH = os.path.join(CORE_DIR, "data", "metadata_cache.json")


def prune_cache(cache_path, remove_empty=False, max_age=None, vault_path=None, dry_run=False):
    if not os.path.exists(cache_path):
        print(f"Cache not found: {cache_path}")
        return

    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    before = len(cache)
    removed = 0
    empty_removed = 0
    stale_removed = 0
    orphan_removed = 0

    vault_files = set()
    if vault_path and os.path.isdir(vault_path):
        vault_files = {e.name for e in os.scandir(vault_path) if e.name.endswith(".md")}

    now = time.time()
    keys_to_remove = []

    for key, val in cache.items():
        if remove_empty and (not val or val == {}):
            keys_to_remove.append(key)
            empty_removed += 1
            continue
        if max_age is not None:
            ts = val.get("_ts", 0) if isinstance(val, dict) else 0
            if ts and (now - ts) > max_age * 86400:
                keys_to_remove.append(key)
                stale_removed += 1
                continue
        if vault_path and vault_files:
            if key.startswith("isbn:"):
                isbn = key[5:]
                found = any(isbn in fname for fname in vault_files)
                if not found:
                    keys_to_remove.append(key)
                    orphan_removed += 1
                    continue

    if dry_run:
        print(f"  [DRY RUN] Would remove {len(keys_to_remove)} entries")
        print(f"    Empty:  {empty_removed}")
        print(f"    Stale:  {stale_removed}")
        print(f"    Orphan: {orphan_removed}")
        print(f"    Before: {before}")
        print(f"    After:  {before - len(keys_to_remove)}")
        return

    for key in keys_to_remove:
        del cache[key]
    removed = len(keys_to_remove)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"  Removed: {removed}")
    print(f"    Empty:  {empty_removed}")
    print(f"    Stale:  {stale_removed}")
    print(f"    Orphan: {orphan_removed}")
    print(f"    Before: {before}")
    print(f"    After:  {len(cache)}")
    size_kb = os.path.getsize(cache_path) / 1024
    print(f"    Size:   {size_kb:.1f} KB")


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Prune metadata cache entries")
    parser.add_argument("--cache", default=CACHE_PATH, help="Cache file path")
    parser.add_argument("--empty", action="store_true", help="Remove entries with no data")
    parser.add_argument("--stale", type=float, default=0, help="Remove entries older than N days")
    parser.add_argument("--vault", default=cfg.get("vault_path", ""), help="Vault path for orphan detection")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    prune_cache(args.cache, remove_empty=args.empty, max_age=args.stale or None,
                vault_path=args.vault, dry_run=args.dry_run)
