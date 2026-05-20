# Documentation Plan: ISBN & Book Metadata Enrichment Feature

This document outlines the plan to create, organize, and maintain both user-facing and developer-facing documentation for the new **ISBN & Open Library Book Enrichment** feature in `FixObsidian`.

---

## 1. Documentation Structure & Objectives

Our objective is to ensure that both users running the script and developers modifying/extending it have comprehensive, clear instructions. The documentation suite will consist of:

```
v:\Git\luisgarciadiaz\FixObsidian\
├── README.md                           # Quickstart & user options (Modified)
├── agents.md                           # AI instructions (Completed)
└── docs/
    ├── user_guide_enrichment.md        # [NEW] Full user manual & best practices
    ├── developer_reference.md          # [NEW] Code guide: cache, endpoints, custom APIs
    └── troubleshooting.md              # [NEW] Caching, rate-limiting, missing metadata
```

---

## 2. Document-by-Document Execution Plan

### A. User Guide (`docs/user_guide_enrichment.md`)
This manual will walk a user through running the new metadata enrichment features.
* **Sections to include:**
  * **Features Overview:** Visual before/after examples of notes, highlighting the auto-genre subfolder routing and synopsis callout blocks.
  * **Interactive Command Guide:** How to trigger enrichment using CLI flags:
    * `--enrich`: Live fetching.
    * `--clear-cache`: Purging cached metadata.
  * **Best Practices:** Recommendations for tagging, handling translations, and setting up initial offline-cached runs on large folders.

### B. Developer Reference (`docs/developer_reference.md`)
A guide for developers who want to extend or customize the metadata pipeline.
* **Sections to include:**
  * **Cache Management:** How `data/metadata_cache.json` reads/writes are structured and how to manually edit/invalidate records.
  * **Open Library API Integration:** How the query cycle runs sequentially (ISBN API $\rightarrow$ Search API $\rightarrow$ Work API) and how to handle API schema changes.
  * **Extending to Other APIs:** High-level blueprint to plug in secondary sources (e.g., Google Books, Goodreads, or local SQLite/CSV sources) under the `MetadataEnricher` class structure.

### C. Troubleshooting Guide (`docs/troubleshooting.md`)
A quick guide for diagnosing failures during execution.
* **Sections to include:**
  * **Rate Limiting (HTTP 429):** How to increase retry intervals or use backup proxy endpoints.
  * **Missing / Sparse Metadata:** What to do when an old or niche translation isn't on Open Library (e.g. how to force search using alternate titles).
  * **Incorrect Category Mapping:** How to edit the keyword associations in the `subfolder_map` inside `config.json` to correct routing mistakes.

---

## 3. Integration & Rollout Plan

To ensure the new documentation remains maintained and easily accessible:
1. **README Update:** Append a brief section to the main `README.md` pointing to the new files in the `docs/` folder.
2. **AI-Agent Alignment:** The developer AI must update these docs immediately if it modifies any schemas or changes caching structures during implementation.
