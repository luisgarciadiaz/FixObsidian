# Developer Reference: Metadata Enricher

## Architecture

```
core/vortexy_enricher.py     — MetadataEnricher class, Open Library pipeline
data/metadata_cache.json     — JSON cache (auto-created)
tools/fix_obsidian_notes.py  — Consumer (calls enricher.enrich() per note)
core/vortexy_obsidian.py     — Template (renders publisher/synopsis fields)
```

## MetadataEnricher Class

Located in `core/vortexy_enricher.py:13`.

### Constructor

```python
MetadataEnricher(subfolder_map, dry_run=False, cache_path=None)
```

- `subfolder_map` — dict from config.json subfolder_map
- `dry_run` — if True, never makes live API requests
- `cache_path` — defaults to `data/metadata_cache.json`

### Key Methods

| Method | Description |
|--------|-------------|
| `enrich(isbn, title, author)` | Main entry point. Returns dict with publisher, publish_date, synopsis, suggested_category |
| `clear_cache()` | Empties in-memory cache and saves to disk |

### Return Value

```python
{
    "publisher": "Del Rey",
    "publish_date": "1977",
    "synopsis": "A long description of the book...",
    "suggested_category": "03 Science Fiction"
}
```

Returns empty dict `{}` if no metadata found.

---

## API Pipeline

The enricher queries Open Library in this sequence:

### 1. ISBN Lookup

```
GET https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data
```

Extracts: title, publish_date, publisher, subjects, work_key

### 2. Search Fallback (ISBN)

If Step 1 returns nothing:

```
GET https://openlibrary.org/search.json?isbn={isbn}
```

### 3. Title/Author Search

If Steps 1-2 fail:

```
GET https://openlibrary.org/search.json?title={title}&author={author}
```

### 4. Work Lookup

If a work_key is found (`/works/OLxxxxxW`):

```
GET https://openlibrary.org/works/OLxxxxxW.json
```

Extracts: description (synopsis), subjects

### Subject-to-Subfolder Mapping (`_map_subjects`)

The subjects list from all API responses is matched against keywords
in `subfolder_map` (case-insensitive substring match). Longest match wins.

---

## Cache Structure

`data/metadata_cache.json`:

```json
{
  "isbn:0553293370": {
    "publisher": "Spectra",
    "publish_date": "1991",
    "synopsis": "...",
    "suggested_category": "03 Science Fiction"
  },
  "title:gateway|frederik pohl": { ... }
}
```

Keys are either `isbn:{cleaned_isbn}` or `title:{title}|{author}`.

---

## Extending to Other APIs

To add a secondary source (Google Books, Goodreads, etc.):

1. Add a new method to `MetadataEnricher` (e.g., `_google_books(self, isbn)`)
2. Call it in `enrich()` after the Open Library pipeline returns empty
3. Normalize the response to the same dict format
4. Cache works automatically since the cache key stays the same

## Integration Points

### In fix_notes loop (tools/fix_obsidian_notes.py:122-124)

```python
enriched = {}
if enricher:
    enriched = enricher.enrich(existing_isbn, title, author)
```

### Subfolder routing (tools/fix_obsidian_notes.py:133-138)

Enrichment suggested category is priority #2, between author_genre_map
and title keyword matching.

### Template rendering (core/vortexy_obsidian.py:81)

`make_obsidian_content()` accepts optional `publisher`, `publish_date`,
`synopsis` params. Each is rendered conditionally if non-empty.
