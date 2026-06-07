import unittest

from backend.compy.diff_engine import DiffEngine
from backend.compy.matcher import SectionMatcher
from backend.compy.models import Document, DocumentMetadata, ExtractionResult, PageArtifact
from backend.compy.normalizer import DocumentNormalizer
from backend.compy.text_utils import normalize_text


def document(document_id: str, text: str) -> Document:
    # No bookmark outline here, so this exercises the regex fallback section builder.
    pages = [PageArtifact(page_index=0, raw_text=text, normalized_text=normalize_text(text))]
    extraction = ExtractionResult(
        metadata=DocumentMetadata(file_name=f"{document_id}.pdf", page_count=1),
        pages=pages,
        outline=[],
        prose_blocks=[],
        outline_available=False,
    )
    return DocumentNormalizer().normalize(
        document_id=document_id,
        source_pdf=f"{document_id}.pdf",
        extraction=extraction,
    )


class CompareCoreTests(unittest.TestCase):
    def test_detects_added_deleted_and_changed(self) -> None:
        old = document(
            "old",
            "1 Intro\nVoltage is 1.8 V here now\n"
            "2 Reset\nReset stays identical here\n"
            "4 Legacy\nLegacy only in old",
        )
        new = document(
            "new",
            "1 Intro\nVoltage is 3.3 V here now\n"
            "2 Reset\nReset stays identical here\n"
            "3 Power\nPower only in new",
        )

        matches = SectionMatcher().match(old, new)
        diff_items = DiffEngine().diff(old, new, matches)
        types = {item.change_type for item in diff_items}

        self.assertIn("changed", types)  # 1.8 V -> 3.3 V
        self.assertIn("added", types)    # section 3 Power
        self.assertIn("deleted", types)  # section 4 Legacy
        self.assertFalse(any(item.section_number == "2" for item in diff_items))  # unchanged skipped

    def test_changed_snippet_focuses_on_changed_words(self) -> None:
        old = document("old", "1 Intro\nThe STM32CubeF7/H5/H7/H7RS provides a JPEG driver.")
        new = document("new", "1 Intro\nThe STM32CubeF7/H5/H7/H8RS provides a JPEG driver.")

        diff_items = DiffEngine().diff(old, new, SectionMatcher().match(old, new))

        self.assertEqual(len(diff_items), 1)
        self.assertEqual(diff_items[0].change_type, "changed")
        self.assertIn("H7RS", diff_items[0].old_snippet)
        self.assertIn("H8RS", diff_items[0].new_snippet)

    def test_reports_every_change_in_one_paragraph(self) -> None:
        # Three independent edits in the same paragraph must be reported separately.
        old = document("old", "1 List\nIf N = 0 first then. If N = 0 second then. If N = 0 third then.")
        new = document("new", "1 List\nIf N = 1 first then. If N = 1 second then. If N = 1 third then.")

        diff_items = DiffEngine().diff(old, new, SectionMatcher().match(old, new))
        changed = [d for d in diff_items if d.change_type == "changed"]

        self.assertEqual(len(changed), 3)


if __name__ == "__main__":
    unittest.main()
