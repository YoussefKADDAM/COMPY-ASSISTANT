# Embedding COMPY in another application

COMPY is fully object-oriented. To embed it you only need **one class**:
`CompyEngine` (a facade over the internal pipeline). Everything else
(extractor, normalizer, matcher, diff, summarizer, report) stays internal.

## Quick start

```python
from backend.compy import CompyEngine

engine = CompyEngine()

# In memory (no files written) — ideal when embedding:
result = engine.compare("v1.pdf", "v2.pdf")

print(result.kpi_summary)        # {'added': 9, 'deleted': 2, 'changed': 5, 'total': 16}
for change in result.changes:    # one DiffItem per edit
    print(change.change_type,    # 'added' | 'deleted' | 'changed'
          change.section_number,  # e.g. '3.4'
          change.page_v2,         # page in V2
          change.old_change,      # only the removed/changed words (V1 side)
          change.new_change)      # only the added/changed words (V2 side)
```

## With artifacts on disk and progress updates

```python
result = engine.compare(
    "v1.pdf", "v2.pdf",
    output_dir="outputs/run1",     # writes JSON + comparison_report.html
    progress=print,                # called with short status strings
)
print(result.output_dir)
```

## With STGpt / OpenAI summaries

```python
from backend.compy import CompyEngine, LLMConfig

engine = CompyEngine(LLMConfig(provider="stgpt", base_url="...", api_key="..."))
result = engine.compare("v1.pdf", "v2.pdf")
```

By default no LLM is called; the deterministic diff already fills every change.

## What you get back

`result` is a `ComparisonJobResult`:

| Field | Meaning |
| --- | --- |
| `changes` / `diff_items` | list of `DiffItem`, one per edit |
| `kpi_summary` | `{added, deleted, changed, total}` |
| `revision_entries` | human-readable revision history rows |
| `section_matches` | how V1/V2 sections aligned |
| `old_document`, `new_document` | the structured, sectioned documents |
| `output_dir` | where artifacts were written (`""` if in memory) |

### `DiffItem` fields most apps use
`change_type`, `section_number`, `section_title`, `page_v1`, `page_v2`,
`old_snippet`/`new_snippet` (full context), and the split
`old_prefix/old_change/old_suffix` + `new_prefix/new_change/new_suffix` so a host
UI can colour **only the changed words**.

## Threading note
`compare()` is synchronous and CPU-bound. Run it on a worker thread/process in a
GUI app (the bundled PySide6 UI uses a `QThread`); pass a `progress` callback to
surface status.

## Public API surface
`from backend.compy import CompyEngine, ComparisonJobResult, DiffItem,
RevisionEntry, LLMConfig`. Treat anything not exported in
`backend/compy/__init__.py` as internal and subject to change.
