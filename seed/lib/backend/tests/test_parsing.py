"""Tests for `noctusai_lib.parsing` — absorbed parsing/formatting helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from noctusai_lib.primitives.parsing import (
    safe_float,
    safe_json_loads,
    format_brl,
    parse_iso_or_400,
    parse_iso_or_none,
)


# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_clean_numeric_string(self):
        assert safe_float("42") == 42.0
        assert safe_float("3.14") == 3.14
        assert safe_float("-0.5") == -0.5

    def test_messy_currency_strings(self):
        # Strips R$ + spaces; keeps digits + dot + minus.
        assert safe_float("R$ 1234.56") == 1234.56
        # The "anos" suffix is stripped.
        assert safe_float("42 anos") == 42.0

    def test_already_numeric(self):
        assert safe_float(7) == 7.0
        assert safe_float(2.5) == 2.5

    def test_none_returns_default(self):
        assert safe_float(None) == 0.0
        assert safe_float(None, default=99.0) == 99.0

    def test_empty_returns_default(self):
        assert safe_float("") == 0.0
        assert safe_float("abc") == 0.0  # no digits left after cleaning
        assert safe_float("abc", default=12.0) == 12.0

    def test_unparseable_returns_default(self):
        # Multiple dots can't parse — falls back.
        assert safe_float("1.2.3", default=99.0) == 99.0


# ---------------------------------------------------------------------------
# safe_json_loads
# ---------------------------------------------------------------------------

class TestSafeJsonLoads:
    def test_plain_json_dict(self):
        assert safe_json_loads('{"a": 1}') == {"a": 1}

    def test_plain_json_list(self):
        assert safe_json_loads('[1, 2, 3]') == [1, 2, 3]

    def test_strips_markdown_fence(self):
        raw = "```json\n{\"a\": 1}\n```"
        assert safe_json_loads(raw) == {"a": 1}

    def test_strips_bare_fence(self):
        raw = "```\n[1, 2]\n```"
        assert safe_json_loads(raw) == [1, 2]

    def test_invalid_json_returns_none(self):
        assert safe_json_loads("not json") is None
        assert safe_json_loads("{ a: 1 }") is None  # unquoted key

    def test_empty_returns_none(self):
        assert safe_json_loads("") is None
        assert safe_json_loads(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# format_brl
# ---------------------------------------------------------------------------

class TestFormatBrl:
    def test_default_two_decimals_with_currency(self):
        assert format_brl(1234.56) == "R$ 1.234,56"
        assert format_brl(0) == "R$ 0,00"

    def test_zero_decimals(self):
        # ERP digest flavor: rounded BRL with no decimals.
        # Python's `format(...,'.0f')` uses banker's rounding (half-to-even):
        # 1234.5 rounds to 1234, not 1235. Matches the original `_fmt_brl`.
        assert format_brl(1234.5, decimals=0) == "R$ 1.234"
        assert format_brl(1234.7, decimals=0) == "R$ 1.235"  # > .5 rounds up
        assert format_brl(1000) == "R$ 1.000,00"  # default decimals=2
        assert format_brl(1000, decimals=0) == "R$ 1.000"

    def test_raw_no_currency(self):
        # DIMOB flavor: locale-free fixed format for export files.
        assert format_brl(1234.56, with_currency=False) == "1234.56"
        assert format_brl(0, with_currency=False) == "0.00"

    def test_negative_values(self):
        assert format_brl(-1234.56) == "R$ -1.234,56"

    def test_none_returns_zero(self):
        assert format_brl(None) == "R$ 0"
        assert format_brl(None, with_currency=False) == "0.00"

    def test_non_numeric_returns_zero(self):
        # String input that can't coerce → zero with warning logged.
        assert format_brl("not a number") == "R$ 0"  # type: ignore[arg-type]

    def test_int_input(self):
        assert format_brl(42) == "R$ 42,00"


# ---------------------------------------------------------------------------
# parse_iso_or_400
# ---------------------------------------------------------------------------

class TestParseIsoOr400:
    def test_valid_iso(self):
        result = parse_iso_or_400("2026-04-29T15:30:00")
        assert result is not None
        assert result.year == 2026 and result.month == 4 and result.day == 29

    def test_z_suffix_normalized(self):
        result = parse_iso_or_400("2026-04-29T15:30:00Z")
        assert result is not None
        # Z → +00:00 → tzinfo set
        assert result.utcoffset() is not None

    def test_none_returns_none(self):
        assert parse_iso_or_400(None) is None

    def test_empty_returns_none(self):
        assert parse_iso_or_400("") is None

    def test_invalid_raises_http_400(self):
        with pytest.raises(HTTPException) as exc:
            parse_iso_or_400("not-a-date")
        assert exc.value.status_code == 400
        assert "not-a-date" in exc.value.detail


# ---------------------------------------------------------------------------
# parse_iso_or_none
# ---------------------------------------------------------------------------

class TestParseIsoOrNone:
    def test_valid_iso(self):
        result = parse_iso_or_none("2026-04-29T15:30:00")
        assert result is not None

    def test_invalid_returns_none(self):
        # Background-job flavor: never raises.
        assert parse_iso_or_none("not-a-date") is None

    def test_none_returns_none(self):
        assert parse_iso_or_none(None) is None
