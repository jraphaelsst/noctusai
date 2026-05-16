"""Deterministic content aggregates — the LLM-counting-trap fix.

Reconciled 2026-05-16 by `projects/social-wiring-absorption/` Wave 1.E3
from the workspace intake's `_compute_content_stats`
(`SESSION-NOTES_drive-api-2026-05-13.md` §3).

THE BUG THIS PREVENTS
---------------------
First live test: user asked "how many lines with code ONE?" against
a 198-line CSV. The LLM answered 35 (truth: 183 lines / 176 unique).
LLMs pattern-match the first few rows of long structured data and
extrapolate — they cannot count reliably even when the full payload
is in context. Fix: precompute aggregates in Python; the tool
description forbids the model from recomputing and points it at the
`stats` field as ground truth. Re-test matched Python exactly.

This helper is GENERIC (line/char/CSV-shape counts). The
real-estate-specific "ONE-code" regex stays a per-product concern —
products pass their own domain extractor on top of these base
stats; it does NOT belong in the seed.

NOTE for the architect / W1.E1: `SESSION-NOTES_drive-api §3`
recommends this lift to `noctusai_lib.domain.chatbot` as a generic
`compute_aggregates(text, schema_hints)` consumed by ALL
LLM-over-structured-data tools (transcripts → wpm, email digests →
unread count, calendar → events/day). It is Drive-scoped here to
respect Wave-1 file-disjoint discipline (`domain/chatbot/` is
W1.E1's package). Promote to `domain/chatbot` at integration —
flagged in the engineer return as a cross-package wiring need.
"""

from __future__ import annotations


def compute_content_stats(text: str, *, rendered_as: str) -> dict:
    """Compute deterministic aggregates over text content.

    Always returns `total_chars`, `total_lines`, `non_empty_lines`.
    When `rendered_as == "text/csv"` (a Sheets export) it additionally
    parses the header + column count + data-row count so the LLM can
    quote `stats.csv_data_rows` instead of miscounting.

    Args:
        text: the decoded file content.
        rendered_as: the `DriveFileContent.rendered_as` hint
            (`"text/csv"` triggers CSV shape analysis).

    Returns a dict the consumer attaches to the tool response as
    `stats`. The tool description MUST instruct the LLM to quote this
    field verbatim and NEVER recount from the raw text.
    """
    lines = text.split("\n")
    # Trailing newline produces an empty final element — don't count it
    # as a line (matches `wc -l`-style intuition the operator verifies).
    if lines and lines[-1] == "":
        lines = lines[:-1]
    non_empty = [ln for ln in lines if ln.strip()]
    stats: dict = {
        "total_chars": len(text),
        "total_lines": len(lines),
        "non_empty_lines": len(non_empty),
    }
    if rendered_as == "text/csv" and lines:
        header = lines[0]
        # Naive split is correct for the well-formed Sheets exports we
        # see; quoted-comma CSVs would need the csv module, deferred
        # until a consumer hits a quoted-field sheet (no-premature-
        # complexity — surfaced as a follow-up, not silently skipped).
        columns = header.split(",")
        stats["csv_header"] = header
        stats["csv_column_count"] = len(columns)
        stats["csv_data_rows"] = max(len(non_empty) - 1, 0)
    return stats


__all__ = ["compute_content_stats"]
