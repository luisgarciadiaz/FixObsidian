# User Guide: ISBN & Book Metadata Enrichment

## Overview

The enrichment feature fetches rich book metadata from the free public
**Open Library API** to automatically correct misclassified categories,
add publisher/synopsis details, and enrich note frontmatter.

### What it does

- Looks up ISBN in frontmatter via the Open Library Books API
- Falls back to title/author search if ISBN is missing or unmatched
- Fetches work details (synopsis, subjects) from `/works/` endpoint
- Maps API subjects to your vault subfolder categories
- Caches all responses to `data/metadata_cache.json`

### Before / After

**Before (AI misclassified):**
```markdown
---
category: Technical & Programming
tags: [vortexy, technical-programming]
---
```

**After (enrichment corrected):**
```markdown
---
category: Science Fiction
tags: [vortexy, science-fiction]
publisher: "Del Rey"
publish_date: "1977"
---

> [!info] Synopsis
> Gateway is a 1977 sci-fi novel by Frederik Pohl...
```

---

## CLI Usage

### Enable enrichment

```powershell
python tools/fix_obsidian_notes.py --enrich
```

### Dry-run with enrichment (cache-only, no API calls)

```powershell
python tools/fix_obsidian_notes.py --dry-run --enrich
```

### Process first 100 notes with enrichment

```powershell
python tools/fix_obsidian_notes.py --limit 100 --enrich
```

### Clear cache and refetch all metadata

```powershell
python tools/fix_obsidian_notes.py --enrich --clear-cache
```

### Enable in config.json

Set `"isbn_enrichment": true` in `config.json` to enable by default:

```json
{
  "isbn_enrichment": true,
  "enrichment_cache_path": "data/metadata_cache.json"
}
```

When enabled in config, the `--enrich` flag is optional.

---

## Performance & Caching

- First run: one API call per note (~0.5s each), results cached to disk
- Subsequent runs: instant cache lookups, zero API calls for previously seen books
- Dry-run: reads from cache but never makes live API requests
- Cache file: `data/metadata_cache.json` (JSON, human-readable)

## Genre Routing Priority

When enrichment is enabled, subfolder routing uses this priority:

1. Author genre map (Postgres DB, if not "00 General Fiction")
2. **Enrichment suggested category** (from Open Library subjects)
3. Title keyword match against `subfolder_map`
4. Author genre map fallback
5. Category frontmatter keyword match

## Rate Limiting

A 0.5-second delay is inserted between API calls to stay within free
limits. Open Library has no API key requirement for reasonable use.
