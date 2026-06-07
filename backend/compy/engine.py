"""Public facade for embedding COMPY in another application.

`CompyEngine` is the one class an outside app needs. It hides the internal
pipeline wiring (extractor -> normalizer -> matcher -> diff -> summarizer ->
report) behind a small, stable API and can run fully in memory (no files) or
also write artifacts to a directory.

Example
-------
    from backend.compy import CompyEngine

    engine = CompyEngine()
    result = engine.compare("v1.pdf", "v2.pdf")          # in memory
    print(result.kpi_summary)                            # {'added':.., 'deleted':.., 'changed':.., 'total':..}
    for change in result.changes:                        # one DiffItem per edit
        print(change.change_type, change.section_number, change.page_v2, change.new_change)

    # With artifacts on disk and a progress callback:
    result = engine.compare("v1.pdf", "v2.pdf", output_dir="outputs/run1",
                            progress=print)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .llm import LLMConfig
from .models import ComparisonJobResult
from .pipeline import ComparisonPipeline


class CompyEngine:
    """Stable, embedding-friendly entry point for a single PDF comparison."""

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self._pipeline = (
            ComparisonPipeline.with_llm_config(llm_config)
            if llm_config is not None
            else ComparisonPipeline()
        )

    def compare(
        self,
        pdf_v1: str | Path,
        pdf_v2: str | Path,
        output_dir: str | Path | None = None,
        progress: Optional[Callable[[str], None]] = None,
        debug: bool = False,
    ) -> ComparisonJobResult:
        """Compare two PDFs and return the result.

        Parameters
        ----------
        pdf_v1, pdf_v2 : paths to the old and new PDF.
        output_dir     : if given, JSON/HTML artifacts are written there; if
                         ``None`` (default) the run is fully in memory.
        progress       : optional callback receiving short status strings.

        Returns
        -------
        ComparisonJobResult with ``.changes`` (per-edit ``DiffItem`` list),
        ``.kpi_summary`` (added/deleted/changed/total), ``.revision_entries``,
        and the matched documents. Set ``debug=True`` to also write the large
        per-page ``pages.json`` artifact (off by default for large PDFs).
        """
        return self._pipeline.run(pdf_v1, pdf_v2, output_dir, progress=progress, debug=debug)
