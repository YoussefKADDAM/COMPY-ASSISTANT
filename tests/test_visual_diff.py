"""Tests for severity + the visual side-by-side model."""

import unittest
from pathlib import Path

from backend.compy.diff_engine import classify_severity

PDF_DIR = Path(__file__).resolve().parents[1] / "PDF Tests"
AN2V1 = PDF_DIR / "AN2V1.pdf"
AN2V2 = PDF_DIR / "AN2V2.pdf"


class SeverityTests(unittest.TestCase):
    def test_value_changes_are_major(self):
        self.assertEqual(classify_severity("changed", "AN2606", "AN2004"), "major")
        self.assertEqual(classify_severity("changed", "1.8 V", "3.3 V"), "major")

    def test_small_wording_is_minor(self):
        self.assertEqual(classify_severity("changed", "the", ""), "minor")
        self.assertEqual(classify_severity("changed", "host", "controller"), "minor")

    def test_long_phrase_is_major(self):
        self.assertEqual(
            classify_severity("added", "", "one two three four five six seven"),
            "major",
        )


@unittest.skipUnless(AN2V1.exists() and AN2V2.exists(), "sample PDFs not available")
class VisualDiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.compy import CompyEngine
        from backend.compy.visual_diff import build_visual_diff

        result = CompyEngine().compare(str(AN2V1), str(AN2V2), parallel=False)
        cls.changes = result.changes
        cls.visual = build_visual_diff(str(AN2V1), str(AN2V2), result.changes)

    def test_groups_and_highlights_exist(self):
        self.assertGreater(len(self.visual.groups), 0)
        # At least one group should carry highlight boxes on each side.
        self.assertTrue(any(g.v1_highlights for g in self.visual.groups))
        self.assertTrue(any(g.v2_highlights for g in self.visual.groups))

    def test_highlight_kinds_are_valid(self):
        kinds = {
            h.kind
            for g in self.visual.groups
            for h in (g.v1_highlights + g.v2_highlights)
        }
        self.assertTrue(kinds.issubset({"added", "deleted", "changed"}))

    def test_render_page_returns_png_bytes(self):
        from backend.compy.visual_diff import render_page

        group = next(g for g in self.visual.groups if g.v2_highlights)
        png = render_page(self.visual.v2_pdf, group.v2_page - 1, group.v2_highlights)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertGreater(len(png), 1000)


if __name__ == "__main__":
    unittest.main()
