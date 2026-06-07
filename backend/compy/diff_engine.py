"""Deterministic section diffing.

Each matched section can contain several independent edits. We diff at the word
level and emit ONE change per non-equal span, so multiple edits inside the same
paragraph (e.g. three separate "N = 0" -> "N = 1" replacements) are reported
separately. Every change is classified as:

- ``added``   -> text present in V2 but not V1
- ``deleted`` -> text present in V1 but not V2
- ``changed`` -> text present in both but reworded
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .models import DiffItem, Document, Section, SectionMatch
from .text_utils import canonical_key, first_words

CONTEXT_WORDS = 5  # words of surrounding context shown around each change
# Above this many words, diff line-by-line first (cheap) and only word-diff the
# changed lines. Keeps very long sections from a costly whole-section word diff.
TWO_LEVEL_WORD_LIMIT = 8000


class DiffEngine:
    def diff(self, old_document: Document, new_document: Document, matches: list[SectionMatch]) -> list[DiffItem]:
        old_by_id = {section.section_id: section for section in old_document.sections}
        new_by_id = {section.section_id: section for section in new_document.sections}
        diff_items: list[DiffItem] = []

        for match in matches:
            old_section = old_by_id.get(match.old_section_id)
            new_section = new_by_id.get(match.new_section_id)

            if match.status == "matched" and old_section and new_section:
                if old_section.normalized_text_hash == new_section.normalized_text_hash:
                    continue
                diff_items.extend(self._section_changes(old_section, new_section))
            elif match.status == "removed" and old_section:
                diff_items.append(self._whole_section_item(old_section, "deleted"))
            elif match.status == "added" and new_section:
                diff_items.append(self._whole_section_item(new_section, "added"))

        return diff_items

    # -- granular, word-level changes ---------------------------------------
    def _section_changes(self, old_section: Section, new_section: Section) -> list[DiffItem]:
        old_words, old_pages = _words_with_pages(old_section)
        new_words, new_pages = _words_with_pages(new_section)

        if len(old_words) + len(new_words) <= TWO_LEVEL_WORD_LIMIT:
            return self._word_changes(
                old_section, new_section, old_words, old_pages, new_words, new_pages,
                0, len(old_words), 0, len(new_words), start_counter=0,
            )

        # Very long section: diff lines first, then word-diff only changed lines.
        old_lines = [str(entry[1]) for entry in old_section.page_map] or [old_section.normalized_text]
        new_lines = [str(entry[1]) for entry in new_section.page_map] or [new_section.normalized_text]
        old_offsets = _word_offsets(old_lines)
        new_offsets = _word_offsets(new_lines)
        matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
        changes: list[DiffItem] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            sub = self._word_changes(
                old_section, new_section, old_words, old_pages, new_words, new_pages,
                old_offsets[i1], old_offsets[i2], new_offsets[j1], new_offsets[j2],
                start_counter=len(changes),
            )
            changes.extend(sub)
        return changes

    def _word_changes(
        self,
        old_section: Section,
        new_section: Section,
        old_words: list[str],
        old_pages: list[int],
        new_words: list[str],
        new_pages: list[int],
        oa: int,
        ob: int,
        na: int,
        nb: int,
        start_counter: int,
    ) -> list[DiffItem]:
        """Word-level diff of a span ``old_words[oa:ob]`` vs ``new_words[na:nb]``."""
        matcher = SequenceMatcher(None, old_words[oa:ob], new_words[na:nb], autojunk=False)
        changes: list[DiffItem] = []
        counter = start_counter

        for tag, ri1, ri2, rj1, rj2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            i1, i2, j1, j2 = oa + ri1, oa + ri2, na + rj1, na + rj2
            old_part = " ".join(old_words[i1:i2])
            new_part = " ".join(new_words[j1:j2])
            # Ignore pure punctuation/spacing differences (e.g. "10. Read" vs "10.Read").
            if canonical_key(old_part) == canonical_key(new_part):
                continue

            if tag == "insert":
                change_type = "added"
            elif tag == "delete":
                change_type = "deleted"
            else:
                change_type = "changed"

            page_v1 = old_pages[min(i1, len(old_pages) - 1)] if old_pages else old_section.page_start
            page_v2 = new_pages[min(j1, len(new_pages) - 1)] if new_pages else new_section.page_start
            counter += 1
            changes.append(
                DiffItem(
                    diff_id=f"diff_{change_type}_{new_section.section_id or old_section.section_id}_{counter}",
                    change_type=change_type,
                    old_section_id=old_section.section_id,
                    new_section_id=new_section.section_id,
                    section_number=new_section.number or old_section.number,
                    section_title=new_section.title or old_section.title,
                    page_v1=str(page_v1),
                    page_v2=str(page_v2),
                    deterministic_summary=self._summary(change_type),
                    old_snippet=_context(old_words, i1, i2),
                    new_snippet=_context(new_words, j1, j2),
                )
            )
        return changes

    @staticmethod
    def _summary(change_type: str) -> str:
        return {
            "added": "Text added.",
            "deleted": "Text deleted.",
            "changed": "Text changed.",
        }[change_type]

    @staticmethod
    def _whole_section_item(section: Section, change_type: str) -> DiffItem:
        snippet = first_words(section.normalized_text)
        return DiffItem(
            diff_id=f"diff_{change_type}_section_{section.section_id}",
            change_type=change_type,
            old_section_id=section.section_id if change_type == "deleted" else "",
            new_section_id=section.section_id if change_type == "added" else "",
            section_number=section.number,
            section_title=section.title,
            page_v1=str(section.page_start) if change_type == "deleted" else "",
            page_v2=str(section.page_start) if change_type == "added" else "",
            deterministic_summary=f"Section {change_type}.",
            old_snippet=snippet if change_type == "deleted" else "",
            new_snippet=snippet if change_type == "added" else "",
        )


def _words_with_pages(section: Section) -> tuple[list[str], list[int]]:
    """Flatten a section's comparison text into words tagged with their page."""
    words: list[str] = []
    pages: list[int] = []
    for entry in section.page_map:
        page, text = int(entry[0]), str(entry[1])
        for word in text.split():
            words.append(word)
            pages.append(page)
    if not words:  # legacy/fallback sections without a page map
        words = section.normalized_text.split()
        pages = [section.page_start] * len(words)
    return words, pages


def _word_offsets(lines: list[str]) -> list[int]:
    """Prefix word counts: offsets[k] = index of the first word of line k."""
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.split()))
    return offsets


def _context(words: list[str], start: int, end: int) -> str:
    """The changed span plus a few words of context on each side."""
    lo = max(0, start - CONTEXT_WORDS)
    hi = min(len(words), end + CONTEXT_WORDS)
    return " ".join(words[lo:hi])
