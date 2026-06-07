# MVP1 — How "real text vs tables/TOC" is solved

## The problem

A technical PDF, once flattened to a plain text stream, interleaves real prose
with content that *looks* like text but is not:

- **Figure internals** — a diagram's labels (`ECC wrapper`, `ramecc_hclk`,
  `Ctrl`, `Data in`) and its drawing ID (`DT62937V1`).
- **Captions** — `Figure 2. ...`, `Table 5. ...`.
- **Table cells** — numeric/register rows.
- **Table of contents / lists** — dot-leader lines (`Introduction ....... 5`).
- **Headers / footers** — running title, `AN5342 - Rev 8 page 5/20`.

The previous approach extracted with `pypdf.extract_text()` (which destroys
layout) and then tried to *reconstruct* what was prose using hardcoded keyword
lists (`ramecc`, `irq`, `bootloadercommandset`, …). It worked on one document and
broke on the next. **You cannot reliably recover structure after the PDF has been
flattened.**

## The solution: exclude by geometry, not vocabulary

Extraction uses **PyMuPDF (`fitz`)**, which knows *where* things are on the page.

### 1. Exclusion regions (per page) — `backend/compy/extractor.py`
- **Tables** via `page.find_tables()` → bounding boxes.
- **Figures** via raster image blocks + clustered vector drawings
  (`page.get_drawings()`), extended to swallow the figure's labels.
- **Headers/footers** via top/bottom bands.

Any text whose bbox falls inside a table/figure region or a header/footer band is
dropped. On the sample PDF, `find_tables()` returns the figure-diagram rectangles
and *every* figure label sits inside them, so the labels vanish without naming a
single one.

### 2. Body prose detection
Remaining text is kept if it is near the document's **dominant body font size**.
- Captions (`Figure N.` / `Table N.` followed by a separator) are dropped — but a
  sentence that merely *mentions* a table (`Table 5 shows the word size…`) is
  **kept**, because the number is followed by a word, not a separator.
- Tiny fonts (drawing IDs) and short sub-body "orphan" lines (figure legends) are
  dropped by font size, not by keyword.

### 3. Sections from the bookmark outline — `OutlineSectionBuilder`
`doc.get_toc()` gives exact section numbers, titles, and pages. Each bookmark
becomes one section; boundaries come from matching each heading to its block in
the prose stream. `Contents`, `List of tables`, `List of figures`,
`Revision history`, and the cover are classified and marked
`comparison_enabled = False`.

### 4. Font-size fallback when there is no outline — `FontHeadingSectionBuilder`
Some PDFs ship without bookmarks (e.g. `AV2.pdf`). Headings are then detected on
the cleaned prose by font size + the numbered-heading pattern (a number on its
own line is merged with the following title line). This keeps a bookmarked V1 and
an un-bookmarked V2 aligned by section number.

### 5. Thin, generic safety net — `text_utils.remove_non_text_comparison_lines`
A last, document-agnostic pass drops only unambiguous structural noise:
dot-leader TOC lines, pure-numeric table rows, generic page footers, and bare
enumeration markers (`1.` `2.`). It contains **no document vocabulary**.

### 6. Running-header echoes — `heading_echo_keys`
Tagged PDFs render a section title twice (the visible heading + a body-size
running header). The echo is an exact duplicate of the title, so body lines
matching a known heading title are dropped.

## What still leaks (known MVP1 limitations)
- **Table footnotes / notes** in a *gridless* table that `find_tables()` cannot
  detect may leak as body text on a no-bookmark PDF. This is table content and is
  addressed by **MVP3**.

## Verifying
```powershell
python -m backend.compy.cli "PDF Tests/AV1.pdf" "PDF Tests/AV2.pdf" --output-dir outputs/av_check
python -m unittest discover -s tests
```
The integration test asserts no figure labels, captions, footers, or TOC lines
reach the comparison text across the sample documents.
