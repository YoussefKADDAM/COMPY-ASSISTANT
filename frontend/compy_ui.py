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
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
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


class CompareWorker(QThread):
    finished_ok = Signal(str, int, list)
    failed = Signal(str)

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
            result = ComparisonPipeline().run(self.pdf_v1, self.pdf_v2, self.output_dir)
        except PdfExtractionError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"Comparison failed: {exc}")
            return
        result_lines = [format_diff_item(item) for item in result.diff_items]
        self.finished_ok.emit(result.output_dir, len(result.diff_items), result_lines)


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

        tabs = QTabWidget()
        tabs.addTab(self.log, "Results")
        layout.addWidget(tabs)
        self.setCentralWidget(root)

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
        self.log.append("Starting comparison.")
        self.worker = CompareWorker(
            self.v1_input.text(), self.v2_input.text(), self.output_input.text()
        )
        self.worker.finished_ok.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _finished(self, output_dir: str, change_count: int, result_lines: list) -> None:
        self.status.setText("Complete")
        self.log.append(f"Detected {change_count} changes.")
        if result_lines:
            self.log.append("")
            self.log.append("Changes found:")
            for line in result_lines:
                self.log.append(f"- {line}")
        else:
            self.log.append("No section changes found.")
        self.log.append("")
        self.log.append(f"Artifacts: {output_dir}")

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
