# MVP1 — Comparing the text of (small) PDFs

**Goal:** take two versions of a PDF and reliably list the **real text changes** —
nothing else. No tables, no figure labels, no page numbers, no table of contents.

## The hard part (the problem we had to solve)

When you "extract text" from a PDF the naive way, everything comes out mashed
together into one stream:

```
RAM ECC controllers are assigned to each...   ← real sentence (we want this)
Figure 2. RAM ECC controller                   ← a caption (junk)
DT62937V1                                       ← a drawing code (junk)
ECC wrapper   Data in   Ctrl                    ← labels inside a diagram (junk)
Introduction .................. 5               ← table-of-contents line (junk)
AN5342 - Rev 8  page 5/20                       ← page footer (junk)
```

The old attempt tried to *guess* which lines were junk using a hand-written list of
bad words (`ramecc`, `irq`, …). That only worked on one document and broke on the
next. **You can't tell prose from a diagram label after everything is flattened.**

## The fix: look at *where* things are on the page, not *what* they say

COMPY uses a smarter PDF reader (**PyMuPDF**) that knows the **position** of
everything. So instead of guessing by words, we exclude junk by **geometry**:

| Junk | How we remove it |
| --- | --- |
| Tables | Find the table's box and drop any text inside it |
| Figures / diagrams | Find the drawing/image area and drop labels inside it |
| Captions ("Figure 2.") | They start with "Figure/Table N." + a dot/dash |
| Page header & footer | They sit in the top/bottom margin band |
| Tiny labels & drawing codes | Their font is much smaller than the body text |

What's left is **real body prose** — and it works on *any* document, because boxes
and font sizes are universal, unlike a word list.

## How COMPY splits the document into sections

To compare fairly, COMPY compares **section 3.4 with section 3.4**, not page-with-page
(pages shift between versions). It finds the sections two ways:

1. **Bookmarks (best):** most ST PDFs have a built-in outline (`1`, `2`, `2.1`, …).
   COMPY just reads it — exact and free.
2. **No bookmarks (fallback):** if a PDF has none, COMPY detects headings by their
   **bigger font** + the numbered pattern (`2.1 Title`). So a V1 *with* bookmarks
   still lines up against a V2 *without* them.

Sections like **Contents**, **List of tables/figures**, and **Revision history** are
recognized and **excluded** from the comparison — they're not real content.

## How it finds the changes

- Each section gets a **fingerprint** (a hash of its cleaned text). If V1 and V2
  fingerprints match → unchanged → **skipped** instantly. Most sections don't change,
  so this is fast.
- For sections that differ, COMPY compares **word by word** and reports **every**
  edit separately (so three small edits in one paragraph = three rows, not one).

## How each change is labelled (the 3 buckets)

- 🟢 **Added** — words that are in V2 but were not in V1.
- 🔴 **Deleted** — words that were in V1 and are gone in V2.
- 🟠 **Changed** — words that exist in both but were reworded (e.g. `AN2606` → `AN2004`).

A neat detail: punctuation is separated from words before comparing, so inserting a
few words into a sentence is correctly seen as **Added** (not a confusing "Changed").
And only the **exact changed words** are highlighted — red on the old side, green on
the new side — with the rest of the sentence left plain.

## What you get out

- A **colored table** in the app (dark theme), one row per change, with the section
  number and page.
- **KPI counts**: how many Added / Deleted / Changed in total.
- The same as files on disk (`diff_report.json`, `comparison_report.html`,
  `revision_history_draft.json`, …) for sharing or feeding the next step.

## In one sentence

> MVP1 reads two PDFs, keeps only the real sentences (using their position on the
> page, not a word blacklist), lines them up section by section, and tells you
> exactly which words were added, deleted, or changed — with colors, section
> numbers, and pages.
