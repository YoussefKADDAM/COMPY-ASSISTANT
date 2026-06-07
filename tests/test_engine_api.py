"""Tests for the public embedding facade (sample-free; no PDFs needed)."""

import unittest

from backend.compy import CompyEngine, ComparisonJobResult, DiffItem
from backend.compy.models import Document, DocumentMetadata
from backend.compy.reporting import ReportBuilder


class EngineApiTests(unittest.TestCase):
    def test_engine_constructs(self) -> None:
        self.assertIsInstance(CompyEngine(), CompyEngine)
        self.assertTrue(hasattr(CompyEngine(), "compare"))

    def test_kpi_summary_counts(self) -> None:
        items = [
            DiffItem(diff_id="1", change_type="added"),
            DiffItem(diff_id="2", change_type="changed"),
            DiffItem(diff_id="3", change_type="changed"),
            DiffItem(diff_id="4", change_type="deleted"),
        ]
        self.assertEqual(
            ReportBuilder.kpi_summary(items),
            {"added": 1, "deleted": 1, "changed": 2, "total": 4},
        )

    def test_report_builds_in_memory_without_writing(self) -> None:
        items = [DiffItem(diff_id="1", change_type="changed", section_number="1", section_title="X", new_snippet="b")]
        entries = ReportBuilder().build(items, [], output_dir=None)  # None => in-memory
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].section, "1 X")

    def test_result_changes_alias(self) -> None:
        doc = Document(document_id="a", source_pdf="a.pdf", document_metadata=DocumentMetadata(), outline_available=False)
        items = [DiffItem(diff_id="1", change_type="added")]
        result = ComparisonJobResult(
            old_document=doc, new_document=doc, section_matches=[],
            diff_items=items, revision_entries=[], output_dir="", kpi_summary={},
        )
        self.assertIs(result.changes, result.diff_items)


if __name__ == "__main__":
    unittest.main()
