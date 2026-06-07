# Architecture (MVP1)

```
PDF v1 + PDF v2
  → extraction        (PyMuPDF: prose blocks + outline + table/figure regions)
  → normalization     (sections from outline, or font fallback; comparison flags)
  → section matching  (align v1 ↔ v2 by number / title / text similarity)
  → deterministic diff (hash compare; skip unchanged; word-level snippets)
  → AI summarization  (STGpt/OpenAI; optional — runs only on changed sections)
  → reporting         (JSON + HTML + revision-history draft)
```

The design is **deterministic-first**: Python finds the changes; the LLM only
phrases them. This keeps it cheap, reproducible, and free of context-window
limits.

## Modules (`backend/compy/`)

| Module | Responsibility |
| --- | --- |
| `extractor.py` | **PyMuPDF** layout-aware extraction. Produces an `ExtractionResult`: per-page `PageArtifact` (raw + prose text, table/figure bboxes), the parsed bookmark `outline`, the geometry-filtered `prose_blocks`, and the dominant `body_font_size`. Geometry excludes tables, figures, headers/footers, captions. |
| `normalizer.py` | Builds `Section`s. `OutlineSectionBuilder` (bookmarks) is primary; `FontHeadingSectionBuilder` (font-size heading detection) is the no-outline fallback; the old regex `SectionBuilder` is a last resort. Sets `comparison_enabled` per section type. |
| `text_utils.py` | Generic, vocabulary-free helpers: normalization, hashing, canonical comparison text, and a thin structural safety net. |
| `matcher.py` | Aligns sections between versions (number → title → similarity). |
| `diff_engine.py` | Compares matched sections by canonical hash, skips unchanged, emits word-level snippets for modified ones. |
| `llm.py` | Provider-neutral `LLMClient` + `ChangeSummarizer` (OpenAI / STGpt). |
| `reporting.py` | Builds the diff report, revision-history draft, and HTML. |
| `pipeline.py` | Orchestrates the full run. |
| `io.py`, `models.py` | JSON I/O and domain dataclasses. |

## Data model highlights (`models.py`)

- `PageArtifact` — `raw_text`, `prose_text`, and `table_bboxes` / `figure_bboxes`
  (recorded for MVP3/MVP4).
- `OutlineEntry` — one bookmark: `level`, `number`, `title`, `section_type`,
  `page_index`.
- `ProseBlock` — a geometry-filtered block with per-line `(text, size)` for the
  font fallback.
- `Section` — `comparison_enabled`, `normalized_text`, `normalized_text_hash`
  (canonical), plus number/title/page metadata.

## Section types and comparison

`main_content`, `introduction`, `appendix` → **compared**.
`toc`, `list_of_tables`, `list_of_figures`, `revision_history`, `legal_notice`,
`front_matter` → extracted but **not compared**.

## Frontend

`frontend/compy_ui.py` — PySide6 desktop app driving the same `ComparisonPipeline`.
