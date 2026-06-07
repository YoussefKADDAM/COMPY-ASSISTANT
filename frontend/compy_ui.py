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
        QMainWindow,
        QMessageBox,
        QPushButton,
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
    finished_ok = Signal(str, list)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, pdf_v1: str, pdf_v2: str, output_dir: str) -> None:
        super().__init__()
        self.pdf_v1 = pdf_v1
        self.pdf_v2 = pdf_v2
        self.output_dir = output_dir

    def run(self) -> None:
        _ensure_project_root()
        from backend.compy.extractor import PdfExtractionError
        from backend.compy.pipeline import ComparisonPipeline

        try:
            result = ComparisonPipeline().run(
                self.pdf_v1, self.pdf_v2, self.output_dir, progress=self.progress.emit
            )
        except PdfExtractionError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"Comparison failed: {exc}")
            return
        records = [change_record(item) for item in result.diff_items]
        self.finished_ok.emit(result.output_dir, records)


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

        self.v1_input = QLineEdit()
        self.v2_input = QLineEdit()
        self.output_input = QLineEdit(str(Path("outputs") / "compy_ui_run"))
        self.status = QLabel("Ready")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.kpi_label = QLabel("")
        self.kpi_label.setStyleSheet("font-size: 15px; font-weight: 600; padding: 6px 2px;")
        self.table = self._build_table()

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._header())
        layout.addLayout(self._file_row("PDF V1", self.v1_input))
        layout.addLayout(self._file_row("PDF V2", self.v2_input))
        layout.addLayout(self._file_row("Output", self.output_input, directory=True))

        compare_button = QPushButton("Compare")
        compare_button.clicked.connect(self.compare)
        layout.addWidget(compare_button)
        layout.addWidget(self.status)

        changes_tab = QWidget()
        changes_layout = QVBoxLayout(changes_tab)
        changes_layout.addWidget(self.kpi_label)
        changes_layout.addWidget(self.table)

        tabs = QTabWidget()
        tabs.addTab(changes_tab, "Changes")
        tabs.addTab(self.log, "Log")
        layout.addWidget(tabs)
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
        self, label: str, line_edit: QLineEdit, directory: bool = False
    ) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addWidget(line_edit)
        button = QPushButton("Browse")
        button.clicked.connect(lambda: self._browse(line_edit, directory))
        layout.addWidget(button)
        return layout

    def _browse(self, line_edit: QLineEdit, directory: bool) -> None:
        if directory:
            selected = QFileDialog.getExistingDirectory(self, "Select output directory")
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self, "Select PDF", "", "PDF files (*.pdf)"
            )
        if selected:
            line_edit.setText(selected)

    def compare(self) -> None:
        if not self.v1_input.text() or not self.v2_input.text():
            QMessageBox.warning(self, "Missing PDFs", "Select both PDF V1 and PDF V2.")
            return
        self.status.setText("Comparing...")
        self.log.clear()
        self.table.setRowCount(0)
        self.kpi_label.setText("Comparing...")
        self.log.append("Starting comparison.")
        self.worker = CompareWorker(
            self.v1_input.text(), self.v2_input.text(), self.output_input.text()
        )
        self.worker.finished_ok.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.worker.progress.connect(self.status.setText)
        self.worker.start()

    def _finished(self, output_dir: str, records: list) -> None:
        self.status.setText("Complete")
        self._populate_table(records)
        self._populate_kpis(records)

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
