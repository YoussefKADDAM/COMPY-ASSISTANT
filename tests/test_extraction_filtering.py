"""Tests for the layout-aware sectioning and prose filtering (MVP1).

The geometry filtering itself needs a real PDF, so it is covered by a guarded
integration test against the sample AV1.pdf. The section builders are covered by
fast, deterministic unit tests using synthetic prose blocks.
"""

import unittest
from pathlib import Path

from backend.compy.extractor import PdfExtractor, classify_section_type
from backend.compy.models import OutlineEntry, ProseBlock
from backend.compy.normalizer import (
    DocumentNormalizer,
    FontHeadingSectionBuilder,
    OutlineSectionBuilder,
    heading_echo_keys,
)

SAMPLE_PDF = Path(__file__).resolve().parents[1] / "PDF Tests" / "AV1.pdf"


def block(page, text, size):
    return ProseBlock(page_index=page, y0=0.0, x0=0.0, text=text, max_size=size, lines=[[text, size]])


def multiline_block(page, lines):
    text = " ".join(t for t, _ in lines)
    return ProseBlock(
        page_index=page, y0=0.0, x0=0.0, text=text,
        max_size=max(s for _, s in lines), lines=[[t, s] for t, s in lines],
    )


class ClassifyTests(unittest.TestCase):
    def test_section_type_classification(self):
        self.assertEqual(classify_section_type("Contents"), "toc")
        self.assertEqual(classify_section_type("List of tables"), "list_of_tables")
        self.assertEqual(classify_section_type("List of figures"), "list_of_figures")
        self.assertEqual(classify_section_type("Revision history"), "revision_history")
        self.assertEqual(classify_section_type("Introduction"), "introduction")
        self.assertEqual(classify_section_type("Appendix A ECC sequences"), "appendix")
        self.assertEqual(classify_section_type("AN5342"), "front_matter")
        self.assertEqual(classify_section_type("2 ECC overview"), "main_content")


class HeadingEchoKeyTests(unittest.TestCase):
    def test_includes_title_and_appendix_stripped_variant(self):
        keys = heading_echo_keys([("", "Appendix A ECC sequences"), ("2.2", "RAM ECC")])
        self.assertIn("eccsequences", keys)          # running header drops "Appendix A"
        self.assertIn("appendixaeccsequences", keys)
        self.assertIn("ramecc", keys)

    def test_skips_short_titles(self):
        self.assertNotIn("far", heading_echo_keys([("", "FAR")]))


class OutlineSectionBuilderTests(unittest.TestCase):
    def test_builds_sections_with_types_and_drops_echo(self):
        blocks = [
            block(0, "Introduction", 12.0),
            block(0, "Intro prose describing the application note scope.", 9.0),
            block(1, "1 General information", 14.0),
            block(1, "Body of the general information section text.", 9.0),
            block(1, "General information", 9.0),   # running-header echo -> dropped
            block(2, "Contents", 14.0),
            block(2, "1 General information ......... 2", 10.0),
        ]
        outline = [
            OutlineEntry(1, "", "Introduction", "introduction", 0),
            OutlineEntry(1, "1", "General information", "main_content", 1),
            OutlineEntry(1, "", "Contents", "toc", 2),
        ]
        sections = OutlineSectionBuilder().build(outline, blocks, body_size=9.0)

        self.assertEqual([s.full_title for s in sections], ["Introduction", "1 General information", "Contents"])
        intro, general, contents = sections
        self.assertIn("Intro prose", intro.normalized_text)
        self.assertIn("Body of the general information", general.normalized_text)
        self.assertNotIn("\nGeneral information", "\n" + general.normalized_text)  # echo gone
        self.assertTrue(general.comparison_enabled)
        self.assertFalse(contents.comparison_enabled)  # toc excluded from comparison


class FontHeadingSectionBuilderTests(unittest.TestCase):
    def test_detects_headings_by_font_including_split_numbers(self):
        blocks = [
            block(0, "Introduction", 12.0),
            block(0, "Intro body prose for the note.", 9.0),
            # number on its own line, title on the next line (both heading-sized)
            multiline_block(1, [("2.1 ", 12.0), ("ECC implications", 12.0),
                                ("Detailed prose about ECC implications here.", 9.0)]),
            block(1, "NOTE: this callout must not become a section.", 11.0),
            block(2, "5 Conclusion", 14.0),
            block(2, "Concluding remarks for the document.", 9.0),
        ]
        sections = FontHeadingSectionBuilder().build(blocks, body_size=9.0)

        titles = [s.full_title for s in sections]
        self.assertEqual(titles, ["Introduction", "2.1 ECC implications", "5 Conclusion"])
        impl = sections[1]
        self.assertEqual(impl.number, "2.1")
        self.assertIn("Detailed prose about ECC implications", impl.normalized_text)
        # The NOTE callout stays as body, never its own section.
        self.assertNotIn("NOTE", " ".join(titles))

    def test_no_headings_returns_empty(self):
        blocks = [block(0, "just plain prose with no headings at all here", 9.0)]
        self.assertEqual(FontHeadingSectionBuilder().build(blocks, body_size=9.0), [])


@unittest.skipUnless(SAMPLE_PDF.exists(), "sample PDF not available")
class IntegrationTests(unittest.TestCase):
    """End-to-end geometry filtering against the real sample PDF."""

    @classmethod
    def setUpClass(cls):
        ex = PdfExtractor().extract(str(SAMPLE_PDF))
        cls.doc = DocumentNormalizer().normalize("av1", "AV1.pdf", ex)
        cls.compared = "\n".join(s.normalized_text for s in cls.doc.sections if s.comparison_enabled)

    def test_outline_is_used(self):
        self.assertTrue(any(s.number == "2.2" for s in self.doc.sections))

    def test_figure_labels_and_ids_are_excluded(self):
        for noise in ("ECC wrapper", "DT62937", "ramecc_hclk", "Signal line Data bus"):
            self.assertNotIn(noise, self.compared, f"figure noise leaked: {noise}")

    def test_captions_footers_and_toc_excluded(self):
        self.assertNotIn("Figure 2.", self.compared)
        self.assertNotIn("page 5/20", self.compared)
        self.assertNotIn("....", self.compared)

    def test_real_prose_is_retained(self):
        self.assertIn("RAM ECC controllers are assigned", self.compared)

    def test_structural_sections_not_compared(self):
        for s in self.doc.sections:
            if s.section_type in {"toc", "list_of_tables", "list_of_figures", "revision_history", "front_matter"}:
                self.assertFalse(s.comparison_enabled, f"{s.full_title} should not be compared")


if __name__ == "__main__":
    unittest.main()
