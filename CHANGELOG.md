# CHANGELOG

## v1.2.0 (2026-05-19)

### Added
- **Chapter prefix extraction** — Numeric/section prefixes (e.g., `04 -`, `03A -`) are now stripped from filenames and saved as `chapter` field in frontmatter
- `chapter` field in frontmatter and body (displays as `- **Chapter:** 04`)

### Fixed
- Course/tutorial files with numeric prefixes (like `04 - 01-Basic FKIK switching theory.md`) now get proper `Author - Title` naming
- `strip_bad_prefix()` now returns the prefix as chapter when no valid author is found

## v1.1.0 (2026-05-19)

### Added
- `AGENTS.md` — Expanded agent instructions with CLI usage, author resolution strategy, and statistics tracked
- `README.md` — Improved documentation with quick start, feature list, subfolder category table, and CLI options reference

### Changed
- `tools/fix_obsidian_notes.py` — Added `--force` flag to rewrite notes even when filename is already correct
- `core/vortexy_obsidian.py` — `create_obsidian_note()` now removes stale note with old author name before creating corrected note

### Fixed
- `tools/fix_obsidian_notes.py` — Author resolution now strips bad prefixes (`an`, `el`, `los`, `la`, `mi`, `no`, `lg`, `m`, `dune`, `dragon`, `stephen`, `charles`, `patricia`, `historia`, `platon`, `homero`, `isabel`, `gabriel`, `mao`)
- `tools/fix_obsidian_notes.py` — Title now properly cleaned of redundant author prefix via `strip_author_prefix()`

## v1.0.0 (2026-05-18)

Initial release of the FixObsidian toolset.

### Added
- `core/vortexy_obsidian.py` — Improved note template with:
  - `title` field in YAML frontmatter (was missing)
  - `tags` block with `[vortexy, category-slug]`
  - Clickable Open Library ISBN link when ISBN is non-empty
  - Proper `#Category_Name` tag rendering
  - Subfolder mapping utility for category-based organization
- `tools/fix_obsidian_notes.py` — Standalone fixer script:
  - Scans Obsidian vault for Vortexy-generated notes
  - Parses existing frontmatter, heading, and body
  - Fixes author to "Unknown Auto" when unidentifiable
  - Renames notes to correct `Author - Title.md` format
  - Rewrites content with the improved template
  - Re-discovers file_uri by scanning PDF library path
  - Optional `--organize` flag to move notes into category subfolders
  - `--dry-run`, `--limit`, `--force` CLI flags
- `AGENTS.md` — Project instructions for AI-assisted development
- `CHANGELOG.md` — This file