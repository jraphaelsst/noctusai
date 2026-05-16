"""compute_content_stats — universal aggregates + per-product SchemaHint.

Validates the LLM-counting-trap fix: deterministic line/char/CSV
aggregates the model quotes verbatim, plus the generalized SchemaHint
seam that keeps domain-specific code-pattern regexes (the real-estate
ONE-code) OUT of the seed.
"""

import re

from noctusai_lib.domain.chatbot.content_stats import (
    SchemaHint,
    compute_content_stats,
)


def test_empty_text_returns_zero_baseline() -> None:
    assert compute_content_stats("") == {"total_chars": 0, "total_lines": 0}


def test_basic_line_and_char_counts() -> None:
    stats = compute_content_stats("a\n\nbb\nccc")
    assert stats["total_chars"] == len("a\n\nbb\nccc")
    assert stats["total_lines"] == 4
    assert stats["non_empty_lines"] == 3


def test_csv_shape_keys() -> None:
    stats = compute_content_stats(
        "name,code,price\nfoo,1,10\nbar,2,20", rendered_as="csv"
    )
    assert stats["csv_header"] == "name,code,price"
    assert stats["csv_column_count"] == 3
    assert stats["csv_data_rows"] == 2
    assert stats["total_lines"] == 3


def test_schema_hint_emits_prefixed_keys() -> None:
    one_code = SchemaHint(
        key_prefix="one_code", pattern=re.compile(r"\bONE\d{3,6}\b")
    )
    stats = compute_content_stats(
        "deal ONE0007 and ONE0007 plus ONE1234",
        schema_hints=[one_code],
    )
    assert stats["one_code_count"] == 3
    assert stats["unique_one_codes"] == 2
    assert stats["one_codes_sample"] == ["ONE0007", "ONE1234"]


def test_schema_hint_absent_when_no_match() -> None:
    one_code = SchemaHint(
        key_prefix="one_code", pattern=re.compile(r"\bONE\d{3,6}\b")
    )
    stats = compute_content_stats("no codes here", schema_hints=[one_code])
    assert "one_code_count" not in stats
    assert stats["total_chars"] == len("no codes here")


def test_seed_ships_no_default_hints() -> None:
    # The real-estate ONE-code regex must NOT be a seed default — it is
    # a social-wiring product concern supplied as a SchemaHint.
    stats = compute_content_stats("deal ONE0007")
    assert "one_code_count" not in stats
