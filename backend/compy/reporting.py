"""Comparison report and revision-history artifact generation."""

from __future__ import annotations

import html
from pathlib import Path

from .io import write_json, write_text
from .models import DiffItem, RevisionEntry, SectionMatch, to_dict

# Change type -> (label, colour) for the report. Added=green, Deleted=red, Changed=orange.
CHANGE_STYLE = {
    "added": ("Added", "#1a7f37", "#e6f4ea"),
    "deleted": ("Deleted", "#b42318", "#fde8e6"),
    "changed": ("Changed", "#b54708", "#fdf0e3"),
}


class ReportBuilder:
    def build(
        self,
        diff_items: list[DiffItem],
        section_matches: list[SectionMatch],
        output_dir: str | Path,
    ) -> list[RevisionEntry]:
        out = Path(output_dir)
        revision_entries = [
            RevisionEntry(
                section=f"{item.section_number} {item.section_title}".strip() or "Document",
                revision_summary=item.ai_summary or item.deterministic_summary,
                severity=item.severity,
                source_diff_id=item.diff_id,
            )
            for item in diff_items
        ]
        kpis = self.kpi_summary(diff_items)

        write_json(out / "section_matches.json", [to_dict(match) for match in section_matches])
        write_json(out / "diff_report.json", [to_dict(item) for item in diff_items])
        write_json(out / "revision_history_draft.json", [to_dict(entry) for entry in revision_entries])
        write_json(out / "kpi_summary.json", kpis)
        write_text(out / "comparison_report.html", self._html_report(diff_items, kpis))
        return revision_entries

    @staticmethod
    def kpi_summary(diff_items: list[DiffItem]) -> dict:
        counts = {"added": 0, "deleted": 0, "changed": 0}
        for item in diff_items:
            if item.change_type in counts:
                counts[item.change_type] += 1
        counts["total"] = sum(counts[k] for k in ("added", "deleted", "changed"))
        return counts

    @staticmethod
    def _snippet_html(prefix: str, change: str, suffix: str, full: str, colour: str) -> str:
        # Context stays default colour; only the changed words are coloured.
        if not (prefix or change or suffix):
            return f'<span style="color:{colour}">{html.escape(full)}</span>' if full else ""
        out = html.escape(prefix)
        if change:
            if out:
                out += " "
            out += f'<span style="color:{colour};font-weight:600">{html.escape(change)}</span>'
        if suffix:
            sep = "" if suffix[:1] in ".,;:!?)]}%" else " "
            out += sep + html.escape(suffix)
        return out

    @classmethod
    def _html_report(cls, diff_items: list[DiffItem], kpis: dict) -> str:
        rows = []
        for item in diff_items:
            label, colour, bg = CHANGE_STYLE.get(item.change_type, (item.change_type, "#1f2933", "#ffffff"))
            section = html.escape((item.section_number + " " + item.section_title).strip() or "Document")
            page = html.escape(item.page_v2 or item.page_v1 or "")
            old_html = cls._snippet_html(item.old_prefix, item.old_change, item.old_suffix, item.old_snippet, "#b42318")
            new_html = cls._snippet_html(item.new_prefix, item.new_change, item.new_suffix, item.new_snippet, "#1a7f37")
            rows.append(
                f'<tr style="background:{bg}">'
                f'<td><span style="color:{colour};font-weight:600">{label}</span></td>'
                f"<td>{html.escape(item.section_number) or '&mdash;'}</td>"
                f"<td>{section}</td>"
                f"<td>Page {page}</td>"
                f"<td>{old_html}</td>"
                f"<td>{new_html}</td>"
                "</tr>"
            )
        kpi_cards = "".join(
            f'<div class="kpi {key}"><div class="kpi-n">{kpis.get(key, 0)}</div>'
            f'<div class="kpi-l">{label}</div></div>'
            for key, (label, _c, _b) in CHANGE_STYLE.items()
        )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>COMPY Comparison Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2933; }}
    h1 {{ color: #03234B; }}
    .kpis {{ display: flex; gap: 16px; margin: 16px 0 24px; }}
    .kpi {{ border-radius: 10px; padding: 14px 22px; min-width: 96px; text-align: center; color: #fff; }}
    .kpi.added {{ background: #1a7f37; }}
    .kpi.deleted {{ background: #b42318; }}
    .kpi.changed {{ background: #b54708; }}
    .kpi-n {{ font-size: 28px; font-weight: 700; }}
    .kpi-l {{ font-size: 13px; opacity: .9; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #d7dde5; padding: 8px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #03234B; color: white; }}
  </style>
</head>
<body>
  <h1>COMPY Comparison Report</h1>
  <div class="kpis">{kpi_cards}
    <div class="kpi" style="background:#03234B"><div class="kpi-n">{kpis.get('total', 0)}</div><div class="kpi-l">Total</div></div>
  </div>
  <table>
    <thead><tr><th>Type</th><th>Section #</th><th>Section</th><th>Page</th><th>V1 (old)</th><th>V2 (new)</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
