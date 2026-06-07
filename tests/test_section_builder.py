import unittest

from backend.compy.models import PageArtifact
from backend.compy.normalizer import SectionBuilder
from backend.compy.text_utils import normalize_text


def page(index: int, text: str) -> PageArtifact:
    return PageArtifact(page_index=index, raw_text=text, normalized_text=normalize_text(text))


class SectionBuilderTests(unittest.TestCase):
    def test_builds_numbered_sections_across_pages(self) -> None:
        sections = SectionBuilder().build_sections(
            [
                page(0, "1 Introduction\nOld intro text\n2 Clock tree\nClock details"),
                page(1, "2.1 PLL\nPLL details\nMore PLL details"),
            ]
        )

        self.assertEqual([section.number for section in sections], ["1", "2", "2.1"])
        self.assertEqual(sections[2].parent_section_id, "sec_2")
        self.assertIn("PLL details", sections[2].normalized_text)
        self.assertNotIn("2 Clock tree", sections[0].normalized_text)

    def test_falls_back_to_whole_document_without_headings(self) -> None:
        sections = SectionBuilder().build_sections([page(0, "plain document text")])

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].section_id, "sec_document")
        self.assertEqual(sections[0].title, "Document")

    def test_ignores_table_rows_and_toc_lines_as_headings(self) -> None:
        sections = SectionBuilder().build_sections(
            [
                page(
                    0,
                    "1 General information\n"
                    "Useful prose\n"
                    "16 11 10 16 24 40 51 61\n"
                    "99 99 99 99 99 99 99 99\n"
                    "2 Hardware JPEG codec overview ................................................... 3\n"
                    "2 Hardware JPEG codec overview\n"
                    "More prose",
                )
            ]
        )

        self.assertEqual([section.full_title for section in sections], ["1 General information", "2 Hardware JPEG codec overview"])
        self.assertNotIn("16 11 10", sections[0].normalized_text)
        self.assertNotIn("................................", sections[0].normalized_text)

    def test_ignores_numbered_procedure_steps_as_headings(self) -> None:
        sections = SectionBuilder().build_sections(
            [
                page(
                    0,
                    "3 Bootloader command set\n"
                    "3.1 Get command\n"
                    "1. Byte 1: ACK\n"
                    "2. Byte 2: N = 10 = Number of commands\n"
                    "3. Wait for ACK or NACK\n"
                    "3.2 Get version command\n"
                    "Useful prose",
                )
            ]
        )

        self.assertEqual(
            [section.full_title for section in sections],
            ["3 Bootloader command set", "3.1 Get command", "3.2 Get version command"],
        )

    def test_ignores_single_number_resets_inside_a_section(self) -> None:
        sections = SectionBuilder().build_sections(
            [
                page(
                    0,
                    "1 General information\n"
                    "2 ECC overview\n"
                    "2.1 ECC implications\n"
                    "1 AXI bus is 64b, but this is a footnote.\n"
                    "2 Only the first 256 KB of SRAM3.\n"
                    "2.2 RAM ECC\n"
                    "3 ECC testing\n"
                    "1 Select a flash page.\n",
                )
            ]
        )

        self.assertEqual(
            [section.full_title for section in sections],
            [
                "1 General information",
                "2 ECC overview",
                "2.1 ECC implications",
                "2.2 RAM ECC",
                "3 ECC testing",
            ],
        )


if __name__ == "__main__":
    unittest.main()
