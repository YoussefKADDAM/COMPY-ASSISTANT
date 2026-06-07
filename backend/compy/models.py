"""Domain models for the COMPY MVP1 comparison pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DocumentMetadata:
    document_code: str = ""
    title: str = ""
    revision: str = ""
    publication_date: str = ""
    page_count: int = 0
    file_name: str = ""
    pdf_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PageArtifact:
    page_index: int
    displayed_page_number: str = ""
    raw_text: str = ""
    normalized_text: str = ""
    prose_text: str = ""
    header_candidate: str = ""
    footer_candidate: str = ""
    page_width: float = 0.0
    page_height: float = 0.0
    extraction_confidence: Optional[float] = None
    # Geometry of non-prose regions excluded from MVP1 comparison. Recorded now so
    # MVP3 (tables) and MVP4 (figures) can reuse them. Each bbox is [x0, y0, x1, y1].
    table_bboxes: List[List[float]] = field(default_factory=list)
    figure_bboxes: List[List[float]] = field(default_factory=list)


@dataclass
class OutlineEntry:
    """One bookmark from the PDF outline, used to build sections deterministically."""

    level: int
    number: str
    title: str
    section_type: str
    page_index: int  # 0-based page where the heading starts


@dataclass
class ProseBlock:
    """A body-prose paragraph/heading block after geometry-based filtering."""

    page_index: int
    y0: float
    x0: float
    text: str
    max_size: float
    # Per-line (text, font_size) pairs, used by the no-outline fallback to detect
    # headings by font size when bookmarks are unavailable.
    lines: List[Any] = field(default_factory=list)


@dataclass
class ExtractionResult:
    metadata: "DocumentMetadata"
    pages: List[PageArtifact]
    outline: List[OutlineEntry]
    prose_blocks: List[ProseBlock]
    outline_available: bool
    body_font_size: float = 0.0


@dataclass
class Section:
    section_id: str
    number: str
    title: str
    full_title: str
    level: int
    parent_section_id: str
    section_type: str
    page_start: int
    page_end: int
    order_index: int
    raw_text: str
    normalized_text: str
    comparison_enabled: bool
    normalized_text_hash: str
    text_length: int
    word_count: int
    table_ids: List[str] = field(default_factory=list)
    figure_ids: List[str] = field(default_factory=list)
    # Comparison text split into [page_number, text] pieces, so the diff engine
    # can report the actual page a change occurs on (sections can span pages).
    page_map: List[List[Any]] = field(default_factory=list)


@dataclass
class Document:
    document_id: str
    source_pdf: str
    document_metadata: DocumentMetadata
    outline_available: bool
    pages: List[PageArtifact] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)


@dataclass
class SectionMatch:
    match_id: str
    status: str
    old_section_id: str = ""
    new_section_id: str = ""
    score: float = 0.0
    reason: str = ""


@dataclass
class DiffItem:
    diff_id: str
    change_type: str
    old_section_id: str = ""
    new_section_id: str = ""
    section_number: str = ""
    section_title: str = ""
    page_v1: str = ""
    page_v2: str = ""
    deterministic_summary: str = ""
    old_snippet: str = ""
    new_snippet: str = ""
    severity: str = ""
    ai_summary: str = ""
    # Snippets split so the UI/report can colour ONLY the changed words: the
    # prefix/suffix are unchanged context, the *_change part is what differs.
    old_prefix: str = ""
    old_change: str = ""
    old_suffix: str = ""
    new_prefix: str = ""
    new_change: str = ""
    new_suffix: str = ""


@dataclass
class RevisionEntry:
    section: str
    revision_summary: str
    severity: str = ""
    source_diff_id: str = ""


@dataclass
class ComparisonJobResult:
    old_document: Document
    new_document: Document
    section_matches: List[SectionMatch]
    diff_items: List[DiffItem]
    revision_entries: List[RevisionEntry]
    output_dir: str


def to_dict(value: Any) -> Any:
    """Convert dataclass graphs to JSON-friendly dictionaries."""
    return asdict(value)
