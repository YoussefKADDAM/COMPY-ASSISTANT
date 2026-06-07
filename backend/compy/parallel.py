"""Parallel extraction of the two PDF versions using a process pool.

PyMuPDF is not thread-safe, so to extract V1 and V2 at the same time we use
separate *processes*. Each worker reports page-level progress back to the parent
through a shared queue, so the UI can show both versions advancing together
("V1 page 1200/6000 | V2 page 1100/5800").

This is best-effort: callers should fall back to sequential extraction if
`extract_pair_parallel` raises (e.g. on a locked-down environment that cannot
spawn processes).
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
from pathlib import Path
from queue import Empty
from typing import Callable, Optional

from .models import ExtractionResult


def _extract_worker(path: str, output_dir: Optional[str], debug: bool, queue, tag: str) -> ExtractionResult:
    """Runs in a child process: extract one PDF, reporting progress to `queue`."""
    from .extractor import PdfExtractor

    def progress(message: str) -> None:
        try:
            queue.put((tag, message))
        except Exception:
            pass

    return PdfExtractor().extract(path, output_dir, progress, debug)


def extract_pair_parallel(
    jobs: "list[tuple[str, Path, Optional[Path], bool]]",
    notify: Optional[Callable[[str], None]] = None,
) -> "dict[str, ExtractionResult]":
    """Extract several PDFs concurrently.

    ``jobs`` is a list of ``(tag, path, output_dir, debug)``. Returns
    ``{tag: ExtractionResult}``. Raises if the pool cannot be used.
    """
    results: dict[str, ExtractionResult] = {}
    with Manager() as manager:
        queue = manager.Queue()
        status = {tag: "" for (tag, *_rest) in jobs}
        order = [tag for (tag, *_rest) in jobs]

        def flush() -> None:
            updated = False
            while True:
                try:
                    tag, message = queue.get_nowait()
                except Empty:
                    break
                status[tag] = message
                updated = True
            if updated and notify is not None:
                notify("   |   ".join(status[t] for t in order if status[t]))

        with ProcessPoolExecutor(max_workers=len(jobs)) as executor:
            future_to_tag = {
                executor.submit(
                    _extract_worker, str(path), (str(out) if out is not None else None), debug, queue, tag
                ): tag
                for (tag, path, out, debug) in jobs
            }
            pending = set(future_to_tag)
            while pending:
                flush()
                for future in [f for f in pending if f.done()]:
                    results[future_to_tag[future]] = future.result()  # raises on worker error
                    pending.discard(future)
                if pending:
                    time.sleep(0.05)
            flush()
    return results
