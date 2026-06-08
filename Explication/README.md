# Explication — COMPY in simple words

This folder explains, in plain friendly language, **what COMPY does and how**, with
no heavy jargon. It's the "explain it like I'm in a hurry" version of the project.

## What is COMPY, in one breath?

You have two versions of a big technical PDF (V1 and V2). COMPY reads both, figures
out **what actually changed in the text**, and gives you a clean list: what was
**Added**, **Deleted**, or **Changed** — with the section number and page — so you
can write the revision history without re-reading hundreds of pages by hand.

## The golden rule

**Python does the boring, exact work** (reading, splitting into sections, finding
changes). **The AI (STGpt) only writes the nice summaries later.** This keeps it
fast, cheap, and reliable — the computer never "guesses" what changed.

## Read these

- **[MVP1.md](MVP1.md)** — Comparing the *text* of small PDFs (the foundation).
- **[MVP2.md](MVP2.md)** — Making it work on *huge* PDFs (hundreds–thousands of pages).
- **[UI.md](UI.md)** — A tour of the desktop app and what every panel shows.
- **[VISUAL_DIFF.md](VISUAL_DIFF.md)** — The side-by-side "see what changed" view.

(More files will be added for MVP3 tables, MVP4 figures, MVP5 export, as we build them.)

## The 5-stage plan (where we are)

1. **MVP1 — Text, small PDFs** ✅ done
2. **MVP2 — Text, large PDFs** 🛠️ in progress (fast + light on memory)
3. **MVP3 — Tables** ⏳ next
4. **MVP4 — Figures/images** ⏳
5. **MVP5 — Full report + export + insights** ⏳
