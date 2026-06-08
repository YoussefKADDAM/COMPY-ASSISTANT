# Visual Diff — see exactly what changed, side by side

After a comparison, the **Visual Diff** tab lets you *look* at the changes on the real
pages instead of reading a list. It shows **only the pages that changed**, old on the
left and new on the right, with the changed text **highlighted in color**.

## What you see

- 🟢 **Green** = text that was **added** in the new version.
- 🔴 **Red** = text that was **deleted** from the old version.
- 🟠 **Orange** = text that was **modified** (reworded).
- A **navigator** on the left lists every changed section, with a **Major/Minor** badge
  so you know which changes matter most.
- **Prev / Next** buttons (and clicking a navigator item) jump you straight to each change.
- **⛶ Full screen / Restore** buttons give the two pages the whole screen when you need it.

The highlight is **context-aware**: if the same word appears both in a register table and
in the body text, COMPY highlights the one in the body (where the real change is), by
matching the words *around* the change, not just the word itself.

So the experience is: *"Here are only the pages that changed, and here is exactly what
changed on them."*

## How it works (in simple words)

1. COMPY already knows **what** changed (the exact words) and **where** (section + page),
   from the normal comparison.
2. For each change, it finds the **position of those words on the page** by matching the
   change's letters against the page's word boxes (this still works even when the PDF has
   weird spacing).
3. It **renders only the changed pages** to images and **paints the colored boxes** right
   onto them.
4. The app shows the old page and the new page next to each other, and lets you flip
   through the changes.

Pages are rendered **on demand** (only when you open a change) and cached, so even a huge
document stays snappy — it never renders the thousands of pages that didn't change.

## Major vs Minor (importance)

Each change gets a quick importance tag:

- **Major** — a number/value changed (e.g. `AN2606 → AN2004`, a voltage, a size), or a
  whole sentence/section was added or removed.
- **Minor** — a small wording tweak (a word or two).

This helps you focus on the changes that actually matter and skim past the trivial ones.

## What's coming next (phase 2)

- 🔵 **Blue = moved / reordered** — when a paragraph wasn't really changed, just moved to
  a different place. (Needs extra matching, so it's a follow-up.)
- Synchronized scrolling and zoom, jump-to-next-change shortcuts, and exporting the
  visual comparison.

## In one sentence

> The Visual Diff tab renders only the pages that changed, side by side, and highlights
> the exact added (green), deleted (red), and modified (orange) words right on the page —
> with a Major/Minor tag and quick navigation — so you *see* the changes instead of
> reading about them.
