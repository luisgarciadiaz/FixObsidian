# ISBN and Book Metadata Enrichment Plan

This plan details how to add automatic book metadata enrichment to the `FixObsidian` toolset. It will leverage the free, public **Open Library API** to automatically correct misclassified categories, enrich note frontmatter/body with publisher and series info, and append synopses.

## Goal Description

Currently, notes in the vault are processed using local regex heuristics, which often results in:
* **Misclassified categories:** e.g., Sci-Fi novels like Frederik Pohl's *Gateway* misclassified as `Technical & Programming`.
* **Sparse note bodies:** Missing publication dates, publishers, series/volume details, and descriptive summaries.

We propose updating `tools/fix_obsidian_notes.py` and `core/vortexy_obsidian.py` to optionally fetch rich metadata using a non-key, rate-friendly pipeline from the Open Library API.

---

## User Review Required

> [!IMPORTANT]
> **API Call Policy & Rate Limiting:**
> The script will perform network requests when running. To avoid hitting rate limits or slowing down execution:
> 1. We will cache API responses locally (e.g. in `data/metadata_cache.json`) so subsequent runs or dry-runs for the same book are instant.
> 2. We will limit rapid requests using a short sleep interval (e.g. 0.5s) between notes.
> 3. We will provide a new CLI switch `--enrich` to explicitly turn on metadata fetching. By default, it will check the cache or only run when requested.

> [!TIP]
> **Automated Genre Mapping:**
> Subject tags returned by Open Library (e.g., "Science fiction", "Horror", "Interplanetary voyages") will be matched against your existing `subfolder_map` in `config.json` to assign notes to the correct category subfolders automatically.

---

## Open Questions

* **Metadata Cache Location:** We plan to store cached metadata in a new `data/metadata_cache.json` file inside the workspace so that you don't re-query the API for the same books. Does that location work for you?
* **Override Policy:** If the note already has a manually corrected category or fields in frontmatter, should we skip overwriting them? (Recommended: Only enrich empty or AI-generated values like "Unknown Auto" / "Uncategorized" or when the existing category matches an AI misclassification).

---

## Proposed Changes

### FixObsidian Core

#### [MODIFY] [vortexy_obsidian.py](file:///v:/Git/luisgarciadiaz/FixObsidian/core/vortexy_obsidian.py)
* Update `make_obsidian_content()` to accept new optional arguments: `publisher`, `publish_date`, and `synopsis`.
* Refactor the markdown template to include:
  * Frontmatter fields: `publisher: "{publisher}"`, `publish_date: "{publish_date}"`.
  * Note body: A new `> [!info] Synopsis` callout block if a synopsis is present.
  * Corrected category tagging based on API subjects.

---

### FixObsidian Tools

#### [MODIFY] [fix_obsidian_notes.py](file:///v:/Git/luisgarciadiaz/FixObsidian/tools/fix_obsidian_notes.py)
* Add a `MetadataEnricher` class to handle:
  1. **ISBN Lookup:** Call Open Library Book API (`https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data`).
  2. **Search API Fallback:** If the exact ISBN is missing, query Open Library Search (`https://openlibrary.org/search.json?isbn={isbn}`).
  3. **Title/Author Fallback:** If search by ISBN fails, query Open Library Search with title and author parsed from the filename/existing frontmatter.
  4. **Work Lookup:** Follow the `/works/OLxxxxxW` link to fetch description and subjects.
* Add local cache reading/writing to `data/metadata_cache.json`.
* Integrate the enricher into the main note processing loop of `fix_notes()`:
  * When `isbn_enrichment` is enabled in config or `--enrich` is passed via CLI, trigger lookup.
  * Use returned subjects to find the best-matching genre subfolder.
* Add CLI flags:
  * `--enrich`: Turn on live web metadata enrichment.
  * `--clear-cache`: Clear the local metadata cache.

---

## Verification Plan

### Automated/Manual Verification
1. Run with a single note limit to test integration:
   ```powershell
   python tools/fix_obsidian_notes.py --limit 1 --enrich --dry-run
   ```
2. Verify the output displays corrected category (e.g., `#Science_Fiction`), correctly parsed series, publisher, and synopsis.
3. Validate that `data/metadata_cache.json` is created and correctly populated.
4. Verify that running the script a second time uses the cache and makes zero network requests.
