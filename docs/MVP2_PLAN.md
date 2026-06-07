# MVP2 Plan — Text comparison on large PDFs

## Context

MVP1 compares small PDFs (~20–50 pages) section-by-section. MVP2 must scale that
to **Reference Manuals of hundreds to ~6000 pages** while keeping the comparison
reliable and the STGpt cost low.

## The key decision: whole document vs. split into smaller PDFs

**Recommendation: keep one document, stream it by *section* — do NOT split the
PDF into smaller files.**

Why not split into sub-PDFs:
- The bookmark **outline**, **section numbering**, and **cross-references** span
  the whole document. Splitting breaks them and re-introduces boundary problems.
- The **section is already the unit of comparison.** We never feed the whole
  document to the diff or to STGpt at once — each section is compared on its own.
  The "chunking" the infographic asks for already exists *logically* (by section),
  so we don't need to chunk *physically* (by file).
- Splitting adds I/O, temp files, and re-merge complexity for no benefit.

So "divide into smaller pieces" = **divide by section (logical)**, not by file.
Physical page-windowing is kept only as a memory fallback (see Risks).

The real work in MVP2 is therefore **performance and robustness at scale**, not a
new architecture.

## Progress

Implemented so far (needs validation on large samples):
- ✅ **Indexed O(n) matching** (item 1) — number/title via dict lookups; similarity
  only for residuals.
- ✅ **Two-level diff** (item 3) — long sections diff by line first, then word-diff
  changed lines (guarded; normal sections keep the existing word-level path).
- ✅ **Progress callbacks** (item 4, partial) — `pipeline.run(..., progress=cb)` now
  reports **page-level** extraction progress (`page 1200/6000`); UI + CLI show it.
- ✅ **Glued-word recovery** (item 6) — line text rebuilt from per-character
  positions (`rawdict`). Fixes the AN2V2 "Thehostinitialization" problem.
- ✅ **Per-page speed** — `find_tables()` (the main per-page cost) now runs **only
  on pages with vector graphics/images**; pure-prose pages skip it. This is the key
  win on thousand-page manuals.
- ✅ **Opt-in `pages.json`** (item 2, partial) — the huge per-page artifact is only
  written with `--debug` / `compare(..., debug=True)`; other artifacts always write.
- ✅ **KPI rollups** (item 7) — `kpi_by_chapter` + `kpi_by_chapter.json` + a
  "By chapter" table in the HTML report.

Remaining: deeper streamed/low-memory extraction (drop per-page `raw_text`,
page-window mode), process-pool parallelism (item 4), batched STGpt (item 5).

## Work items

### 1. Indexed section matching (the main bottleneck) — `matcher.py`
Today `_best_match` computes text similarity against *every* candidate → O(n²)
`SequenceMatcher` calls. At 2000+ sections this is the dominant cost.
- Build lookup indexes for new sections: by canonical **number** and by canonical
  **title**. Match old→new with O(1) dict hits first.
- Only the residual unmatched sections (a small set) fall back to similarity,
  and even then restrict candidates to the same hierarchy level / nearby pages.
- Target: matching becomes ~O(n).

### 2. Streamed, lower-memory extraction — `extractor.py`, `pipeline.py`
- Process pages in a streaming loop; after sectioning, **drop page dictionaries**
  and keep only `Section` objects in memory.
- Make the big debug artifacts (`pages.json`) **opt-in** (`--debug`); they are
  unusable at 6000 pages.
- Optionally extract V1 and V2 **in parallel processes**.

### 3. Two-level diff for very long sections — `diff_engine.py`
A single section can span many pages. Word-level `SequenceMatcher` over a huge
section is O(n²) in memory.
- First diff at **line/paragraph** granularity (fast), then run the existing
  word-level diff only on the changed lines. Preserves per-edit granularity while
  bounding cost.

### 4. Parallelism + progress — `pipeline.py`
- Diff changed sections in a process pool (embarrassingly parallel).
- Emit progress callbacks (pages extracted, sections matched, sections diffed) so
  the UI shows a real progress bar.

### 5. Scaled, batched STGpt summarization — `llm.py`
- Summarize **only changed sections** (already true), but **batch** several small
  changes per request and cap tokens per call to control cost/latency.
- Add simple retry/backoff for long runs.

### 6. Extraction-quality: glued-word recovery — `extractor.py`
Some source PDFs (e.g. AN2V2) encode text without spaces
(`Thehostinitialization`), which inflates the diff. Insert a space between
adjacent spans when their bounding boxes show a gap but no space character. This
improves diff precision on imperfect source PDFs and matters more at scale.

### 7. KPIs at scale
- Keep the Added/Deleted/Changed KPI summary; add per-chapter rollups and an
  overall change-density metric (changes per 100 pages) for the dashboard.

## Verification
- Benchmark on a real large RM (target: a few hundred pages first, then the
  largest available). Measure wall-clock for extract / match / diff and peak RAM.
- Assert prose purity still holds (no tables/figures/TOC) on a large sample.
- Confirm unchanged sections are skipped (most of a large doc) and only genuine
  changes are reported, with correct section #, page, and type.
- Add a perf regression test with a synthetic large section set for the matcher.

## Risks / fallbacks
- **Memory** on the very largest PDFs: if peak RAM is too high, add an optional
  page-window streaming mode (process N pages at a time, accumulate sections).
  This is the only place physical chunking is justified.
- **Bad/malformed outlines** are already handled by the font fallback; verify it
  stays O(n) and accurate at scale.
- **find_tables cost** on thousands of pages may be slow; allow disabling it per
  page when no drawings/vector content are present.
