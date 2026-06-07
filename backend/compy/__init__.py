"""COMPY PDF comparison backend.

Public API for embedding: import ``CompyEngine`` and call ``compare()``.
See ``docs/INTEGRATION.md``.
"""

from .engine import CompyEngine
from .llm import LLMConfig
from .models import ComparisonJobResult, DiffItem, RevisionEntry
from .pipeline import ComparisonPipeline

__all__ = [
    "CompyEngine",
    "ComparisonPipeline",
    "ComparisonJobResult",
    "DiffItem",
    "RevisionEntry",
    "LLMConfig",
]
