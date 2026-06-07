# Agent / contributor guidelines

Working notes for anyone (human or AI) extending COMPY Assistant.

## Ground rules

1. **MVP1 is prose-only.** Do not add table or figure *comparison* — that is
   MVP3/MVP4. You may extend table/figure *detection* (bounding boxes) since the
   extractor already records them.
2. **Exclude by geometry, not vocabulary.** Never reintroduce hardcoded,
   document-specific keyword lists (e.g. `ramecc`, `bootloadercommandset`) to
   decide what is prose. Use position, font size, and structure. If you need a
   new filter, make it generic and explain why in `docs/MVP1_APPROACH.md`.
3. **Deterministic first.** Python finds changes; the LLM only summarizes them.
   Do not move comparison logic into the LLM.
4. **Both V1 and V2 must extract symmetrically.** A change that helps one
   document but not the other creates false diffs. Test against a bookmarked PDF
   (`AV1.pdf`) *and* an un-bookmarked one (`AV2.pdf`).

## Where things live

- Extraction / geometry filtering → `backend/compy/extractor.py`
- Section building (outline + font fallback) → `backend/compy/normalizer.py`
- Generic text helpers → `backend/compy/text_utils.py`
- Matching / diffing / reporting → `matcher.py`, `diff_engine.py`, `reporting.py`

## Before you commit

```powershell
python -m unittest discover -s tests
python -m backend.compy.cli "PDF Tests/AV1.pdf" "PDF Tests/AV2.pdf" --output-dir outputs/check
```

Then sanity-check `outputs/check/diff_report.json`: the reported changes should
be real wording changes, not figure labels, captions, footers, or TOC lines.

## Tuning knobs (extractor constants)

`HEADER_BAND`, `FOOTER_BAND`, `TINY_FONT_PT`, `RECT_MARGIN`,
`DRAW_CLUSTER_MIN_AREA`, `SUBBODY_FONT_DELTA`, `ORPHAN_MAX_WORDS`, and the
`BODY_MAX_DELTA` / `HEADING_FONT_DELTA` in `normalizer.py`. Change one at a time
and re-run the integration test.

## Known limitations (MVP1)

- Table footnotes inside a *gridless* table on a no-bookmark PDF can leak as
  prose. Acceptable for MVP1; resolved by MVP3 table detection.
