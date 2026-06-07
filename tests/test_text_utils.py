import unittest

from backend.compy.text_utils import (
    canonical_comparison_text,
    normalize_text,
    remove_non_text_comparison_lines,
    stable_hash,
)


class TextUtilsTests(unittest.TestCase):
    def test_normalize_text_compacts_spaces_and_blank_lines(self) -> None:
        self.assertEqual(normalize_text(" A   B \r\n\r\n\r\n C "), "A B\nC")

    def test_stable_hash_is_repeatable(self) -> None:
        self.assertEqual(stable_hash("abc"), stable_hash("abc"))
        self.assertNotEqual(stable_hash("abc"), stable_hash("abcd"))

    def test_normalize_text_splits_glued_numeric_bullets(self) -> None:
        self.assertEqual(
            normalize_text("– 00: 4:4:4 (no chroma sub-sampling)– 01: 4:2:2"),
            "– 00: 4:4:4 (no chroma sub-sampling)\n– 01: 4:2:2",
        )

    def test_repairs_spaced_letters_and_ignores_basic_punctuation_for_comparison(self) -> None:
        self.assertEqual(normalize_text("B o o t l o a d e r command"), "Bootloader command")
        self.assertEqual(canonical_comparison_text("Hello, world."), canonical_comparison_text("hello world"))

    def test_removes_only_generic_structural_noise(self) -> None:
        # The geometry-aware extractor removes tables/figures upstream. This thin
        # safety net only drops unambiguous structural noise (dot-leader TOC lines,
        # pure-numeric table rows, page footers) and KEEPS real prose -- including
        # sentences that merely mention a table or figure.
        text = "\n".join(
            [
                "Useful prose before.",
                "Table 5 shows the word size for STM32 devices.",
                "Introduction .................................................. 5",
                "16 11 10 16 24 40 51 61",
                "AN5342 - Rev 8 page 5/20",
                "most erroneous words are detected while there is still only one wrong bit.",
            ]
        )

        filtered = remove_non_text_comparison_lines(text)

        self.assertIn("Useful prose before.", filtered)
        self.assertIn("Table 5 shows the word size", filtered)  # prose kept
        self.assertIn("most erroneous words are detected", filtered)
        self.assertNotIn("..........", filtered)        # TOC dot-leader removed
        self.assertNotIn("16 11 10", filtered)          # numeric table row removed
        self.assertNotIn("page 5/20", filtered)         # page footer removed


if __name__ == "__main__":
    unittest.main()
