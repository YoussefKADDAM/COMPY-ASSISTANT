"""Section matching for MVP1."""

from __future__ import annotations

from .models import Document, Section, SectionMatch
from .text_utils import canonical_key, normalize_text, similarity


class SectionMatcher:
    def __init__(self, similarity_threshold: float = 0.72) -> None:
        self.similarity_threshold = similarity_threshold

    def match(self, old_document: Document, new_document: Document) -> list[SectionMatch]:
        old_sections = [section for section in old_document.sections if section.comparison_enabled]
        new_sections = [section for section in new_document.sections if section.comparison_enabled]
        unmatched_new = {section.section_id: section for section in new_sections}
        # Corpus used only to check whether a section title appears anywhere in the
        # other document. Built from section titles + text (titles are excluded from
        # bodies, so we add full_title explicitly).
        old_corpus_key = canonical_key(" ".join(f"{s.full_title} {s.normalized_text}" for s in old_document.sections))
        new_corpus_key = canonical_key(" ".join(f"{s.full_title} {s.normalized_text}" for s in new_document.sections))
        matches: list[SectionMatch] = []

        # Fast path: resolve section-number and exact-title matches with O(1) index
        # lookups so we never run similarity against every candidate. This keeps
        # matching ~O(n) on documents with thousands of sections (MVP2).
        new_by_number: dict[str, Section] = {}
        new_by_title: dict[str, Section] = {}
        for section in new_sections:
            if section.number:
                new_by_number.setdefault(section.number, section)
            new_by_title.setdefault(self._title_key(section), section)

        residual_old: list[Section] = []
        for old_section in old_sections:
            indexed = self._indexed_match(old_section, new_by_number, new_by_title, unmatched_new)
            if indexed is None:
                residual_old.append(old_section)
                continue
            new_section, score, reason = indexed
            del unmatched_new[new_section.section_id]
            matches.append(
                SectionMatch(
                    match_id=f"match_{old_section.section_id}_{new_section.section_id}",
                    status="matched",
                    old_section_id=old_section.section_id,
                    new_section_id=new_section.section_id,
                    score=score,
                    reason=reason,
                )
            )

        # Slow path: only the residual (un-indexed) sections fall back to text
        # similarity, and only against the remaining unmatched candidates.
        for old_section in residual_old:
            new_section, score, reason = self._best_match(old_section, list(unmatched_new.values()))
            if new_section is None:
                if self._section_title_present(old_section, new_corpus_key):
                    matches.append(
                        SectionMatch(
                            match_id=f"match_needs_review_{old_section.section_id}",
                            status="needs_review",
                            old_section_id=old_section.section_id,
                            score=score,
                            reason="section title found in new document but could not be aligned",
                        )
                    )
                    continue
                matches.append(
                    SectionMatch(
                        match_id=f"match_removed_{old_section.section_id}",
                        status="removed",
                        old_section_id=old_section.section_id,
                        score=0.0,
                        reason="no matching section found",
                    )
                )
                continue

            del unmatched_new[new_section.section_id]
            matches.append(
                SectionMatch(
                    match_id=f"match_{old_section.section_id}_{new_section.section_id}",
                    status="matched",
                    old_section_id=old_section.section_id,
                    new_section_id=new_section.section_id,
                    score=score,
                    reason=reason,
                )
            )

        for new_section in unmatched_new.values():
            if self._section_title_present(new_section, old_corpus_key):
                matches.append(
                    SectionMatch(
                        match_id=f"match_needs_review_{new_section.section_id}",
                        status="needs_review",
                        new_section_id=new_section.section_id,
                        score=0.0,
                        reason="section title found in old document but could not be aligned",
                    )
                )
                continue
            matches.append(
                SectionMatch(
                    match_id=f"match_added_{new_section.section_id}",
                    status="added",
                    new_section_id=new_section.section_id,
                    score=0.0,
                    reason="new section has no old counterpart",
                )
            )

        return matches

    def _indexed_match(
        self,
        old_section: Section,
        new_by_number: dict[str, Section],
        new_by_title: dict[str, Section],
        unmatched_new: dict[str, Section],
    ) -> tuple[Section, float, str] | None:
        if old_section.number:
            candidate = new_by_number.get(old_section.number)
            if candidate is not None and candidate.section_id in unmatched_new:
                title_score = similarity(self._title_key(old_section), self._title_key(candidate))
                return candidate, max(0.9, title_score), "section number match"
        candidate = new_by_title.get(self._title_key(old_section))
        if candidate is not None and candidate.section_id in unmatched_new:
            return candidate, 0.86, "normalized title match"
        return None

    def _best_match(self, old_section: Section, candidates: list[Section]) -> tuple[Section | None, float, str]:
        for candidate in candidates:
            if old_section.number and old_section.number == candidate.number:
                title_score = similarity(self._title_key(old_section), self._title_key(candidate))
                return candidate, max(0.9, title_score), "section number match"

        for candidate in candidates:
            if self._title_key(old_section) == self._title_key(candidate):
                return candidate, 0.86, "normalized title match"

        scored = [
            (
                candidate,
                max(
                    similarity(old_section.normalized_text[:4000], candidate.normalized_text[:4000]),
                    similarity(self._title_key(old_section), self._title_key(candidate)),
                ),
            )
            for candidate in candidates
        ]
        if not scored:
            return None, 0.0, ""
        best, score = max(scored, key=lambda item: item[1])
        if score >= self.similarity_threshold:
            return best, score, "text/title similarity fallback"
        return None, score, "below similarity threshold"

    @staticmethod
    def _title_key(section: Section) -> str:
        return normalize_text(section.title).lower()

    @staticmethod
    def _section_title_present(section: Section, corpus_key: str) -> bool:
        title_key = canonical_key(section.title)
        return bool(title_key and len(title_key) >= 8 and title_key in corpus_key)
