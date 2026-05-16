"""Deterministic content-stats — the LLM-counting-trap fix.

LLMs misjudge totals over long structured payloads (line counts, code
occurrences, CSV row counts). When a chatbot tool returns file/sheet
content, the model should *quote* precomputed aggregates rather than
counting tokens itself. This module computes those aggregates
deterministically so the tool layer can attach a `stats` block the
model relays verbatim.

Reconciled 2026-05-16 from the live-validated
`youtube-crawler/app/services/whatsapp_intake_service.py:_compute_content_stats`
(`projects/social-wiring-absorption/` W1.E1, manifest
`multimodal-stack`). The validated implementation inlined a
real-estate-specific ``\\bONE\\d{3,6}\\b`` regex directly in the seed
candidate — that is a **per-product** concern. Here it is generalized:
the universal stats (chars / lines / non-empty / CSV shape) live in
the seed; any domain-specific code-pattern counting is supplied by the
consumer as a :class:`SchemaHint`. The real-estate ONE-code regex
therefore stays in the social-wiring product as a product-level
``SchemaHint``, NOT in seed.

Pure-logic module — no IO. Per `KB § PATTERNS/seed-fake-real-adapter.md`
the Fake-vs-Real exemption test ("would a Fake here exercise different
code than the Real?") answers *no*, so this module is correctly
Protocol-free / Fake-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaHint:
    """A per-consumer, domain-specific code-pattern counter.

    Each hint declares a regex; :func:`compute_content_stats` runs it
    over the text and, when it matches, emits three keys derived from
    `key_prefix`:

      - ``{key_prefix}_count``     — total occurrences
      - ``unique_{key_prefix}s``   — distinct match count
      - ``{key_prefix}s_sample``   — first ``sample_size`` distinct
                                     matches (sorted)

    Example (the real-estate ONE-code pattern that used to be hardcoded
    in the seed candidate — it now lives in the social-wiring product):

        ONE_CODE = SchemaHint(
            key_prefix="one_code",
            pattern=re.compile(r"\\bONE\\d{3,6}\\b"),
        )
        stats = compute_content_stats(text, schema_hints=[ONE_CODE])
        # → {..., "one_code_count": 12, "unique_one_codes": 9,
        #          "one_codes_sample": ["ONE0007", ...]}
    """

    key_prefix: str
    pattern: re.Pattern[str]
    sample_size: int = 20


def compute_content_stats(
    text: str,
    *,
    rendered_as: str | None = None,
    schema_hints: list[SchemaHint] | None = None,
) -> dict[str, Any]:
    """Return deterministic aggregates the LLM can quote without counting.

    Args:
        text: The content (file body, sheet dump, transcript, …).
        rendered_as: Optional hint about the content shape. When
            ``"csv"`` the first non-empty line is treated as a header
            and CSV-specific keys (``csv_header``, ``csv_column_count``,
            ``csv_data_rows``) are added.
        schema_hints: Optional per-consumer domain code-pattern
            counters. The seed ships **none** — the real-estate ONE-code
            counter is a social-wiring product concern, supplied here.

    Returns:
        A flat dict of aggregates. Always includes ``total_chars`` +
        ``total_lines``; adds ``non_empty_lines`` + CSV/hint keys when
        applicable. Empty text returns the zero baseline.
    """
    if not text:
        return {"total_chars": 0, "total_lines": 0}

    lines = text.splitlines()
    total_lines = len(lines)
    non_empty = sum(1 for ln in lines if ln.strip())

    base: dict[str, Any] = {
        "total_chars": len(text),
        "total_lines": total_lines,
        "non_empty_lines": non_empty,
    }

    for hint in schema_hints or []:
        matches = hint.pattern.findall(text)
        if matches:
            unique = sorted(set(matches))
            base[f"{hint.key_prefix}_count"] = len(matches)
            base[f"unique_{hint.key_prefix}s"] = len(unique)
            base[f"{hint.key_prefix}s_sample"] = unique[: hint.sample_size]

    if rendered_as == "csv":
        header_line = lines[0] if lines else ""
        base["csv_header"] = header_line
        base["csv_column_count"] = (
            max(1, header_line.count(",") + 1) if header_line else 0
        )
        base["csv_data_rows"] = (
            max(0, non_empty - 1) if header_line else non_empty
        )

    return base


__all__ = ["SchemaHint", "compute_content_stats"]
