import unittest

from backend.compy.models import DiffItem
from frontend.compy_ui import format_diff_item


class UiFormattingTests(unittest.TestCase):
    def test_formats_added_deleted_and_changed_with_pages(self) -> None:
        added = DiffItem(
            diff_id="1", change_type="added", section_number="2.1", section_title="Clock",
            new_snippet="New PLL paragraph", page_v2="5",
        )
        deleted = DiffItem(
            diff_id="2", change_type="deleted", section_number="3", section_title="Reset",
            old_snippet="Old reset paragraph", page_v1="7",
        )
        changed = DiffItem(
            diff_id="3", change_type="changed", section_number="4", section_title="Power",
            old_snippet="Voltage is 1.8 V", new_snippet="Voltage is 3.3 V", page_v2="9",
        )

        self.assertEqual(format_diff_item(added), "Added in section 2.1 Clock (Page 5): New PLL paragraph")
        self.assertEqual(format_diff_item(deleted), "Deleted from section 3 Reset (Page 7): Old reset paragraph")
        self.assertEqual(
            format_diff_item(changed),
            "Changed section 4 Power (Page 9): Voltage is 1.8 V -> Voltage is 3.3 V",
        )


if __name__ == "__main__":
    unittest.main()
