"""Document normalization and section building."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from .extractor import classify_section_type
from .io import write_json
from .models import (
    Document,
    ExtractionResult,
    OutlineEntry,
    PageArtifact,
    ProseBlock,
    Section,
    to_dict,
)
from .text_utils import (
    canonical_comparison_text,
    canonical_key,
    combined_text,
    is_toc_line,
    normalize_text,
    remove_non_text_comparison_lines,
    slugify,
    stable_hash,
)


HEADING_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)(?:[.)]?\s+)(?P<title>[A-Z0-9][^\n]{2,160})$")

def assemble_body(items: "list[tuple[int, str]]") -> "tuple[str, list[list]]":
    """Filter body pieces and keep their page numbers aligned with the text.

    ``items`` is a list of ``(page_number, text)`` pieces in reading order.
    Returns ``(normalized_text, page_map)`` where ``page_map`` is a list of
    ``[page_number, text]`` for the surviving pieces, so the diff engine can map
    any changed word back to the page it appears on.
    """
    page_map: list[list] = []
    for page, text in items:
        filtered = remove_non_text_comparison_lines(text)
        if filtered.strip():
            page_map.append([page, filtered])
    normalized = "\n".join(text for _page, text in page_map)
    return normalized, page_map


def heading_echo_keys(headings) -> set[str]:
    """Canonical keys of heading titles, used to drop running-header echoes.

    Tagged PDFs often render a section title twice: once as the visible heading
    and once as a body-size running header at the top of each page. The echo is
    an exact duplicate of the title, so we drop body lines that match it. Short
    titles are skipped to avoid removing legitimate one-word sentences.
    """
    keys: set[str] = set()
    for number, title in headings:
        # Running headers may show the title without its "Appendix X" prefix.
        stripped = re.sub(r"^appendix\s+[A-Za-z0-9]+\s+", "", title, flags=re.IGNORECASE)
        for variant in (title, stripped, f"{number} {title}" if number else title):
            key = canonical_key(variant)
            if len(key) >= 6:
                keys.add(key)
    return keys


# Section types that exist in the document but must NOT be diffed as prose.
NON_COMPARISON_TYPES = {
    "toc",
    "list_of_tables",
    "list_of_figures",
    "revision_history",
    "legal_notice",
    "front_matter",
}


class DocumentNormalizer:
    def __init__(
        self,
        section_builder: "SectionBuilder | None" = None,
        outline_builder: "OutlineSectionBuilder | None" = None,
        font_builder: "FontHeadingSectionBuilder | None" = None,
    ) -> None:
        self.section_builder = section_builder or SectionBuilder()
        self.outline_builder = outline_builder or OutlineSectionBuilder()
        self.font_builder = font_builder or FontHeadingSectionBuilder()

    def normalize(
        self,
        document_id: str,
        source_pdf: str,
        extraction: ExtractionResult,
        output_dir: str | Path | None = None,
    ) -> Document:
        pages = extraction.pages
        if extraction.outline_available:
            sections = self.outline_builder.build(
                extraction.outline, extraction.prose_blocks, extraction.body_font_size
            )
        else:
            # No bookmark outline: detect headings by font size on the geometry-cleaned
            # prose blocks. Only if that finds nothing do we use the plain-text regex.
            sections = self.font_builder.build(extraction.prose_blocks, extraction.body_font_size)
            if not sections:
                fallback_pages = [
                    replace(page, normalized_text=page.prose_text or page.normalized_text)
                    for page in pages
                ]
                sections = self.section_builder.build_sections(fallback_pages)

        document = Document(
            document_id=document_id,
            source_pdf=source_pdf,
            document_metadata=extraction.metadata,
            outline_available=extraction.outline_available,
            pages=pages,
            sections=sections,
        )

        if output_dir is not None:
            out = Path(output_dir)
            write_json(out / "normalized_document.json", self.document_payload(document))
            write_json(out / "section_index.json", [to_dict(section) for section in sections])

        return document

    @staticmethod
    def document_payload(document: Document) -> dict:
        payload = to_dict(document)
        payload.pop("pages", None)
        return payload


class OutlineSectionBuilder:
    """Build sections deterministically from the PDF bookmark outline.

    Each outline entry becomes one section. Section boundaries come from matching
    each heading to its block in the geometry-filtered prose stream, so nested
    headings and multiple sections per page are handled without regex guessing.
    """

    # A body block whose font is at least this much larger than body text is a
    # heading/title/banner, not prose, and is kept out of section bodies.
    BODY_MAX_DELTA = 1.5

    def build(
        self,
        outline: list[OutlineEntry],
        prose_blocks: list[ProseBlock],
        body_size: float = 0.0,
    ) -> list[Section]:
        if not outline:
            return []
        anchors = self._anchors(outline, prose_blocks)
        heading_keys = heading_echo_keys(
            (entry.number, entry.title) for entry in outline
        )
        n = len(prose_blocks)
        sections: list[Section] = []
        seen_ids: set[str] = set()

        for index, entry in enumerate(outline):
            start_idx, matched = anchors[index]
            next_start = anchors[index + 1][0] if index + 1 < len(anchors) else n
            if start_idx is None:
                body_blocks: list[ProseBlock] = []
            else:
                body_from = start_idx + (1 if matched else 0)
                body_blocks = prose_blocks[body_from:next_start] if next_start > body_from else []

            items = [
                (block.page_index + 1, block.text)
                for block in body_blocks
                if self._is_body(block, body_size) and canonical_key(block.text) not in heading_keys
            ]
            assembled = "\n".join(text for _page, text in items).strip()
            normalized, page_map = assemble_body(items)
            comparison_text = canonical_key(normalized)

            number = entry.number
            full_title = f"{number} {entry.title}".strip() if number else entry.title
            section_id = self._unique_id(number or entry.title, index, seen_ids)
            page_start = entry.page_index + 1
            page_end = (
                outline[index + 1].page_index + 1
                if index + 1 < len(outline)
                else (body_blocks[-1].page_index + 1 if body_blocks else page_start)
            )
            comparison_enabled = (
                entry.section_type not in NON_COMPARISON_TYPES and bool(normalized.strip())
            )
            sections.append(
                Section(
                    section_id=section_id,
                    number=number,
                    title=entry.title,
                    full_title=full_title,
                    level=entry.level,
                    parent_section_id=self._parent_id(number),
                    section_type=entry.section_type,
                    page_start=page_start,
                    page_end=page_end,
                    order_index=index,
                    raw_text=assembled,
                    normalized_text=normalized,
                    comparison_enabled=comparison_enabled,
                    normalized_text_hash=stable_hash(comparison_text),
                    text_length=len(normalized),
                    word_count=len(normalized.split()),
                    page_map=page_map,
                )
            )
        return sections

    def _anchors(self, outline: list[OutlineEntry], blocks: list[ProseBlock]) -> list[tuple[int | None, bool]]:
        anchors: list[tuple[int | None, bool]] = []
        cursor = 0
        n = len(blocks)
        for entry in outline:
            heading_key = canonical_key(f"{entry.number} {entry.title}" if entry.number else entry.title)
            found: int | None = None
            if len(heading_key) >= 3:
                j = cursor
                while j < n:
                    block_key = canonical_key(blocks[j].text)
                    if block_key.startswith(heading_key) and blocks[j].page_index >= entry.page_index - 1:
                        found = j
                        break
                    j += 1
            if found is not None:
                anchors.append((found, True))
                cursor = found + 1
            else:
                k = cursor
                while k < n and blocks[k].page_index < entry.page_index:
                    k += 1
                anchors.append((k, False))
                cursor = max(cursor, k)
        return anchors

    @staticmethod
    def _unique_id(base: str, index: int, seen: set[str]) -> str:
        section_id = "sec_" + slugify(base, str(index))
        if section_id in seen:
            section_id = f"{section_id}_{index}"
        seen.add(section_id)
        return section_id

    @staticmethod
    def _parent_id(number: str) -> str:
        if "." not in number:
            return ""
        return "sec_" + slugify(number.rsplit(".", 1)[0], "parent")

    @classmethod
    def _is_body(cls, block: ProseBlock, body_size: float) -> bool:
        if not body_size or not block.max_size:
            return True
        return block.max_size < body_size + cls.BODY_MAX_DELTA


class FontHeadingSectionBuilder:
    """Build sections when the PDF has no bookmark outline.

    Headings are detected on the geometry-cleaned prose blocks by font size and
    the numbered-heading pattern (no document-specific vocabulary). This keeps the
    no-outline path almost as reliable as the outline path, so a V1 with bookmarks
    still aligns cleanly against a V2 that lacks them.
    """

    NUMBERED_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)\s+(?P<title>.+)$")
    NUMBER_ONLY_RE = re.compile(r"^\d+(?:\.\d+)*\.?$")
    HEADING_FONT_DELTA = 0.6  # a line this much larger than body font is heading-sized
    # Unnumbered headings we trust by font size (front/back matter only, which keeps
    # banners and callouts like "NOTE:" from being mistaken for headings).
    UNNUMBERED_TYPES = {"introduction", "appendix", "toc", "list_of_tables", "list_of_figures", "revision_history"}

    def build(self, prose_blocks: list[ProseBlock], body_size: float) -> list[Section]:
        lines: list[tuple[int, str, float]] = []
        for block in prose_blocks:
            line_items = block.lines or [[block.text, block.max_size]]
            for text, size in line_items:
                lines.append((block.page_index, text, float(size)))
        if not lines:
            return []

        # heading = (heading_line_idx, body_start_idx, number, title, section_type)
        headings: list[tuple[int, int, str, str, str]] = []
        i, n = 0, len(lines)
        while i < n:
            _pg, text, size = lines[i]
            parsed = None
            body_start = i + 1
            if self._is_heading_font(size, text, body_size):
                heading_text = text.strip()
                # A number on its own line ("2.1 ") joins the title line that follows.
                if (
                    self.NUMBER_ONLY_RE.match(heading_text)
                    and i + 1 < n
                    and self._is_heading_font(lines[i + 1][2], lines[i + 1][1], body_size)
                ):
                    heading_text = heading_text.rstrip(".") + " " + lines[i + 1][1].strip()
                    body_start = i + 2
                parsed = self._classify_heading(heading_text)
            if parsed:
                headings.append((i, body_start, *parsed))
                i = body_start
            else:
                i += 1

        if not headings:
            return []

        heading_keys = heading_echo_keys((h[2], h[3]) for h in headings)
        sections: list[Section] = []
        seen_ids: set[str] = set()
        for order, (start_idx, body_start, number, title, stype) in enumerate(headings):
            end = headings[order + 1][0] if order + 1 < len(headings) else n
            items = [
                (lines[j][0] + 1, lines[j][1])
                for j in range(body_start, end)
                if lines[j][2] < body_size + OutlineSectionBuilder.BODY_MAX_DELTA
                and canonical_key(lines[j][1]) not in heading_keys
            ]
            body = "\n".join(text for _page, text in items).strip()
            normalized, page_map = assemble_body(items)
            comparison_text = canonical_key(normalized)
            page_start = lines[start_idx][0] + 1
            page_end = lines[end - 1][0] + 1 if end > body_start else page_start
            full_title = f"{number} {title}".strip() if number else title
            sections.append(
                Section(
                    section_id=OutlineSectionBuilder._unique_id(number or title, order, seen_ids),
                    number=number,
                    title=title,
                    full_title=full_title,
                    level=number.count(".") + 1 if number else 1,
                    parent_section_id=OutlineSectionBuilder._parent_id(number),
                    section_type=stype,
                    page_start=page_start,
                    page_end=page_end,
                    order_index=order,
                    raw_text=body,
                    normalized_text=normalized,
                    comparison_enabled=stype not in NON_COMPARISON_TYPES and bool(normalized.strip()),
                    normalized_text_hash=stable_hash(comparison_text),
                    text_length=len(normalized),
                    word_count=len(normalized.split()),
                    page_map=page_map,
                )
            )
        return sections

    def _is_heading_font(self, size: float, text: str, body: float) -> bool:
        return bool(size) and size >= body + self.HEADING_FONT_DELTA and not is_toc_line(text.strip())

    def _classify_heading(self, heading_text: str) -> tuple[str, str, str] | None:
        stripped = heading_text.strip()
        if is_toc_line(stripped):
            return None
        match = self.NUMBERED_RE.match(stripped)
        if match:
            title = match.group("title").strip()
            if title and len(title.split()) <= 12 and not title.endswith("."):
                return match.group("number"), title, classify_section_type(stripped)
            return None
        stype = classify_section_type(stripped)
        if stype in self.UNNUMBERED_TYPES and len(stripped.split()) <= 8:
            return "", stripped, stype
        return None


class SectionBuilder:
    def build_sections(self, pages: list[PageArtifact]) -> list[Section]:
        candidates = self._heading_candidates(pages)
        if not candidates:
            return [self._whole_document_section(pages)]

        sections: list[Section] = []
        known_title_keys = {canonical_key(candidate["title"]) for candidate in candidates}
        for index, candidate in enumerate(candidates):
            next_candidate = candidates[index + 1] if index + 1 < len(candidates) else None
            raw_text = self._section_text_between(pages, candidate, next_candidate)
            comparison_source = self._remove_known_heading_lines(raw_text, known_title_keys)
            normalized = remove_non_text_comparison_lines(comparison_source)
            comparison_text = canonical_comparison_text(comparison_source)
            number = candidate["number"]
            section_id = "sec_" + slugify(number, str(index))
            level = number.count(".") + 1
            parent_id = self._parent_id(number)
            title = candidate["title"].strip()
            sections.append(
                Section(
                    section_id=section_id,
                    number=number,
                    title=title,
                    full_title=f"{number} {title}",
                    level=level,
                    parent_section_id=parent_id,
                    section_type=self._section_type(title),
                    page_start=candidate["page_index"] + 1,
                    page_end=(next_candidate["page_index"] + 1 if next_candidate else pages[-1].page_index + 1),
                    order_index=index,
                    raw_text=raw_text,
                    normalized_text=normalized,
                    comparison_enabled=self._comparison_enabled(title, normalized),
                    normalized_text_hash=stable_hash(comparison_text),
                    text_length=len(normalized),
                    word_count=len(normalized.split()),
                )
            )
        return sections

    def _heading_candidates(self, pages: list[PageArtifact]) -> list[dict]:
        candidates: list[dict] = []
        for page in pages:
            if self._is_non_comparison_page(page.normalized_text):
                continue
            for line_index, line in enumerate(page.normalized_text.splitlines()):
                match = HEADING_RE.match(line.strip())
                if match and self._is_valid_heading(line.strip(), match.group("number"), match.group("title")):
                    candidates.append(
                        {
                            "page_index": page.page_index,
                            "line": line_index,
                            "number": match.group("number"),
                            "title": match.group("title"),
                        }
                    )
        return self._filter_hierarchy_candidates(candidates)

    @staticmethod
    def _filter_hierarchy_candidates(candidates: list[dict]) -> list[dict]:
        filtered: list[dict] = []
        current_top = 0
        for index, candidate in enumerate(candidates):
            number = candidate["number"]
            if "." not in number:
                value = int(number)
                if current_top == 0 or value == current_top + 1 or (
                    value > current_top + 1 and not SectionBuilder._returns_to_current_top(candidates[index + 1 :], current_top, value)
                ):
                    filtered.append(candidate)
                    current_top = value
                continue
            top = int(number.split(".", 1)[0])
            if top <= current_top:
                filtered.append(candidate)
        return filtered

    @staticmethod
    def _returns_to_current_top(remaining: list[dict], current_top: int, candidate_top: int) -> bool:
        if current_top == 0:
            return False
        for candidate in remaining:
            number = candidate["number"]
            top = int(number.split(".", 1)[0])
            if "." in number and top == current_top:
                return True
            if "." not in number and top >= candidate_top:
                return False
        return False

    @staticmethod
    def _section_text_between(pages: list[PageArtifact], start: dict, end: dict | None) -> str:
        lines: list[str] = []
        for page in pages:
            if page.page_index < start["page_index"]:
                continue
            if end is not None and page.page_index > end["page_index"]:
                break
            if SectionBuilder._is_non_comparison_page(page.normalized_text):
                continue

            page_lines = page.normalized_text.splitlines()
            start_line = start["line"] + 1 if page.page_index == start["page_index"] else 0
            end_line = end["line"] if end is not None and page.page_index == end["page_index"] else len(page_lines)
            lines.extend(page_lines[start_line:end_line])
        return combined_text(lines)

    @staticmethod
    def _remove_known_heading_lines(text: str, known_title_keys: set[str]) -> str:
        kept = []
        for line in normalize_text(text).splitlines():
            if canonical_key(line) in known_title_keys:
                continue
            kept.append(line)
        return combined_text(kept)

    @staticmethod
    def _whole_document_section(pages: list[PageArtifact]) -> Section:
        raw_text = combined_text(page.normalized_text for page in pages)
        normalized = remove_non_text_comparison_lines(raw_text)
        comparison_text = canonical_comparison_text(raw_text)
        return Section(
            section_id="sec_document",
            number="",
            title="Document",
            full_title="Document",
            level=1,
            parent_section_id="",
            section_type="main_content",
            page_start=1 if pages else 0,
            page_end=pages[-1].page_index + 1 if pages else 0,
            order_index=0,
            raw_text=raw_text,
            normalized_text=normalized,
            comparison_enabled=True,
            normalized_text_hash=stable_hash(comparison_text),
            text_length=len(normalized),
            word_count=len(normalized.split()),
        )

    @staticmethod
    def _parent_id(number: str) -> str:
        if "." not in number:
            return ""
        return "sec_" + slugify(number.rsplit(".", 1)[0], "parent")

    @staticmethod
    def _section_type(title: str) -> str:
        lowered = title.lower()
        if "table of contents" in lowered or lowered == "contents":
            return "toc"
        if "revision history" in lowered:
            return "revision_history"
        if "legal" in lowered or "notice" in lowered:
            return "legal_notice"
        if "appendix" in lowered:
            return "appendix"
        return "main_content"

    @staticmethod
    def _is_valid_heading(line: str, number: str, title: str) -> bool:
        if number.startswith("0"):
            return False
        if is_toc_line(line) or is_toc_line(title):
            return False
        if SectionBuilder._is_procedure_step_title(title):
            return False
        if not re.search(r"[A-Za-z]", title):
            return False
        if title.count(".") >= 4:
            return False
        return True

    @staticmethod
    def _is_procedure_step_title(title: str) -> bool:
        lowered = title.lower().strip()
        step_prefixes = (
            "area ",
            "byte ",
            "bytes ",
            "choose ",
            "erase ",
            "wait for ack",
            "wait for nack",
            "if loop",
            "if not last",
            "if last",
            "not ",
            "only ",
            "perform ",
            "read data ",
            "select ",
            "used ",
        )
        if lowered.startswith(step_prefixes):
            return True
        return lowered.endswith(".") and len(lowered.split()) >= 4

    @staticmethod
    def _is_non_comparison_page(text: str) -> bool:
        lines = [line.strip().lower() for line in normalize_text(text).splitlines() if line.strip()]
        if not lines:
            return False
        first = lines[0]
        return first in {"contents", "revision history"} or first.startswith("list of figures") or first.startswith("list of tables")

    @classmethod
    def _comparison_enabled(cls, title: str, normalized_text: str) -> bool:
        if cls._section_type(title) in {"toc", "front_matter", "legal_notice"}:
            return False
        return bool(normalized_text.strip())
