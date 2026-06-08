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


def build_visual_diff(old_pdf: str | Path, new_pdf: str | Path, diff_items: List[DiffItem]) -> VisualDiff:
    """Group changes by section and locate their highlight boxes on each page."""
    import fitz  # type: ignore

    old_doc = fitz.open(str(old_pdf))
    new_doc = fitz.open(str(new_pdf))
    old_cache: Dict[int, list] = {}
    new_cache: Dict[int, list] = {}

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
            rects = _locate(old_doc, page, item.old_change, old_cache)
            group.v1_highlights.extend(Highlight(bbox=r, kind=kind) for r in rects)
            if rects and not group.v1_page:
                group.v1_page = page

        if item.change_type in ("added", "changed") and item.new_change.strip():
            page = _to_int(item.page_v2)
            kind = "added" if item.change_type == "added" else "changed"
            rects = _locate(new_doc, page, item.new_change, new_cache)
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
def _locate(doc, page_1based: int, text: str, cache: Dict[int, list]) -> List[List[float]]:
    """Per-word boxes for ``text`` on the given (1-based) page; [] if not found."""
    if not (1 <= page_1based <= doc.page_count):
        return []
    target = canonical_key(text)
    if not target:
        return []
    index = page_1based - 1
    words = cache.get(index)
    if words is None:
        try:
            words = doc[index].get_text("words")  # (x0,y0,x1,y1,word,block,line,wno)
        except Exception:
            words = []
        cache[index] = words

    keys = [canonical_key(w[4]) for w in words]
    run = _find_run(keys, target)
    if run is not None:
        start, end = run
        return [[float(words[k][0]), float(words[k][1]), float(words[k][2]), float(words[k][3])]
                for k in range(start, end + 1) if keys[k]]

    # Fallback: PyMuPDF's own search (works when the text matches the PDF verbatim).
    try:
        for rect in doc[index].search_for(text[:120]):
            return [[rect.x0, rect.y0, rect.x1, rect.y1]]
    except Exception:
        pass
    return []


def _find_run(keys: List[str], target: str) -> Optional[tuple]:
    """Smallest run of consecutive words whose joined letters equal `target`."""
    n = len(keys)
    for start in range(n):
        if not keys[start]:
            continue
        acc = ""
        for end in range(start, min(n, start + _MAX_RUN_WORDS)):
            acc += keys[end]
            if acc == target:
                return start, end
            if len(acc) >= len(target):
                break
    return None


def _highlight_parts(highlight) -> tuple:
    if isinstance(highlight, dict):
        return highlight.get("bbox"), highlight.get("kind", "changed")
    return getattr(highlight, "bbox", None), getattr(highlight, "kind", "changed")


def _to_int(value) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return 0
