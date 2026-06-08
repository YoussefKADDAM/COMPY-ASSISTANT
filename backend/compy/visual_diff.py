"""Build the visual side-by-side model and render highlighted pages.

Turns the deterministic ``DiffItem`` list into a :class:`VisualDiff`: the changed
sections paired across versions, each with the **pixel boxes** of the changed text
on the old and new pages. The UI then renders only those pages with the boxes
baked in (green = added, red = deleted, orange = changed).

Locating text is done by matching the change's letters against the page's word
boxes (ignoring spaces/punctuation), which is robust to our space-repair; it falls
back to PyMuPDF ``search_for``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .models import DiffItem, Highlight, VisualDiff, VisualGroup
from .text_utils import canonical_key

# kind -> (fill RGB, stroke RGB), components in 0..1 for PyMuPDF.
HIGHLIGHT_COLORS = {
    "added": ((0.30, 0.80, 0.40), (0.10, 0.55, 0.20)),
    "deleted": ((0.97, 0.45, 0.45), (0.80, 0.15, 0.15)),
    "changed": ((1.00, 0.72, 0.25), (0.85, 0.50, 0.05)),
}
_MAX_RUN_WORDS = 60  # safety cap when scanning page words for a match


def build_visual_diff(
    old_pdf: str | Path,
    new_pdf: str | Path,
    diff_items: List[DiffItem],
    old_regions: "Optional[Dict[int, list]]" = None,
    new_regions: "Optional[Dict[int, list]]" = None,
) -> VisualDiff:
    """Group changes by section and locate their highlight boxes on each page.

    ``old_regions`` / ``new_regions`` map a 0-based page index to a list of
    table/figure bounding boxes; any page word inside one is ignored when
    searching, so a highlight can never land on text inside a register table.
    """
    import fitz  # type: ignore

    old_doc = fitz.open(str(old_pdf))
    new_doc = fitz.open(str(new_pdf))
    old_regions = old_regions or {}
    new_regions = new_regions or {}
    old_cache: Dict[int, tuple] = {}
    new_cache: Dict[int, tuple] = {}

    groups: Dict[str, VisualGroup] = {}
    order: List[str] = []

    for item in diff_items:
        key = item.section_number or f"{item.page_v1}|{item.page_v2}|{item.section_title}"
        group = groups.get(key)
        if group is None:
            group = VisualGroup(
                section_number=item.section_number,
                section_title=item.section_title,
                severity="minor",
                v1_page=_to_int(item.page_v1),
                v2_page=_to_int(item.page_v2),
            )
            groups[key] = group
            order.append(key)

        group.change_count += 1
        if item.severity == "major":
            group.severity = "major"

        if item.change_type in ("deleted", "changed") and item.old_change.strip():
            page = _to_int(item.page_v1)
            kind = "deleted" if item.change_type == "deleted" else "changed"
            rects = _locate(old_doc, page, item.old_prefix, item.old_change, item.old_suffix,
                            old_cache, old_regions.get(page - 1, []))
            group.v1_highlights.extend(Highlight(bbox=r, kind=kind) for r in rects)
            if rects and not group.v1_page:
                group.v1_page = page

        if item.change_type in ("added", "changed") and item.new_change.strip():
            page = _to_int(item.page_v2)
            kind = "added" if item.change_type == "added" else "changed"
            rects = _locate(new_doc, page, item.new_prefix, item.new_change, item.new_suffix,
                            new_cache, new_regions.get(page - 1, []))
            group.v2_highlights.extend(Highlight(bbox=r, kind=kind) for r in rects)
            if rects and not group.v2_page:
                group.v2_page = page

    old_doc.close()
    new_doc.close()
    return VisualDiff(
        v1_pdf=str(old_pdf),
        v2_pdf=str(new_pdf),
        groups=[groups[k] for k in order],
    )


def render_page(pdf_path: str | Path, page_index: int, highlights: List[Highlight], dpi: int = 110) -> bytes:
    """Render a single page (0-based) to PNG bytes with the highlight boxes drawn."""
    import fitz  # type: ignore

    doc = fitz.open(str(pdf_path))
    try:
        if not (0 <= page_index < doc.page_count):
            return b""
        page = doc[page_index]
        for highlight in highlights:
            bbox, kind = _highlight_parts(highlight)
            if not bbox:
                continue
            fill, stroke = HIGHLIGHT_COLORS.get(kind, HIGHLIGHT_COLORS["changed"])
            rect = fitz.Rect(bbox) + (-1, -1, 1, 1)  # pad slightly around the words
            page.draw_rect(rect, color=stroke, fill=fill, fill_opacity=0.30, width=0.6)
        return page.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()


# -- helpers -----------------------------------------------------------------
def _locate(
    doc,
    page_1based: int,
    prefix: str,
    change: str,
    suffix: str,
    cache: Dict[int, tuple],
    regions: "Optional[list]" = None,
) -> List[List[float]]:
    """Word boxes for the *changed* text on a page, anchored by its context.

    We match against the page's concatenated, letters-only text (ignoring spaces
    and punctuation). Words inside ``regions`` (table/figure boxes) are dropped
    first, so a highlight can never land on a table cell; the surrounding
    ``prefix``/``suffix`` then pins the right body occurrence. For long spans we
    fall back to progressively shorter leads so big deletions still highlight.
    """
    if not (1 <= page_1based <= doc.page_count):
        return []
    core = canonical_key(change)
    if not core:
        return []

    index = page_1based - 1
    data = cache.get(index)
    if data is None:
        try:
            words = doc[index].get_text("words")  # (x0,y0,x1,y1,word,block,line,wno)
        except Exception:
            words = []
        if regions:
            words = [w for w in words if not _inside_any(w, regions)]
        keys = [canonical_key(w[4]) for w in words]
        owner: List[int] = []
        for word_index, key in enumerate(keys):
            owner.extend([word_index] * len(key))
        data = (words, owner, "".join(keys))
        cache[index] = data
    words, owner, page_str = data
    if not page_str:
        return []

    pre = canonical_key(prefix)
    post = canonical_key(suffix)

    # 1) Context-anchored exact match (disambiguates table vs body).
    for target, core_offset in ((pre + core + post, len(pre)), (pre + core, len(pre)),
                                (core + post, 0), (core, 0)):
        pos = page_str.find(target)
        if pos != -1:
            return _boxes(words, owner, pos + core_offset, pos + core_offset + len(core))

    # 2) Long / cross-page change: highlight as much of the lead as we can find.
    change_keys = [k for k in (canonical_key(t) for t in change.split()) if k]
    for take in (len(change_keys) * 3 // 4, len(change_keys) // 2, 12, 6, 3):
        if take <= 0:
            continue
        lead = "".join(change_keys[:take])
        if not lead:
            continue
        for target, off in ((pre + lead, len(pre)), (lead, 0)):
            pos = page_str.find(target)
            if pos != -1:
                return _boxes(words, owner, pos + off, pos + off + len(lead))
    return []


def _inside_any(word, regions: list) -> bool:
    """True if the word's center falls inside any table/figure box."""
    cx = (float(word[0]) + float(word[2])) / 2
    cy = (float(word[1]) + float(word[3])) / 2
    for r in regions:
        if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
            return True
    return False


def _boxes(words: list, owner: List[int], char_start: int, char_end: int) -> List[List[float]]:
    """Boxes of the words covering the character span [char_start, char_end)."""
    char_start = max(0, char_start)
    char_end = min(len(owner), char_end)
    indices = sorted({owner[i] for i in range(char_start, char_end)})
    return [[float(words[k][0]), float(words[k][1]), float(words[k][2]), float(words[k][3])]
            for k in indices]


def _highlight_parts(highlight) -> tuple:
    if isinstance(highlight, dict):
        return highlight.get("bbox"), highlight.get("kind", "changed")
    return getattr(highlight, "bbox", None), getattr(highlight, "kind", "changed")


def _to_int(value) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return 0
