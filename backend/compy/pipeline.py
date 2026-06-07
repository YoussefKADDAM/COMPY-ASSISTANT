"""End-to-end COMPY MVP1 pipeline."""

from __future__ import annotations

import time
from pathlib import Path

from .diff_engine import DiffEngine
from .extractor import PdfExtractor
from .io import ensure_dir
from .llm import ChangeSummarizer, LLMClient, LLMConfig
from .matcher import SectionMatcher
from .models import ComparisonJobResult
from .normalizer import DocumentNormalizer
from .reporting import ReportBuilder
from .text_utils import slugify


class ComparisonPipeline:
    def __init__(
        self,
        extractor: PdfExtractor | None = None,
        normalizer: DocumentNormalizer | None = None,
        matcher: SectionMatcher | None = None,
        diff_engine: DiffEngine | None = None,
        summarizer: ChangeSummarizer | None = None,
        report_builder: ReportBuilder | None = None,
    ) -> None:
        self.extractor = extractor or PdfExtractor()
        self.normalizer = normalizer or DocumentNormalizer()
        self.matcher = matcher or SectionMatcher()
        self.diff_engine = diff_engine or DiffEngine()
        self.summarizer = summarizer or ChangeSummarizer()
        self.report_builder = report_builder or ReportBuilder()

    @classmethod
    def with_llm_config(cls, llm_config: LLMConfig) -> "ComparisonPipeline":
        return cls(summarizer=ChangeSummarizer(LLMClient(llm_config)))

    @staticmethod
    def _should_parallelize(path_v1: Path, path_v2: Path, min_total_pages: int = 120) -> bool:
        """Parallelize only when the combined page count makes the spawn cost worth it."""
        try:
            import fitz  # type: ignore

            total = 0
            for path in (path_v1, path_v2):
                doc = fitz.open(str(path))
                total += doc.page_count
                doc.close()
            return total >= min_total_pages
        except Exception:
            return False

    def run(
        self,
        pdf_v1: str | Path,
        pdf_v2: str | Path,
        output_dir: str | Path | None = None,
        progress: "Callable[[str], None] | None" = None,
        debug: bool = False,
        parallel: bool = True,
    ) -> ComparisonJobResult:
        def notify(message: str) -> None:
            if progress is not None:
                progress(message)

        # output_dir=None => run fully in memory (no artifacts written), for embedding.
        if output_dir is not None:
            out: Path | None = ensure_dir(Path(output_dir))
            old_doc_dir: Path | None = ensure_dir(out / "v1")
            new_doc_dir: Path | None = ensure_dir(out / "v2")
        else:
            out = old_doc_dir = new_doc_dir = None

        old_path = Path(pdf_v1)
        new_path = Path(pdf_v2)

        timings: dict[str, float] = {}
        run_start = time.perf_counter()

        old_extraction = new_extraction = None
        stage_start = time.perf_counter()
        # Large documents: extract both versions in parallel processes (PyMuPDF is
        # not thread-safe). Small documents skip it -- process spawn overhead would
        # make them slower. Any failure falls back to sequential, so it never breaks.
        if parallel and self._should_parallelize(old_path, new_path):
            try:
                from .parallel import extract_pair_parallel

                jobs = [("V1", old_path, old_doc_dir, debug), ("V2", new_path, new_doc_dir, debug)]
                results = extract_pair_parallel(jobs, progress)
                old_extraction, new_extraction = results["V1"], results["V2"]
            except Exception as exc:  # pragma: no cover - environment dependent
                notify(f"Parallel extraction unavailable ({type(exc).__name__}); running sequentially")
                old_extraction = new_extraction = None

        if old_extraction is None or new_extraction is None:
            old_extraction = self.extractor.extract(old_path, old_doc_dir, progress, debug)
            new_extraction = self.extractor.extract(new_path, new_doc_dir, progress, debug)
        timings["extraction"] = time.perf_counter() - stage_start

        notify("Structuring sections...")
        stage_start = time.perf_counter()
        old_document = self.normalizer.normalize(
            document_id=slugify(old_path.stem, "document_v1"),
            source_pdf=old_path.name,
            extraction=old_extraction,
            output_dir=old_doc_dir,
        )
        new_document = self.normalizer.normalize(
            document_id=slugify(new_path.stem, "document_v2"),
            source_pdf=new_path.name,
            extraction=new_extraction,
            output_dir=new_doc_dir,
        )
        timings["structuring"] = time.perf_counter() - stage_start

        notify("Matching sections...")
        stage_start = time.perf_counter()
        matches = self.matcher.match(old_document, new_document)
        timings["matching"] = time.perf_counter() - stage_start

        notify("Comparing changed sections...")
        stage_start = time.perf_counter()
        diff_items = self.diff_engine.diff(old_document, new_document, matches)
        timings["diffing"] = time.perf_counter() - stage_start

        notify("Summarizing changes...")
        stage_start = time.perf_counter()
        summarized = self.summarizer.summarize(diff_items)
        timings["summarizing"] = time.perf_counter() - stage_start

        notify("Writing report..." if out is not None else "Finalizing...")
        stage_start = time.perf_counter()
        revision_entries = self.report_builder.build(summarized, matches, out)
        timings["reporting"] = time.perf_counter() - stage_start
        timings["total"] = time.perf_counter() - run_start

        return ComparisonJobResult(
            old_document=old_document,
            new_document=new_document,
            section_matches=matches,
            diff_items=summarized,
            revision_entries=revision_entries,
            output_dir=str(out) if out is not None else "",
            kpi_summary=ReportBuilder.kpi_summary(summarized),
            timings=timings,
        )
