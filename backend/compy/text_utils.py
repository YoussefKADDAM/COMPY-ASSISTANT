"""Text cleanup, hashing, and matching helpers.

MVP1 compares prose only. The heavy lifting of separating prose from tables,
figures, and TOC lines is done upstream by the layout-aware extractor (geometry),
not here. This module therefore keeps only *generic*, document-agnostic cleanup:
normalization, hashing, and a thin structural safety net (dot-leader TOC lines,
pure-numeric table rows, generic page footers). It deliberately contains no
hardcoded document vocabulary.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Iterable


WHITESPACE_RE = re.compile(r"[ \t]+")
LINEBREAK_RE = re.compile(r"\n{3,}")
NUMERIC_TABLE_ROW_RE = re.compile(r"^[0-9A-Fa-fxX.,+\-/()%\s]+$")
SPACED_TOKEN_RUN_RE = re.compile(r"\b(?:[A-Za-z0-9]\s+){2,}[A-Za-z0-9]\b")
DOC_CODE_RE = re.compile(r"^[A-Z]{1,4}\d{3,}$", re.IGNORECASE)
PAGE_FOOTER_RE = re.compile(r"^[A-Z]{1,4}\d{3,}\s*-\s*rev\b.*\bpage\s+\d+\s*/\s*\d+\s*$", re.IGNORECASE)
TOC_LEADER_RE = re.compile(r"\.{4,}\s*\d+\s*$")
ENUM_MARKER_RE = re.compile(r"^\(?\d{1,3}\)?\.?$")  # bare list / footnote markers: "1." "2)" "(3)"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=[).A-Za-z0-9])\s*[–—]\s+(?=\d{2}:)", "\n– ", text)
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    lines = [_repair_spaced_letters(line) for line in lines]
    cleaned = "\n".join(line for line in lines if line)
    return LINEBREAK_RE.sub("\n\n", cleaned).strip()


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or fallback


def similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def first_words(text: str, limit: int = 80) -> str:
    words = text.split()
    return " ".join(words[:limit])


def combined_text(lines: Iterable[str]) -> str:
    return normalize_text("\n".join(lines))


def remove_non_text_comparison_lines(text: str) -> str:
    """Generic, document-agnostic safety net for the comparison text.

    Removes only structural noise that is unambiguous everywhere: dot-leader
    table-of-contents lines, pure-numeric table rows, generic page footers /
    document codes, and lone bullet glyphs. Real prose (including sentences that
    *mention* a table or figure) is preserved. Line structure is kept so the
    diff engine can produce line-level snippets.
    """
    kept: list[str] = []
    for line in normalize_text(text).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"•", "-", "–"} or ENUM_MARKER_RE.match(stripped):
            continue
        if is_toc_line(stripped):
            continue
        if is_boilerplate_line(stripped):
            continue
        if _is_numeric_table_row(stripped):
            continue
        kept.append(stripped)
    return "\n".join(kept)


def canonical_comparison_text(text: str) -> str:
    """Normalize prose for stable text comparison.

    Ignores case, whitespace, and low-signal punctuation so PDF extraction
    differences do not become revision-history entries.
    """
    return canonical_key(remove_non_text_comparison_lines(text))


def canonical_key(text: str) -> str:
    normalized = normalize_text(text).lower()
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def is_toc_line(line: str) -> bool:
    return bool(TOC_LEADER_RE.search(line))


def is_boilerplate_line(line: str) -> bool:
    stripped = normalize_text(line).strip()
    if not stripped:
        return True
    if PAGE_FOOTER_RE.match(stripped):
        return True
    if DOC_CODE_RE.fullmatch(stripped):
        return True
    return False


def _is_numeric_table_row(line: str) -> bool:
    tokens = line.split()
    if len(tokens) < 4:
        return False
    if not NUMERIC_TABLE_ROW_RE.match(line):
        return False
    numeric_tokens = sum(1 for token in tokens if re.search(r"\d", token))
    return numeric_tokens / len(tokens) >= 0.75


def _repair_spaced_letters(line: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        tokens = value.split()
        if len(tokens) < 3:
            return value
        if tokens[0].isdigit() and any(token.isalpha() for token in tokens[1:]):
            return tokens[0] + " " + "".join(tokens[1:])
        return "".join(tokens)

    return SPACED_TOKEN_RUN_RE.sub(replace, line)
