"""Layout-aware PDF extraction for MVP1 (prose-only comparison).

The previous approach flattened each page with ``pypdf.extract_text()`` and then
tried to *guess* which lines were tables, figures, or TOC entries using hardcoded
keyword lists. That cannot generalize across documents.

This extractor uses PyMuPDF (``fitz``) instead, which exposes the *geometry* of
the page: where tables, figures (vector drawings / images), headers, and footers
physically are. We keep only text that lies in the body region and outside those
zones, so figure-internal labels and table cells never reach the comparison text.

The PDF's own bookmark outline (``get_toc``) drives section building downstream.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import List, Tuple

from .io import write_json, write_text
from .models import (
    DocumentMetadata,
    ExtractionResult,
    OutlineEntry,
    PageArtifact,
    ProseBlock,
    to_dict,
)
from .text_utils import normalize_text

# --- Tunable geometry thresholds (fractions of page height) -----------------
HEADER_BAND = 0.105   # text whose bottom is above this fraction is a running header
FOOTER_BAND = 0.955   # text whose top is below this fraction is a page footer
TINY_FONT_PT = 7.5    # drawing IDs / micro-labels (e.g. "DT62937V1") sit below this
RECT_MARGIN = 3.0     # expand exclusion rects slightly to catch edge labels
DRAW_CLUSTER_MIN_AREA = 1500.0  # ignore stray underlines; keep real diagram clusters
SUBBODY_FONT_DELTA = 0.4   # a line this much smaller than body font is sub-body
ORPHAN_MAX_WORDS = 6       # ...and this short is a figure legend / label, not prose

# A real caption is "Figure 2." / "Table 5 -" / "Table 5:" -- the number is followed
# by a separator. Prose that merely starts with "Table 5 shows ..." must be KEPT,
# so we require the separator and do not match a number followed by a word.
CAPTION_RE = re.compile(r"^\s*(figure|table)\s+\d+\s*[.:–—-]", re.IGNORECASE)
NUMBERED_TITLE_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)\s+(?P<title>.+)$")


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be extracted."""


class PdfExtractor:
    def extract(self, pdf_path: str | Path, output_dir: str | Path | None = None) -> ExtractionResult:
        path = Path(pdf_path)
        if not path.exists():
            raise PdfExtractionError(f"PDF not found: {path}")
        if path.suffix.lower() != ".pdf":
            raise PdfExtractionError(f"Expected a .pdf file, got: {path}")

        result = self._extract_with_fitz(path)

        if output_dir is not None:
            out = Path(output_dir)
            write_json(out / "metadata.json", to_dict(result.metadata))
            write_json(out / "pages.json", [to_dict(page) for page in result.pages])
            write_json(out / "outline.json", [to_dict(entry) for entry in result.outline])
            write_text(
                out / "extract_log.txt",
                f"Extracted {len(result.pages)} pages from {path.name}; "
                f"outline_available={result.outline_available}; "
                f"prose_blocks={len(result.prose_blocks)}\n",
            )

        return result

    # -- core ----------------------------------------------------------------
    def _extract_with_fitz(self, path: Path) -> ExtractionResult:
        try:
            import fitz  # type: ignore  # PyMuPDF
        except ImportError as exc:  # pragma: no cover - environment guard
            raise PdfExtractionError(
                "PyMuPDF is not installed. Run 'pip install -r requirements.txt'."
            ) from exc

        doc = fitz.open(str(path))
        pdf_meta = {str(k): str(v) for k, v in (doc.metadata or {}).items() if v}

        # Pass 1: collect body-candidate blocks per page (geometry filtering only).
        page_infos = []
        for index, page in enumerate(doc):
            table_rects = self._table_rects(page)
            figure_rects = self._figure_rects(page, fitz)
            exclusion = [self._expand(r, RECT_MARGIN) for r in (table_rects + figure_rects)]
            candidates = self._candidate_blocks(page, float(page.rect.height), exclusion)
            page_infos.append(
                {
                    "index": index,
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                    "raw_text": page.get_text("text") or "",
                    "table_rects": table_rects,
                    "figure_rects": figure_rects,
                    "candidates": candidates,
                }
            )

        body_size = self._dominant_body_size(page_infos)

        # Pass 2: drop sub-body orphan labels (figure legends), then assemble.
        pages: List[PageArtifact] = []
        prose_blocks: List[ProseBlock] = []
        for info in page_infos:
            index = info["index"]
            page_blocks: List[ProseBlock] = []
            for block in info["candidates"]:
                kept = [
                    (text, size)
                    for (text, size, words) in block["lines"]
                    if not self._is_subbody_orphan(size, words, body_size)
                ]
                if not kept:
                    continue
                page_blocks.append(
                    ProseBlock(
                        page_index=index,
                        y0=block["y0"],
                        x0=block["x0"],
                        text=" ".join(t for t, _ in kept),
                        max_size=max((s for _, s in kept), default=0.0),
                        lines=[[t, s] for t, s in kept],
                    )
                )
            prose_blocks.extend(page_blocks)

            prose_text = "\n".join(b.text for b in page_blocks)
            lines = normalize_text(prose_text).splitlines()
            pages.append(
                PageArtifact(
                    page_index=index,
                    displayed_page_number=str(index + 1),
                    raw_text=info["raw_text"],
                    normalized_text=normalize_text(info["raw_text"]),
                    prose_text=prose_text,
                    header_candidate=lines[0] if lines else "",
                    footer_candidate=lines[-1] if len(lines) > 1 else "",
                    page_width=info["width"],
                    page_height=info["height"],
                    extraction_confidence=1.0 if prose_text.strip() else 0.0,
                    table_bboxes=[[r.x0, r.y0, r.x1, r.y1] for r in info["table_rects"]],
                    figure_bboxes=[[r.x0, r.y0, r.x1, r.y1] for r in info["figure_rects"]],
                )
            )

        outline = self._parse_outline(doc)
        outline_ok = self._outline_is_reliable(outline)
        metadata = DocumentMetadata(
            document_code=str(pdf_meta.get("/Alternate_Name") or ""),
            title=str(pdf_meta.get("/Document_Title") or pdf_meta.get("title") or pdf_meta.get("/Title") or ""),
            revision=str(pdf_meta.get("/Revision") or ""),
            page_count=len(pages),
            file_name=path.name,
            pdf_metadata=pdf_meta,
        )
        doc.close()
        return ExtractionResult(
            metadata=metadata,
            pages=pages,
            outline=outline,
            prose_blocks=prose_blocks,
            outline_available=outline_ok,
            body_font_size=body_size,
        )

    # -- exclusion regions ---------------------------------------------------
    def _table_rects(self, page) -> list:
        try:
            finder = page.find_tables()
            return [_rect(page, t.bbox) for t in finder.tables]
        except Exception:
            return []

    def _figure_rects(self, page, fitz) -> list:
        rects: list = []
        # 1) Embedded raster images.
        try:
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") == 1:
                    rects.append(_rect(page, block["bbox"]))
        except Exception:
            pass
        # 2) Vector-drawing clusters (block diagrams, flowcharts).
        try:
            draw_rects = [
                fitz.Rect(d["rect"]) for d in page.get_drawings() if d.get("rect")
            ]
            rects.extend(self._cluster_rects(draw_rects, fitz))
        except Exception:
            pass
        return rects

    @staticmethod
    def _cluster_rects(rects: list, fitz, gap: float = 12.0) -> list:
        """Merge nearby drawing rects into figure-sized clusters."""
        clusters: list = []
        for raw in rects:
            r = fitz.Rect(raw)
            if r.is_empty:
                continue
            grown = fitz.Rect(r.x0 - gap, r.y0 - gap, r.x1 + gap, r.y1 + gap)
            merged = False
            for i, c in enumerate(clusters):
                if grown.intersects(c):
                    clusters[i] = c | r
                    merged = True
                    break
            if not merged:
                clusters.append(fitz.Rect(r))
        return [c for c in clusters if c.get_area() >= DRAW_CLUSTER_MIN_AREA]

    # -- body text -----------------------------------------------------------
    def _candidate_blocks(self, page, height: float, exclusion: list) -> list:
        """Geometry pass: keep body lines, drop headers/footers/captions/regions.

        Returns a list of blocks: ``{x0, y0, lines: [(text, size, words), ...]}``.
        Font-based orphan filtering happens later, once the document's dominant
        body size is known.
        """
        header_cut = height * HEADER_BAND
        footer_cut = height * FOOTER_BAND
        out: list = []
        try:
            blocks = page.get_text("dict").get("blocks", [])
        except Exception:
            return out
        for block in blocks:
            if block.get("type") != 0:
                continue
            kept: list = []
            for line in block.get("lines", []):
                lx0, ly0, lx1, ly1 = line["bbox"]
                cx, cy = (lx0 + lx1) / 2, (ly0 + ly1) / 2
                if ly1 <= header_cut or ly0 >= footer_cut:
                    continue
                if any(_contains(r, cx, cy) for r in exclusion):
                    continue
                text = "".join(s["text"] for s in line.get("spans", [])).strip()
                if not text or CAPTION_RE.match(text):
                    continue
                size = max((s.get("size", 0.0) for s in line.get("spans", [])), default=0.0)
                if size and size < TINY_FONT_PT:
                    continue
                kept.append((text, round(size, 1), len(text.split())))
            if kept:
                out.append({"x0": float(block["bbox"][0]), "y0": float(block["bbox"][1]), "lines": kept})
        return out

    @staticmethod
    def _dominant_body_size(page_infos: list) -> float:
        """Most common font size among real prose lines (weighted by length)."""
        counter: Counter = Counter()
        for info in page_infos:
            for block in info["candidates"]:
                for _text, size, words in block["lines"]:
                    if words >= 5 and size:
                        counter[size] += words
        return counter.most_common(1)[0][0] if counter else 0.0

    @staticmethod
    def _is_subbody_orphan(size: float, words: int, body_size: float) -> bool:
        """A short line in a font smaller than body text = figure legend / label."""
        if not body_size or not size:
            return False
        return size < body_size - SUBBODY_FONT_DELTA and words <= ORPHAN_MAX_WORDS

    # -- outline -------------------------------------------------------------
    def _parse_outline(self, doc) -> List[OutlineEntry]:
        entries: List[OutlineEntry] = []
        try:
            toc = doc.get_toc(simple=True)
        except Exception:
            toc = []
        for level, raw_title, page in toc:
            title = (raw_title or "").strip()
            if not title:
                continue
            number, clean_title = self._split_number(title)
            entries.append(
                OutlineEntry(
                    level=int(level),
                    number=number,
                    title=clean_title,
                    section_type=classify_section_type(title),
                    page_index=max(int(page) - 1, 0),
                )
            )
        return entries

    @staticmethod
    def _outline_is_reliable(outline: List[OutlineEntry]) -> bool:
        """Reject a PDF's structure/tag tree masquerading as a chapter outline.

        Some PDFs export their accessibility tag tree as bookmarks: dozens of
        unnumbered fragments pointing at table cells and captions (e.g. AN2V2).
        A real chapter outline has several numbered headings, so we require a
        minimum of those before trusting it.
        """
        if not outline:
            return False
        numbered = sum(1 for entry in outline if entry.number)
        return numbered >= 3

    @staticmethod
    def _split_number(title: str) -> Tuple[str, str]:
        match = NUMBERED_TITLE_RE.match(title)
        if match:
            return match.group("number"), match.group("title").strip()
        return "", title

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _expand(rect, margin: float):
        return rect.__class__(rect.x0 - margin, rect.y0 - margin, rect.x1 + margin, rect.y1 + margin)


def classify_section_type(title: str) -> str:
    stripped = title.strip()
    lowered = stripped.lower()
    if re.fullmatch(r"[A-Z]{1,4}\d{3,}", stripped):
        return "front_matter"  # bare document code on the cover
    if lowered == "contents" or "table of contents" in lowered:
        return "toc"
    if lowered.startswith("list of tables"):
        return "list_of_tables"
    if lowered.startswith("list of figures"):
        return "list_of_figures"
    if "revision history" in lowered:
        return "revision_history"
    if "legal" in lowered or "trademark" in lowered:
        return "legal_notice"
    if lowered.startswith("introduction"):
        return "introduction"
    if lowered.startswith("appendix"):
        return "appendix"
    return "main_content"


def _rect(page, bbox):
    return page.rect.__class__(bbox)


def _contains(rect, x: float, y: float) -> bool:
    return rect.x0 <= x <= rect.x1 and rect.y0 <= y <= rect.y1
