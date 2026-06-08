"""Small PySide6 desktop UI for COMPY MVP1."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PySide6.QtCore import QRectF, QSize, Qt, QThread, Signal
    from PySide6.QtGui import (
        QAbstractTextDocumentLayout,
        QBrush,
        QColor,
        QFont,
        QPixmap,
        QTextDocument,
    )
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSplitter,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
    if os.name == "nt" and os.environ.get("COMPY_UI_REEXECED") != "1":
        env = os.environ.copy()
        env["COMPY_UI_REEXECED"] = "1"
        command = ["py", "-3.9", str(Path(__file__).resolve()), *sys.argv[1:]]
        try:
            raise SystemExit(subprocess.call(command, env=env))
        except FileNotFoundError:
            pass
    raise SystemExit(
        "PySide6 is not installed for this Python interpreter.\n"
        f"Interpreter: {sys.executable}\n"
        f"Install with: \"{sys.executable}\" -m pip install -r requirements.txt\n"
        "On Windows, COMPY also tries to relaunch with: py -3.9 frontend\\compy_ui.py"
    ) from exc


def _ensure_project_root() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


# Dark theme for the results table.
TABLE_BG = "#2b2b2b"
TABLE_FG = "#f0f0f0"
ADDED_COLOR = "#3fb950"    # bright green on dark grey
DELETED_COLOR = "#f85149"  # bright red on dark grey
CHANGED_COLOR = "#e3a008"  # amber/orange

# Change type -> (label with emoji, strong text colour for the Type cell).
TYPE_STYLE = {
    "added": ("🟢 Added", ADDED_COLOR),
    "deleted": ("🔴 Deleted", DELETED_COLOR),
    "changed": ("🟠 Changed", CHANGED_COLOR),
}


class CompareWorker(QThread):
    finished_ok = Signal(str, list, dict, object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, pdf_v1: str, pdf_v2: str, output_dir: str) -> None:
        super().__init__()
        self.pdf_v1 = pdf_v1
        self.pdf_v2 = pdf_v2
        self.output_dir = output_dir

    def run(self) -> None:
        _ensure_project_root()
        from backend.compy import CompyEngine
        from backend.compy.extractor import PdfExtractionError

        try:
            result = CompyEngine().compare(
                self.pdf_v1, self.pdf_v2, self.output_dir, progress=self.progress.emit
            )
        except PdfExtractionError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"Comparison failed: {exc}")
            return
        records = [change_record(item) for item in result.diff_items]
        old_meta = result.old_document.document_metadata
        new_meta = result.new_document.document_metadata
        compared = [s for s in result.new_document.sections if s.comparison_enabled]
        changed_sections = len({c.section_number for c in result.diff_items if c.section_number})
        meta = {
            "timings": dict(result.timings),
            "v1_title": old_meta.title or old_meta.file_name,
            "v1_pages": old_meta.page_count,
            "v2_title": new_meta.title or new_meta.file_name,
            "v2_pages": new_meta.page_count,
            "sections_total": len(result.new_document.sections),
            "sections_compared": len(compared),
            "sections_changed": changed_sections,
        }

        # Build the visual side-by-side model (changed pages + highlight boxes).
        self.progress.emit("Building visual diff...")
        try:
            from backend.compy.visual_diff import build_visual_diff

            visual = build_visual_diff(self.pdf_v1, self.pdf_v2, result.diff_items)
        except Exception:
            visual = None
        self.finished_ok.emit(result.output_dir, records, meta, visual)


def change_record(item: object) -> dict:
    """Flatten a DiffItem into a row for the results table."""
    return {
        "type": str(getattr(item, "change_type", "")).lower(),
        "number": str(getattr(item, "section_number", "")).strip(),
        "section": _section_label(
            str(getattr(item, "section_number", "")),
            str(getattr(item, "section_title", "")),
        ),
        "page": str(getattr(item, "page_v2", "") or getattr(item, "page_v1", "")).strip(),
        "old": " ".join(str(getattr(item, "old_snippet", "")).split()),
        "new": " ".join(str(getattr(item, "new_snippet", "")).split()),
        "old_prefix": str(getattr(item, "old_prefix", "")),
        "old_change": str(getattr(item, "old_change", "")),
        "old_suffix": str(getattr(item, "old_suffix", "")),
        "new_prefix": str(getattr(item, "new_prefix", "")),
        "new_change": str(getattr(item, "new_change", "")),
        "new_suffix": str(getattr(item, "new_suffix", "")),
    }


def _snippet_html(prefix: str, change: str, suffix: str, full: str, color: str) -> str:
    """White context with ONLY the changed words coloured (red for old, green for new)."""
    from html import escape

    if not change and not prefix and not suffix:
        # Whole-section add/remove (no fine-grained span): colour the whole snippet.
        body = f'<span style="color:{color}">{escape(full)}</span>' if full else ""
        return f'<span style="color:{TABLE_FG}">{body}</span>'
    parts = []
    if prefix:
        parts.append(escape(prefix))
    if change:
        parts.append(f'<span style="color:{color}; font-weight:bold">{escape(change)}</span>')
    text = " ".join(parts)
    if suffix:
        sep = "" if suffix[0] in ".,;:!?)]}%" else " "
        text = f"{text}{sep}{escape(suffix)}"
    return f'<span style="color:{TABLE_FG}">{text}</span>'


def format_diff_item(item: object) -> str:
    change_type = str(getattr(item, "change_type", "")).lower()
    section = _section_label(
        str(getattr(item, "section_number", "")),
        str(getattr(item, "section_title", "")),
    )
    old_snippet = str(getattr(item, "old_snippet", "")).strip()
    new_snippet = str(getattr(item, "new_snippet", "")).strip()
    summary = str(getattr(item, "ai_summary", "") or getattr(item, "deterministic_summary", "")).strip()
    page = str(getattr(item, "page_v2", "") or getattr(item, "page_v1", "")).strip()
    where = f"section {section}" + (f" (Page {page})" if page else "")

    if change_type == "added":
        detail = _shorten(new_snippet or summary)
        return f"Added in {where}: {detail}"
    if change_type == "deleted":
        detail = _shorten(old_snippet or summary)
        return f"Deleted from {where}: {detail}"
    if change_type == "changed":
        old_detail = _shorten(old_snippet)
        new_detail = _shorten(new_snippet)
        if old_detail and new_detail:
            return f"Changed {where}: {old_detail} -> {new_detail}"
        return f"Changed {where}: {_shorten(summary)}"
    return f"{change_type.title() or 'Changed'} {where}: {_shorten(summary)}"


def _record_line(record: dict) -> str:
    where = f"section {record['section']}" + (f" (Page {record['page']})" if record["page"] else "")
    if record["type"] == "added":
        return f"Added in {where}: {_shorten(record['new'])}"
    if record["type"] == "deleted":
        return f"Deleted from {where}: {_shorten(record['old'])}"
    return f"Changed {where}: {_shorten(record['old'])} -> {_shorten(record['new'])}"


def _fmt_duration(seconds: float) -> str:
    """Format seconds as 'MM:SS min' (>= 1 min) or 'S.s sec' (under a minute)."""
    seconds = max(0.0, float(seconds or 0))
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    if minutes > 0:
        return f"{minutes:02d}:{int(round(rest)):02d} min"
    return f"{rest:.1f} sec"


def _section_label(number: str, title: str) -> str:
    label = f"{number} {title}".strip()
    return label or "Document"


def _shorten(value: str, limit: int = 180) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return "content"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


class RichTextDelegate(QStyledItemDelegate):
    """Render a cell's HTML (so only the changed words are coloured) on dark grey."""

    def paint(self, painter, option, index) -> None:
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        painter.save()
        if options.state & QStyle.State_Selected:
            painter.fillRect(option.rect, options.palette.highlight())
        else:
            background = index.data(Qt.BackgroundRole)
            painter.fillRect(option.rect, background if background is not None else QColor(TABLE_BG))

        doc = QTextDocument()
        doc.setHtml(options.text or "")
        doc.setTextWidth(max(0, option.rect.width() - 8))
        painter.translate(option.rect.left() + 4, option.rect.top() + 3)
        clip = QRectF(0, 0, option.rect.width() - 8, option.rect.height() - 6)
        painter.setClipRect(clip)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.clip = clip
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        doc = QTextDocument()
        doc.setHtml(options.text or "")
        width = options.rect.width() if options.rect.width() > 0 else 320
        doc.setTextWidth(max(0, width - 8))
        return QSize(int(doc.idealWidth()) + 8, int(doc.size().height()) + 8)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("COMPY")
        self.setMinimumSize(860, 560)
        self.worker: CompareWorker | None = None
        self._preview: dict = {}  # tag -> (title, pages) for the PDF-info panel
        self.visual = None  # VisualDiff model from the last run
        self._render_cache: dict = {}  # (side, group_index) -> QPixmap

        self.v1_input = QLineEdit()
        self.v2_input = QLineEdit()
        self.output_input = QLineEdit(str(Path("outputs") / "compy_ui_run"))
        self.status = QLabel("Ready")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.kpi_label = QLabel("")
        self.kpi_label.setStyleSheet("font-size: 15px; font-weight: 600; padding: 6px 2px;")
        self.table = self._build_table()

        # Small panel under the Compare button: per-version PDF title + page count.
        self.pdf_info = QLabel("")
        self.pdf_info.setTextFormat(Qt.RichText)
        self.pdf_info.setWordWrap(True)
        self.pdf_info.setStyleSheet(
            "background:#1f1f1f; color:#e8e8e8; border-radius:6px; padding:8px 12px; font-size:13px;"
        )
        # Bottom panel: processing-time + section KPIs.
        self.stats_panel = QLabel("")
        self.stats_panel.setTextFormat(Qt.RichText)
        self.stats_panel.setWordWrap(True)
        self.stats_panel.setStyleSheet(
            "background:#03234B; color:#ffffff; border-radius:6px; padding:10px 14px; font-size:13px;"
        )

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._header())
        layout.addLayout(self._file_row("PDF V1", self.v1_input, tag="V1"))
        layout.addLayout(self._file_row("PDF V2", self.v2_input, tag="V2"))
        layout.addLayout(self._file_row("Output", self.output_input, directory=True))

        compare_button = QPushButton("Compare")
        compare_button.clicked.connect(self.compare)
        layout.addWidget(compare_button)
        layout.addWidget(self.status)
        layout.addWidget(self.pdf_info)

        changes_tab = QWidget()
        changes_layout = QVBoxLayout(changes_tab)
        changes_layout.addWidget(self.kpi_label)
        changes_layout.addWidget(self.table)

        tabs = QTabWidget()
        tabs.addTab(changes_tab, "Changes")
        tabs.addTab(self._build_visual_tab(), "Visual Diff")
        tabs.addTab(self.log, "Log")
        layout.addWidget(tabs)
        layout.addWidget(self.stats_panel)
        self.setCentralWidget(root)

    def _build_table(self) -> QTableWidget:
        headers = ["Type", "Section #", "Section", "Page", "V1 (old)", "V2 (new)"]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setWordWrap(True)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet(
            f"QTableWidget {{ background-color: {TABLE_BG}; color: {TABLE_FG};"
            f" gridline-color: #444; }}"
            f" QHeaderView::section {{ background-color: #1f1f1f; color: {TABLE_FG};"
            f" padding: 6px; border: 0px; font-weight: 600; }}"
            f" QTableCornerButton::section {{ background-color: #1f1f1f; }}"
        )
        # Render the V1/V2 columns as HTML so only the changed words are coloured.
        self.rich_delegate = RichTextDelegate(table)
        table.setItemDelegateForColumn(4, self.rich_delegate)
        table.setItemDelegateForColumn(5, self.rich_delegate)
        header = table.horizontalHeader()
        for col in (0, 1, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        return table

    def _build_visual_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)

        top = QHBoxLayout()
        legend = QLabel(
            '<b>Legend:</b> &nbsp;<span style="color:#1a7f37">■ Added</span>'
            '&nbsp;&nbsp;<span style="color:#b42318">■ Deleted</span>'
            '&nbsp;&nbsp;<span style="color:#b54708">■ Changed</span>'
        )
        legend.setTextFormat(Qt.RichText)
        self.prev_btn = QPushButton("◀ Prev")
        self.next_btn = QPushButton("Next ▶")
        self.prev_btn.clicked.connect(lambda: self._step_group(-1))
        self.next_btn.clicked.connect(lambda: self._step_group(1))
        top.addWidget(legend)
        top.addStretch(1)
        top.addWidget(self.prev_btn)
        top.addWidget(self.next_btn)
        outer.addLayout(top)

        self.nav_list = QListWidget()
        self.nav_list.setMinimumWidth(220)
        self.nav_list.setMaximumWidth(300)
        self.nav_list.currentRowChanged.connect(self._on_group_selected)

        self.old_view = QLabel("")
        self.new_view = QLabel("")
        for view in (self.old_view, self.new_view):
            view.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        old_scroll = QScrollArea()
        old_scroll.setWidget(self.old_view)
        old_scroll.setWidgetResizable(False)
        new_scroll = QScrollArea()
        new_scroll.setWidget(self.new_view)
        new_scroll.setWidgetResizable(False)

        def titled(title: str, widget: QWidget) -> QWidget:
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            heading = QLabel(title)
            heading.setStyleSheet("font-weight:600; padding:2px;")
            box_layout.addWidget(heading)
            box_layout.addWidget(widget)
            return box

        pages = QSplitter(Qt.Horizontal)
        pages.addWidget(titled("V1 (old)", old_scroll))
        pages.addWidget(titled("V2 (new)", new_scroll))
        pages.setSizes([500, 500])

        main = QSplitter(Qt.Horizontal)
        main.addWidget(self.nav_list)
        main.addWidget(pages)
        main.setSizes([240, 900])
        outer.addWidget(main, 1)

        self.visual_empty = QLabel("Run a comparison to see changed pages side by side.")
        self.visual_empty.setStyleSheet("color:#667; padding:6px;")
        outer.addWidget(self.visual_empty)
        return tab

    def _set_visual(self, visual) -> None:
        self.visual = visual
        self._render_cache.clear()
        self.nav_list.clear()
        self.old_view.clear()
        self.new_view.clear()
        groups = getattr(visual, "groups", None) if visual is not None else None
        if not groups:
            self.visual_empty.setText("No changed pages to show.")
            self.visual_empty.show()
            return
        self.visual_empty.hide()
        for group in groups:
            sec = group.section_number or "—"
            badge = "\U0001F534 Major" if group.severity == "major" else "▪ Minor"
            item = QListWidgetItem(
                f"{badge}\nSec {sec}  ·  p{group.v1_page or '-'}→{group.v2_page or '-'}"
                f"  ·  {group.change_count} change(s)"
            )
            self.nav_list.addItem(item)
        self.nav_list.setCurrentRow(0)  # triggers the first render

    def _step_group(self, delta: int) -> None:
        if self.nav_list.count() == 0:
            return
        row = max(0, min(self.nav_list.count() - 1, self.nav_list.currentRow() + delta))
        self.nav_list.setCurrentRow(row)

    def _on_group_selected(self, row: int) -> None:
        groups = getattr(self.visual, "groups", None)
        if not groups or row < 0 or row >= len(groups):
            return
        group = groups[row]
        self._render_side("old", row, group)
        self._render_side("new", row, group)

    def _render_side(self, side: str, row: int, group) -> None:
        label = self.old_view if side == "old" else self.new_view
        cache_key = (side, row)
        pixmap = self._render_cache.get(cache_key)
        if pixmap is None:
            pdf = self.visual.v1_pdf if side == "old" else self.visual.v2_pdf
            page = group.v1_page if side == "old" else group.v2_page
            highlights = group.v1_highlights if side == "old" else group.v2_highlights
            if not page:
                label.setPixmap(QPixmap())
                label.setText("(no matching page)")
                label.adjustSize()
                return
            try:
                from backend.compy.visual_diff import render_page

                png = render_page(pdf, page - 1, highlights)
                pixmap = QPixmap()
                pixmap.loadFromData(png)
                self._render_cache[cache_key] = pixmap
            except Exception as exc:  # pragma: no cover - defensive
                label.setText(f"(could not render page: {exc})")
                label.adjustSize()
                return
        label.setText("")
        label.setPixmap(pixmap)
        label.adjustSize()

    def _header(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        logo_path = Path(__file__).resolve().parents[1] / "LOGO" / "ST_LOGO.png"
        logo = QLabel()
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path)).scaledToHeight(48)
            logo.setPixmap(pixmap)
        title = QLabel("COMPY PDF Revision Assistant")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #03234B;")
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addStretch(1)
        return widget

    def _file_row(
        self, label: str, line_edit: QLineEdit, directory: bool = False, tag: str = ""
    ) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addWidget(line_edit)
        button = QPushButton("Browse")
        button.clicked.connect(lambda: self._browse(line_edit, directory, tag))
        layout.addWidget(button)
        return layout

    def _browse(self, line_edit: QLineEdit, directory: bool, tag: str = "") -> None:
        if directory:
            selected = QFileDialog.getExistingDirectory(self, "Select output directory")
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self, "Select PDF", "", "PDF files (*.pdf)"
            )
        if selected:
            line_edit.setText(selected)
            if tag and not directory:
                self._preview_pdf(tag, selected)

    def compare(self) -> None:
        if not self.v1_input.text() or not self.v2_input.text():
            QMessageBox.warning(self, "Missing PDFs", "Select both PDF V1 and PDF V2.")
            return
        self.status.setText("Comparing...")
        self.log.clear()
        self.table.setRowCount(0)
        self.kpi_label.setText("Comparing...")
        self.stats_panel.setText("")
        self.log.append("Starting comparison.")
        self.worker = CompareWorker(
            self.v1_input.text(), self.v2_input.text(), self.output_input.text()
        )
        self.worker.finished_ok.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.worker.progress.connect(self.status.setText)
        self.worker.start()

    def _finished(self, output_dir: str, records: list, meta: dict, visual=None) -> None:
        self.status.setText("Complete")
        self._populate_table(records)
        self._populate_kpis(records)
        self._set_pdf_info(meta)
        self._set_stats(meta)
        self._set_visual(visual)

        self.log.append(f"Detected {len(records)} changes.")
        if records:
            self.log.append("")
            self.log.append("Changes found:")
            for record in records:
                self.log.append(f"- {_record_line(record)}")
        else:
            self.log.append("No section changes found.")
        self.log.append("")
        self.log.append(f"Artifacts: {output_dir}")

    def _populate_kpis(self, records: list) -> None:
        counts = {"added": 0, "deleted": 0, "changed": 0}
        for record in records:
            if record["type"] in counts:
                counts[record["type"]] += 1
        total = sum(counts.values())
        self.kpi_label.setText(
            f"Total: {total}    "
            f"🟢 Added: {counts['added']}    "
            f"🔴 Deleted: {counts['deleted']}    "
            f"🟠 Changed: {counts['changed']}"
        )

    def _populate_table(self, records: list) -> None:
        self.table.setRowCount(len(records))
        bg = QBrush(QColor(TABLE_BG))
        white = QBrush(QColor(TABLE_FG))
        for row, record in enumerate(records):
            label, type_color = TYPE_STYLE.get(record["type"], (record["type"].title(), TABLE_FG))
            type_item = QTableWidgetItem(label)
            type_item.setForeground(QBrush(QColor(type_color)))
            bold = QFont()
            bold.setBold(True)
            type_item.setFont(bold)

            old_html = _snippet_html(
                record["old_prefix"], record["old_change"], record["old_suffix"],
                record["old"], DELETED_COLOR,
            )
            new_html = _snippet_html(
                record["new_prefix"], record["new_change"], record["new_suffix"],
                record["new"], ADDED_COLOR,
            )
            cells = [
                type_item,
                QTableWidgetItem(record["number"] or "—"),
                QTableWidgetItem(record["section"]),
                QTableWidgetItem(f"Page {record['page']}" if record["page"] else ""),
                QTableWidgetItem(old_html),  # delegate renders this as HTML
                QTableWidgetItem(new_html),
            ]
            for col, cell in enumerate(cells):
                cell.setBackground(bg)
                if col in (1, 2, 3):
                    cell.setForeground(white)
                cell.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
                self.table.setItem(row, col, cell)
        self.table.resizeRowsToContents()

    def _set_pdf_info(self, meta: dict) -> None:
        from html import escape

        def line(tag: str, title: str, pages) -> str:
            pages_txt = f"{pages} pages" if pages else "? pages"
            return (
                f'<b style="color:#5b9bd5">{tag}</b>&nbsp; {escape(str(title) or "—")}'
                f'&nbsp;·&nbsp; <span style="color:#9fd3a0">{pages_txt}</span>'
            )

        self.pdf_info.setText(
            line("V1", meta.get("v1_title", ""), meta.get("v1_pages"))
            + "<br>"
            + line("V2", meta.get("v2_title", ""), meta.get("v2_pages"))
        )

    def _set_stats(self, meta: dict) -> None:
        t = meta.get("timings", {})
        extraction = float(t.get("extraction", 0))
        structuring = float(t.get("structuring", 0))
        total = float(t.get("total", 0))
        comparing = max(0.0, total - extraction - structuring)
        timing = (
            "⏱ <b>Processing time</b> &nbsp;—&nbsp; "
            f"Extraction <b>{_fmt_duration(extraction)}</b> &nbsp;·&nbsp; "
            f"Structuring Sections <b>{_fmt_duration(structuring)}</b> &nbsp;·&nbsp; "
            f"Comparing <b>{_fmt_duration(comparing)}</b> &nbsp;·&nbsp; "
            f"Total <b>{_fmt_duration(total)}</b>"
        )
        stats = (
            "📊 <b>{total_s}</b> sections &nbsp;({compared} compared, {changed} changed)"
            " &nbsp;·&nbsp; V1 {v1}p &nbsp;·&nbsp; V2 {v2}p"
        ).format(
            total_s=meta.get("sections_total", 0),
            compared=meta.get("sections_compared", 0),
            changed=meta.get("sections_changed", 0),
            v1=meta.get("v1_pages", 0),
            v2=meta.get("v2_pages", 0),
        )
        self.stats_panel.setText(timing + "<br>" + stats)

    def _preview_pdf(self, tag: str, path: str) -> None:
        """Best-effort: show title + page count as soon as a PDF is picked."""
        try:
            import fitz  # type: ignore

            doc = fitz.open(path)
            title = (doc.metadata or {}).get("title") or Path(path).name
            pages = doc.page_count
            doc.close()
            self._preview[tag] = (title, pages)
        except Exception:
            self._preview[tag] = (Path(path).name, None)
        self._set_pdf_info(
            {
                "v1_title": self._preview.get("V1", ("", None))[0],
                "v1_pages": self._preview.get("V1", ("", None))[1],
                "v2_title": self._preview.get("V2", ("", None))[0],
                "v2_pages": self._preview.get("V2", ("", None))[1],
            }
        )

    def _failed(self, message: str) -> None:
        self.status.setText("Failed")
        self.log.append(message)
        QMessageBox.critical(self, "COMPY failed", message)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(200, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
