# The COMPY app — what each part shows

A quick tour of the desktop window, top to bottom, in plain words.

## Inputs (top)

- **PDF V1 / PDF V2** — pick the old and new version. As soon as you pick a file,
  the panel just below shows its **title and page count**, so you can confirm you
  grabbed the right document before running.
- **Output** — where the report files are saved (optional; the app still shows
  everything on screen even without it).
- **Compare** — runs the comparison.

## PDF info panel (under the Compare button)

Shows, for each version, the document **title** and **number of pages**, e.g.:

```
V1  How to use ECC management on STM32 MCUs  ·  20 pages
V2  How to use ECC management on STM32 MCUs  ·  23 pages
```

Handy to double-check the two files and to see at a glance that V2 grew/shrank.

## Live status

While it works, a one-line status shows the current step and — on big files —
**both versions' page progress at once**:

```
Extracting V1.pdf: page 1200/6000   |   Extracting V2.pdf: page 1100/5800
```

## Results — the "Changes" tab

- A **KPI bar**: 🟢 Added · 🔴 Deleted · 🟠 Changed · Total.
- A **colored table**, one row per change: Type, Section #, Section, Page, and the
  old vs new text. Only the **changed words** are coloured — red on the V1 side,
  green on the V2 side — the rest stays plain so the change pops out.

## Results — the "Log" tab

The same changes as plain text lines (easy to copy/paste).

## Bottom panel — processing time + KPIs

A summary strip with the **timing breakdown** and a few **at-a-glance numbers**:

```
⏱ Processing time — Extraction 02:11 min · Structuring Sections 25.0 sec · Comparing 36.0 sec · Total 03:12 min
📊 29 sections (24 compared, 5 changed) · V1 20p · V2 23p
```

- **Extraction** — reading both PDFs (usually the longest step).
- **Structuring Sections** — splitting into sections.
- **Comparing** — matching sections and finding the changes.
- **Total** — end to end.
- The second line tells you **how many sections** there are, how many were actually
  compared, how many changed, and the page counts — a quick health check of the run.

These numbers also help you *feel* the MVP2 speed-ups: on a big manual you'll see the
Extraction time stay reasonable thanks to skipping table-hunting on plain pages and
reading both versions in parallel.
