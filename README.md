# COMPY Assistant

COMPY is an internal STMicroelectronics TechDoc assistant that compares two
versions of a technical PDF (Application Notes / Reference Manuals) and drafts a
**revision history**. Python does the deterministic extraction, sectioning, and
diffing; STGpt is used only to summarize the changes that Python has already
found.

This repository is the **MVP1** build: **prose-only text comparison on small
PDFs**. Tables, figures, and the table of contents are detected and deliberately
**excluded** from the comparison so that the diff reflects genuine wording
changes only. See [ROADMAP.md](ROADMAP.md) for the 5-stage plan.

## The key idea

Older attempts flattened the PDF with `pypdf.extract_text()` and then tried to
guess "is this prose, a table, a figure label, or a TOC entry?" from the flat
string using hardcoded keyword lists. That cannot generalize.

COMPY Assistant instead extracts with **PyMuPDF (layout-aware)** and excludes
non-prose **by geometry**: tables and figures are removed by their bounding
boxes, headers/footers by position, and the section structure comes from the
PDF's own bookmark **outline** (with a font-size fallback when a PDF has no
bookmarks). See [docs/MVP1_APPROACH.md](docs/MVP1_APPROACH.md).

## Docs

- [Explication/](Explication/) — **plain-language** explanations of each MVP (start here)
- [docs/CLASS_REFERENCE.md](docs/CLASS_REFERENCE.md) — class & function map
- [ARCHITECTURE.md](ARCHITECTURE.md) — module responsibilities
- [docs/INTEGRATION.md](docs/INTEGRATION.md) — embedding via `CompyEngine`
- [ROADMAP.md](ROADMAP.md) · [docs/MVP1_APPROACH.md](docs/MVP1_APPROACH.md) · [docs/MVP2_PLAN.md](docs/MVP2_PLAN.md)

## Setup

```powershell
python -m pip install -r requirements.txt
```

Dependencies: `PyMuPDF` (extraction), `PySide6` (desktop UI). `pypdf` is kept as
a lightweight metadata fallback.

## CLI

```powershell
python -m backend.compy.cli "path\to\v1.pdf" "path\to\v2.pdf" --output-dir outputs\run1
```

By default no LLM API is called. To test OpenAI summaries:

```powershell
$env:OPENAI_API_KEY = "..."
python -m backend.compy.cli "v1.pdf" "v2.pdf" --llm-provider openai
```

The production STGpt integration uses the same `LLMClient` wrapper with
`--llm-provider stgpt` and a compatible base URL/config.

## Desktop UI

```powershell
python frontend\compy_ui.py
```

## Tests

```powershell
python -m unittest discover -s tests
```

Sample documents live in `PDF Tests/` (three V1/V2 pairs). The integration test
runs the full pipeline against `AV1.pdf` and asserts that no figure labels,
captions, footers, or TOC lines reach the comparison text.

## Change classification & KPIs

Every edit is detected and classified into three types (the KPI buckets):

- **Added** (green) — text in V2 that was not in V1
- **Deleted** (red) — text in V1 that is no longer in V2
- **Changed** (orange) — text reworded between versions

Classification is **token-level**: inserting words into an otherwise-unchanged
sentence is **Added** (not Changed); removing words is **Deleted**; a genuine
substitution (e.g. `AN2606` → `AN2004`) is **Changed**.

Changes are reported **per edit**, not per section, so several edits inside the
same paragraph are listed separately. Each row carries the **section number** and
the **page** it occurs on. In both the desktop table (dark theme) and the HTML
report, **only the changed words are coloured** — red on the V1 side, green on the
V2 side — with the surrounding context left neutral. `kpi_summary.json` holds the
totals.

## Output artifacts (per run)

- `v1/`, `v2/` — per-document `metadata.json`, `pages.json`, `outline.json`,
  `normalized_document.json`, `section_index.json`
- `section_matches.json` — how sections aligned between versions
- `diff_report.json` — every change with type, section #, page, old/new snippet
- `kpi_summary.json` — counts of added / deleted / changed
- `revision_history_draft.json` — the user-facing revision history
- `comparison_report.html` — colored table + KPI cards
