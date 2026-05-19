# CHANGELOG

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
- `agents.md` — Project instructions for AI-assisted development
- `CHANGELOG.md` — This file
