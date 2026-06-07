# MVP2 — Making it work on *huge* PDFs (hundreds–thousands of pages)

MVP1 already compares text correctly. MVP2 is about making that **fast and light**
enough to handle a 1,000–6,000 page reference manual without crawling or running out
of memory. Same results — just built to scale.

Think of MVP1 as "it works," and MVP2 as "it works on the monster files too."

## 1. Pairing sections quickly — *indexed matching*

**Problem:** to compare, COMPY must pair each V1 section with the same V2 section.
The slow way checks every section against every other — with thousands of sections
that's millions of checks.
**Fix:** build an index (like the A–Z tabs in a dictionary) and jump straight to
"3.4" by its number. Time now grows in a straight line instead of exploding.

## 2. Only zoom in where needed — *two-level diff*

**Problem:** comparing a very long section word-by-word is expensive.
**Fix:** first compare **line by line** (cheap) to find which lines changed, then do
the careful **word-by-word** comparison only on those few lines. Like skimming to
find the changed paragraph, then reading just that paragraph closely.

## 3. The big speed win — *skip table-hunting on text pages*

**Problem:** checking a page for tables is the slowest step, and COMPY did it on
**every** page. In a manual, most pages are plain text with no tables.
**Fix:** first do a cheap check — "does this page even have any lines or graphics?"
If not, **skip the expensive table search entirely.** On a 1,000-page manual where
900 pages are pure text, that's 900 slow checks avoided. This is the single biggest
time saver.

## 4. Doing both versions at once — *parallel processing*

**Problem:** COMPY read V1, then V2, one after the other — using only one CPU core.
**Fix:** read **both versions at the same time** in two separate processes, using two
cores. (We use processes, not threads, because the PDF reader isn't thread-safe.)
**Bonus you asked for:** the app now shows **both** versions advancing together:

```
Extracting V1.pdf: page 1200/6000   |   Extracting V2.pdf: page 1100/5800
```

If a computer can't start extra processes for some reason, COMPY quietly falls back
to the one-at-a-time mode — it never breaks, just runs a bit slower.

## 5. Using less memory — *lighter data*

**Problem:** COMPY was keeping the full text of every page in memory, sometimes
stored twice. On a 6,000-page file that's a lot of RAM.
**Fix:** stop keeping the redundant raw page text (the comparison uses the cleaned
section text instead), and only keep the extra per-line font details when a PDF has
**no bookmarks** (the only time we need them). It also frees each page's temporary
data as soon as it's done with it.

## 6. Seeing the big picture — *progress + KPI rollups*

- **Live progress** so a long run isn't a frozen-looking screen — you see the page
  counter moving.
- **By-chapter rollup:** when a big document has *thousands* of changes, a flat list
  is overwhelming. COMPY groups the counts by chapter, so you instantly see
  "Chapter 4: 120 changed, Chapter 9: 3 changed" and know where to look.
- **No giant debug file by default:** the per-page dump (`pages.json`) can balloon to
  gigabytes, so it's now **off** unless you ask for it (`--debug`).

## What's intentionally left for later

- **Page-window streaming** for the *very* largest files (needs a bigger redesign,
  because splitting into sections has to see the whole document).
- **Batched AI summaries (STGpt):** grouping changes into fewer AI calls — we'll do
  this in the LLM/revision-history phase, *after* MVP2.

## One honest limitation

A few source PDFs are saved with **no spaces between some words** (e.g.
`Thehostinitialization`). COMPY repairs this when the letters have a visible gap, but
some files pack them with *no gap at all* — there's literally nothing to detect.
Good news: this never creates a **fake** change, because COMPY ignores
spacing-only differences when deciding what changed.

## In one sentence

> MVP2 keeps MVP1's exact results but makes them scale: it pairs sections instantly,
> skips slow table-hunting on plain pages, reads both versions at once on multiple
> cores (showing both page counters), and uses far less memory — so a thousand-page
> manual compares in a reasonable time without choking.
