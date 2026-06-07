# COMPY — Class & Function Reference

A quick map of the codebase. The flow is a pipeline of classes:

```
CompyEngine.compare()                      (public facade)
        │
        ▼
ComparisonPipeline.run()                   (orchestrator)
        │
        ├─ PdfExtractor.extract()          → ExtractionResult
        ├─ DocumentNormalizer.normalize()  → Document (Sections)
        │     ├─ OutlineSectionBuilder      (bookmarks present)
        │     ├─ FontHeadingSectionBuilder  (no bookmarks)
        │     └─ SectionBuilder             (last-resort regex)
        ├─ SectionMatcher.match()          → [SectionMatch]
        ├─ DiffEngine.diff()               → [DiffItem]
        ├─ ChangeSummarizer.summarize()    (LLMClient, optional)
        └─ ReportBuilder.build()           → [RevisionEntry] + artifacts
```

---

## 1. Public facade — `engine.py`

### `class CompyEngine`
The single entry point for embedding COMPY in another app.
- `__init__(llm_config=None)` — build the engine; optional STGpt/OpenAI config.
- `compare(pdf_v1, pdf_v2, output_dir=None, progress=None, debug=False)` — compare
  two PDFs and return a `ComparisonJobResult`. Runs in memory unless `output_dir`
  is given; `progress` is a status callback; `debug=True` also writes `pages.json`.

## 2. Orchestrator — `pipeline.py`

### `class ComparisonPipeline`
Wires the stages together (each stage is injectable for testing).
- `__init__(extractor, normalizer, matcher, diff_engine, summarizer, report_builder)` —
  all optional; sensible defaults are created.
- `with_llm_config(llm_config)` *(classmethod)* — build a pipeline whose summarizer
  uses the given LLM provider.
- `run(pdf_v1, pdf_v2, output_dir=None, progress=None, debug=False)` — execute the
  full extract → normalize → match → diff → summarize → report flow.

## 3. Extraction — `extractor.py`

### `class PdfExtractor`
Layout-aware extraction with PyMuPDF; excludes tables/figures/headers by geometry.
- `extract(pdf_path, output_dir=None, progress=None, debug_artifacts=False)` — main
  entry; returns an `ExtractionResult`, optionally writing artifacts.
- `_extract_with_fitz(path, progress)` — the two-pass core (collect candidate body
  blocks, compute dominant body font, assemble prose blocks + sections).
- `_table_rects(page)` — table bounding boxes via `find_tables()`.
- `_safe_drawings(page)` — vector drawings (fetched once, reused).
- `_figure_rects(page, fitz, blocks, drawings)` — figure regions (images + drawing
  clusters) to exclude.
- `_cluster_rects(rects, fitz, gap)` — merge nearby drawing rects into figure blocks.
- `_candidate_blocks(blocks, height, exclusion)` — keep body lines, drop
  headers/footers/captions/excluded regions.
- `_dominant_body_size(page_infos)` — most common body font size (drives filtering).
- `_is_subbody_orphan(size, words, body_size)` — flags small figure-legend lines.
- `_parse_outline(doc)` / `_outline_is_reliable(outline)` — read bookmarks; reject a
  malformed tag-tree masquerading as an outline.
- `_split_number(title)` — split "2.1 Title" into number + title.
- `_expand(rect, margin)` — grow an exclusion rect slightly.

**Module functions:**
- `classify_section_type(title)` — toc / list_of_tables / revision_history /
  introduction / appendix / front_matter / main_content.
- `_reconstruct_line_text(line)` — rebuild a line from per-character positions,
  inserting missing spaces (fixes "Thehostinitialization").
- `_rect`, `_contains` — small geometry helpers.

### `class PdfExtractionError(RuntimeError)`
Raised when a PDF is missing or unreadable.

## 4. Sectioning — `normalizer.py`

### `class DocumentNormalizer`
Turns an `ExtractionResult` into a `Document` of `Section`s; picks the builder.
- `normalize(document_id, source_pdf, extraction, output_dir=None)` — outline builder
  if bookmarks are reliable, else the font builder, else regex.
- `document_payload(document)` *(static)* — JSON form without page bodies.

### `class OutlineSectionBuilder`  *(primary)*
Build sections from the PDF bookmark outline.
- `build(outline, prose_blocks, body_size=0.0)` — one section per bookmark; bodies
  assembled from prose blocks between heading anchors.
- `_anchors(...)` — locate each heading in the prose stream.
- `_unique_id`, `_parent_id`, `_is_body` — id/hierarchy/body-vs-heading helpers.

### `class FontHeadingSectionBuilder`  *(no-outline fallback)*
Detect headings by font size + numbered pattern when there are no bookmarks.
- `build(prose_blocks, body_size)` — detect headings, slice bodies between them.
- `_is_heading_font(...)`, `_classify_heading(...)` — heading detection rules.

### `class SectionBuilder`  *(last-resort regex)*
Regex heading detection on plain page text (used only if the above yield nothing).
- `build_sections(pages)` and several private heading-validation helpers.

**Module functions:** `assemble_body(items)` (filter body pieces, keep page map),
`heading_echo_keys(headings)` (drop running-header echoes of titles).

## 5. Matching — `matcher.py`

### `class SectionMatcher`
Align V1 ↔ V2 sections.
- `match(old_document, new_document)` — O(n) index match by number/title, then text
  similarity only for the residual; returns `[SectionMatch]`.
- `_indexed_match(...)` — fast dict lookup by number/title.
- `_best_match(...)` — similarity fallback for residual sections.
- `_title_key`, `_section_title_present` — normalization/lookup helpers.

## 6. Diffing — `diff_engine.py`

### `class DiffEngine`
Produce one `DiffItem` per edit; classify added/deleted/changed.
- `diff(old_document, new_document, matches)` — skip unchanged (hash equal), diff the
  rest, emit whole-section add/remove items.
- `_section_changes(old, new)` — token-level diff (two-level for very long sections).
- `_word_changes(...)` — emit changes for one token span, with page + structured
  prefix/change/suffix snippets.
- `_summary`, `_whole_section_item` — helpers.

**Module functions:** `_tokenize` (split words from punctuation — makes insertions
classify as *Added* and isolates the exact changed words), `_tokens_with_pages`,
`_token_offsets`, `_split_snippet`, `_join_tokens`.

## 7. Summarization — `llm.py`

### `class LLMConfig` *(dataclass)*
Provider/model/keys; `from_env()` builds it from environment variables.

### `class LLMClient`
Provider-neutral chat-completion wrapper (OpenAI / STGpt).
- `summarize_change(diff_item)` — one revision sentence (empty if no provider).
- `_chat_completion(url, diff_item)` — HTTP call.

### `class ChangeSummarizer`
- `summarize(diff_items)` — fill each item's `ai_summary` (LLM or deterministic
  fallback). `_fallback_summary(item)` builds the offline wording.

## 8. Reporting — `reporting.py`

### `class ReportBuilder`
Build the revision history + KPIs + artifacts.
- `build(diff_items, section_matches, output_dir)` — returns `[RevisionEntry]`; writes
  JSON/HTML when `output_dir` is not None.
- `kpi_summary(diff_items)` *(static)* — `{added, deleted, changed, total}`.
- `kpi_by_chapter(diff_items)` *(static)* — counts rolled up by top-level chapter.
- `_snippet_html`, `_html_report` — colored table (only changed words highlighted).

**Module function:** `_chapter_sort_key` — numeric chapter ordering.

## 9. Data models — `models.py` (all `@dataclass`)

| Class | What it holds |
| --- | --- |
| `DocumentMetadata` | file name, title, doc code, revision, page count, PDF metadata |
| `PageArtifact` | one page: raw + prose text, header/footer, table/figure bboxes |
| `OutlineEntry` | one bookmark: level, number, title, section_type, page index |
| `ProseBlock` | a geometry-filtered paragraph/heading block (+ per-line font sizes) |
| `ExtractionResult` | metadata + pages + outline + prose_blocks + body_font_size |
| `Section` | one section: text, hash, page range, type, `comparison_enabled`, page_map |
| `Document` | a normalized document: metadata + pages + sections |
| `SectionMatch` | how an old section aligned to a new one (status/score/reason) |
| `DiffItem` | one change: type, section #, page, old/new snippet + prefix/change/suffix |
| `RevisionEntry` | one human-readable revision-history row |
| `ComparisonJobResult` | the full result: documents, matches, `changes`, `kpi_summary` |

`to_dict(value)` converts any dataclass graph to JSON-friendly dicts.

## 10. Utilities — `text_utils.py`, `io.py`
Stateless helpers (kept as functions by design):
- `text_utils`: `normalize_text`, `canonical_key`, `canonical_comparison_text`,
  `stable_hash`, `similarity`, `slugify`, `first_words`, `remove_non_text_comparison_lines`,
  `is_toc_line`, `is_boilerplate_line`.
- `io`: `ensure_dir`, `write_json`, `write_text`.

## 11. CLI & UI

- `cli.py` — `build_parser()`, `main()`; runs `CompyEngine` and prints KPIs.
- `frontend/compy_ui.py`:
  - `class MainWindow` — the desktop window (inputs, KPI bar, results table, log).
  - `class CompareWorker(QThread)` — runs the comparison off the UI thread; emits
    `progress` / `finished_ok` / `failed`.
  - `class RichTextDelegate(QStyledItemDelegate)` — renders the V1/V2 cells as HTML so
    only the changed words are coloured on the dark table.
  - helpers: `change_record`, `_snippet_html`, `format_diff_item`, `_record_line`.
