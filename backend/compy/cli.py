"""Command-line entrypoint for COMPY MVP1."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .engine import CompyEngine
from .extractor import PdfExtractionError
from .llm import LLMConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two technical PDFs with COMPY.")
    parser.add_argument("pdf_v1", help="Path to the old PDF")
    parser.add_argument("pdf_v2", help="Path to the new PDF")
    parser.add_argument("--output-dir", default="outputs/compy_run", help="Directory for JSON and HTML artifacts")
    parser.add_argument("--llm-provider", default="none", choices=["none", "openai", "stgpt"], help="LLM provider for summaries")
    parser.add_argument("--llm-model", default="gpt-4o-mini", help="Model name for the configured provider")
    parser.add_argument("--llm-base-url", default="", help="Override chat-completions compatible endpoint")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = ""
    if args.llm_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
    elif args.llm_provider == "stgpt":
        api_key = os.getenv("STGPT_API_KEY", "")
    config = LLMConfig(
        provider=args.llm_provider,
        model=args.llm_model,
        api_key=api_key,
        base_url=args.llm_base_url,
    )
    engine = CompyEngine(config)
    try:
        result = engine.compare(args.pdf_v1, args.pdf_v2, Path(args.output_dir))
    except PdfExtractionError as exc:
        print(f"PDF extraction failed: {exc}", file=sys.stderr)
        return 2

    kpis = result.kpi_summary
    print(f"COMPY comparison complete: {kpis['total']} changes detected")
    print(f"  Added:   {kpis['added']}")
    print(f"  Deleted: {kpis['deleted']}")
    print(f"  Changed: {kpis['changed']}")
    print(f"Artifacts written to: {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
