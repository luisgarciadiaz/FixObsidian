# Troubleshooting: Metadata Enrichment

## Enrichment returns empty results

**Symptom:** Notes processed with `--enrich` show no publisher/synopsis added.

**Causes & Fixes:**

1. **Book not on Open Library** — especially for non-English, very old,
   or obscure titles. Check manually at `https://openlibrary.org`.

2. **ISBN missing from frontmatter** — the enricher falls back to
   title/author search, which is less precise. Add an ISBN to the
   note's frontmatter for better results.

3. **Dry-run mode** — dry-runs never make live API calls. Run without
   `--dry-run` to fetch new data (existing cache entries still work).

4. **Title/author mismatch** — if the resolved title/author differs
   from the Open Library entry, the search won't match. Verify the
   resolved values in the dry-run output.

---

## Rate Limiting (HTTP 429)

Open Library is generous with free usage, but if you hit limits:

- The built-in 0.5s delay between requests should prevent this
- If it happens, stop the script and wait 30 minutes
- Use `--limit N` to process in smaller batches
- The cache prevents re-querying already-fetched books

---

## Incorrect Category Mapping

**Symptom:** A book is assigned to the wrong genre subfolder after enrichment.

**Fix:** Edit the keyword associations in the `subfolder_map` within
`config.json`. Each subfolder has a list of keywords. When an Open Library
subject matches a keyword, that subfolder is selected.

Example: If "Space Opera" books go to General Fiction instead of Sci-Fi,
add `"space opera"` to the `03 Science Fiction` keywords list.

```json
"03 Science Fiction": ["science fiction", "sci-fi", "scifi", "space", "space opera"]
```

After editing, clear the cache with `--clear-cache` and reprocess to
re-map categories.

---

## Clear Stale Cache

```powershell
python tools/fix_obsidian_notes.py --enrich --clear-cache --limit 100
```

This deletes `data/metadata_cache.json` and refetches all metadata.

---

## Cache File Corruption

If `data/metadata_cache.json` becomes corrupted (malformed JSON), the
enricher will silently ignore it and start fresh. You can also delete
it manually:

```powershell
Remove-Item -LiteralPath "data\metadata_cache.json"
```

---

## Network Errors / Timeouts

The enricher retries failed requests up to 2 times with a 1-second
delay between attempts. If all retries fail, the request is skipped
and the note continues processing without enrichment data.

Common causes:
- No internet connection
- Open Library API downtime (rare, check https://openlibrary.org)
- Firewall blocking outbound HTTPS on port 443
