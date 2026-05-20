#!/usr/bin/env python3
"""
Look up authors via OpenLibrary API to determine primary genre.
Populates the author_genre_map table with genre -> subfolder mappings.
Run this once as a batch enrichment - not during fixer runs.

Usage:
    python enrich_author_genres.py              # full run
    python enrich_author_genres.py --skip 150   # resume from author 150
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from collections import Counter

import psycopg2

# OpenLibrary subject → Vault subfolder mapping
SUBJECT_TO_SUBFOLDER = {
    "horror": "01 Horror",
    "horror tales": "01 Horror",
    "horror fiction": "01 Horror",
    "gothic fiction": "01 Horror",
    "fantasy": "02 Fantasy",
    "fantasy fiction": "02 Fantasy",
    "epic fantasy": "02 Fantasy",
    "magic": "02 Fantasy",
    "science fiction": "03 Science Fiction",
    "sci-fi": "03 Science Fiction",
    "dystopian": "03 Science Fiction",
    "space opera": "03 Science Fiction",
    "mystery": "04 Crime & Mystery",
    "detective": "04 Crime & Mystery",
    "detective and mystery stories": "04 Crime & Mystery",
    "thriller": "04 Crime & Mystery",
    "suspense": "04 Crime & Mystery",
    "crime": "04 Crime & Mystery",
    "noir": "04 Crime & Mystery",
    "thrillers": "04 Crime & Mystery",
    "romance": "05 Romance",
    "love stories": "05 Romance",
    "erotic": "05 Romance",
    "historical fiction": "06 Historical Fiction",
    "historical": "06 Historical Fiction",
    "biography": "07 Biography & Autobiography",
    "autobiography": "07 Biography & Autobiography",
    "memoir": "07 Biography & Autobiography",
    "self-help": "08 Memoir & Self-Help",
    "personal development": "08 Memoir & Self-Help",
    "psychology": "08 Memoir & Self-Help",
    "history": "09 History",
    "ancient": "09 History",
    "medieval": "09 History",
    "military": "09 History",
    "war": "09 History",
    "programming": "10 Technical & Programming",
    "computers": "10 Technical & Programming",
    "computer science": "10 Technical & Programming",
    "software": "10 Technical & Programming",
    "technology": "13 Science & Technology",
    "philosophy": "11 Philosophy",
    "ethics": "11 Philosophy",
    "business": "12 Business & Economics",
    "economics": "12 Business & Economics",
    "management": "12 Business & Economics",
    "finance": "12 Business & Economics",
    "science": "13 Science & Technology",
    "physics": "13 Science & Technology",
    "chemistry": "13 Science & Technology",
    "biology": "13 Science & Technology",
    "mathematics": "13 Science & Technology",
    "comics": "14 Graphic & Literary Arts",
    "graphic novels": "14 Graphic & Literary Arts",
    "poetry": "14 Graphic & Literary Arts",
    "art": "14 Graphic & Literary Arts",
    "fiction": None,  # too broad, ignore
    "literature": None,
    "novel": None,
    "stories": None,
}

API_URL = "https://openlibrary.org/search.json"
FIELDS = "key,title,subject_facet"
REQUEST_DELAY = 0.3  # be nice to the API


def lookup_author(author_name):
    """Query OpenLibrary for an author's works and extract top subjects."""
    params = urllib.parse.urlencode({
        "author": author_name,
        "limit": 20,
        "fields": FIELDS,
    })
    url = f"{API_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FixObsidian/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [!] API error for '{author_name}': {e}")
        return None

    docs = data.get("docs", [])
    if not docs:
        return None

    subject_counter = Counter()
    for doc in docs:
        for subj in doc.get("subject_facet", []):
            subj_lower = subj.lower()
            subject_counter[subj_lower] += 1
            for part in (p.strip() for p in subj_lower.split(",")):
                if part and part != subj_lower:
                    subject_counter[part] += 1

    best_sf = None
    best_score = 0
    for subj, count in subject_counter.most_common():
        sf = SUBJECT_TO_SUBFOLDER.get(subj)
        if sf and count > best_score:
            best_score = count
            best_sf = sf

    return best_sf


def main():
    parser = argparse.ArgumentParser(description="Enrich author genre map via OpenLibrary API")
    parser.add_argument("--skip", type=int, default=0, help="Skip first N authors (resume)")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host="192.168.68.104", port=5432,
        user="postgres", password="T|2801orxK8F",
        dbname="app_db"
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT author_name FROM author_genre_map
        WHERE subfolder IN ('00 General Fiction', '10 Technical & Programming')
        ORDER BY author_name
    """)
    fiction_authors = [r[0] for r in cur.fetchall()]
    total = len(fiction_authors)
    print(f"Fiction authors to classify: {total}")

    if args.skip:
        fiction_authors = fiction_authors[args.skip:]
        print(f"Skipping first {args.skip}, {len(fiction_authors)} remaining")

    updated = 0
    skipped = 0
    for i, author in enumerate(fiction_authors):
        idx = args.skip + i + 1
        safe_name = author.encode('ascii', errors='replace').decode('ascii')
        print(f"[{idx}/{total}] {safe_name} ... ", end="", flush=True)

        genre = lookup_author(author)
        if genre:
            cur.execute(
                "UPDATE author_genre_map SET subfolder = %s WHERE author_name = %s",
                (genre, author)
            )
            conn.commit()
            updated += 1
            print(genre)
        else:
            # Only delete no-match entries that were originally General Fiction
            cur.execute(
                "DELETE FROM author_genre_map WHERE author_name = %s AND subfolder = '00 General Fiction'",
                (author,)
            )
            conn.commit()
            skipped += 1
            print("(removed)")

        time.sleep(REQUEST_DELAY)

    print(f"\nDone. Updated: {updated}, Removed: {skipped}")

    cur.execute("SELECT subfolder, COUNT(*) FROM author_genre_map GROUP BY subfolder ORDER BY COUNT(*) DESC")
    print("\nDistribution:")
    for r in cur.fetchall():
        print(f"  {r[1]:>5}  {r[0]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
