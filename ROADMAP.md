# COMPY — MVP Roadmap (5 stages)

Principles for every stage: **section-based comparison**, **Python for extraction
& diff**, **STGpt only for explanation & summaries**, **skip unchanged content**,
**reliable > fancy**.

## MVP1 — Text comparison (small PDFs) ← current focus
Scope: small PDFs (~20–50 pages), **text/prose only**.
- Extract text from PDFs with page numbers
- Detect and structure sections (from the bookmark outline; font-size fallback)
- **Exclude tables, figures, TOC, headers/footers from the comparison**
- Match sections between V1 and V2
- Compare text section-by-section (diff), skip unchanged sections
- Generate a change report (text) and a revision-history draft (text)
- Use STGpt to summarize changes (optional; deterministic diff comes first)

Outputs: detailed comparison report (text), revision-history draft (text).

**Status: implemented.** Tables/figures are *recorded* (bounding boxes) but not
compared yet — that is MVP3/MVP4.

## MVP2 — Text comparison (large PDFs)
Scope: hundreds to ~6000 pages. Handle large PDFs efficiently, optimize section
detection/matching, chunk long sections, parallelize diffing, scale "skip
unchanged". **Decision: keep one document and stream it by *section* — do not
split into smaller PDFs.** Full plan: [docs/MVP2_PLAN.md](docs/MVP2_PLAN.md).

## MVP3 — Table comparison
Extract tables as structured data (rows/columns/cells), match tables between
versions, detect changes in values/headers/format, summarize table changes, and
fold them into the report and revision history. The MVP1 extractor already
records table bounding boxes per page to build on here.

## MVP4 — Figure / image comparison
Extract images/figures, compare by image hash, detect added/removed/changed
figures, use OCR/vision only when a figure changed, and link figure changes to
their section/page. MVP1 already records figure bounding boxes.

## MVP5 — Full MVP + export + insights
Full comparison (text + tables + figures), final detailed report, exportable
revision history (HTML/Excel/DOCX), a summary dashboard with key stats, and
production STGpt. Hardening for performance, stability, and UX.
