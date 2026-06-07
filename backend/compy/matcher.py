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
        old_corpus_key = canonical_key(" ".join(page.raw_text or page.normalized_text for page in old_document.pages))
        new_corpus_key = canonical_key(" ".join(page.raw_text or page.normalized_text for page in new_document.pages))
        matches: list[SectionMatch] = []

        for old_section in old_sections:
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
