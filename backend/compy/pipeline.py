"""End-to-end COMPY MVP1 pipeline."""

from __future__ import annotations

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

    def run(
        self,
        pdf_v1: str | Path,
        pdf_v2: str | Path,
        output_dir: str | Path | None = None,
        progress: "Callable[[str], None] | None" = None,
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
        notify("Extracting V1...")
        old_extraction = self.extractor.extract(old_path, old_doc_dir)
        notify("Extracting V2...")
        new_extraction = self.extractor.extract(new_path, new_doc_dir)

        notify("Structuring sections...")
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

        notify("Matching sections...")
        matches = self.matcher.match(old_document, new_document)
        notify("Comparing changed sections...")
        diff_items = self.diff_engine.diff(old_document, new_document, matches)
        notify("Summarizing changes...")
        summarized = self.summarizer.summarize(diff_items)
        notify("Writing report..." if out is not None else "Finalizing...")
        revision_entries = self.report_builder.build(summarized, matches, out)

        return ComparisonJobResult(
            old_document=old_document,
            new_document=new_document,
            section_matches=matches,
            diff_items=summarized,
            revision_entries=revision_entries,
            output_dir=str(out) if out is not None else "",
            kpi_summary=ReportBuilder.kpi_summary(summarized),
        )
