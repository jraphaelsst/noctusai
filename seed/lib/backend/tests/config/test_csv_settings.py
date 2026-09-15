"""Unit tests for `noctusai_lib.config.csv_settings`.

Exercises the shared comma-separated-list-setting idiom:

- :func:`parse_csv_setting` — empty input, whitespace, trailing/doubled
  comma, ``lower=True``.
- :func:`reject_json_array` — a plain CSV value passes through unchanged;
  a JSON-array-shaped value raises `ValueError` naming the env var.
"""

from __future__ import annotations

import pytest

from noctusai_lib.config.csv_settings import parse_csv_setting, reject_json_array


class TestParseCsvSetting:
    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_csv_setting("") == []

    def test_plain_comma_separated(self) -> None:
        assert parse_csv_setting("k1,k2") == ["k1", "k2"]

    def test_strips_whitespace_around_items(self) -> None:
        assert parse_csv_setting(" k1 , k2 ") == ["k1", "k2"]

    def test_trailing_comma_drops_empty_item(self) -> None:
        assert parse_csv_setting("k1,k2,") == ["k1", "k2"]

    def test_doubled_comma_drops_empty_item(self) -> None:
        assert parse_csv_setting("k1,,k2") == ["k1", "k2"]

    def test_whitespace_only_item_is_dropped(self) -> None:
        assert parse_csv_setting("k1,   ,k2") == ["k1", "k2"]

    def test_single_item_no_comma(self) -> None:
        assert parse_csv_setting("k1") == ["k1"]

    def test_lower_true_lowercases_every_item(self) -> None:
        assert parse_csv_setting("Example.COM, Other.Org", lower=True) == [
            "example.com",
            "other.org",
        ]

    def test_lower_false_default_preserves_case(self) -> None:
        assert parse_csv_setting("Example.COM") == ["Example.COM"]


class TestRejectJsonArray:
    def test_plain_csv_value_passes_through_unchanged(self) -> None:
        assert reject_json_array("k1,k2", "APPROVAL_ASSERTION_SECRETS") == "k1,k2"

    def test_empty_string_passes_through_unchanged(self) -> None:
        assert reject_json_array("", "APPROVAL_ASSERTION_SECRETS") == ""

    def test_json_array_shaped_value_raises(self) -> None:
        with pytest.raises(ValueError, match="APPROVAL_ASSERTION_SECRETS"):
            reject_json_array('["k1","k2"]', "APPROVAL_ASSERTION_SECRETS")

    def test_error_message_names_env_var_and_echoes_value(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            reject_json_array('["k1"]', "PRIMARY_SOURCE_ALLOWLIST")
        message = str(exc_info.value)
        assert "PRIMARY_SOURCE_ALLOWLIST" in message
        assert "comma-separated" in message
        assert "JSON" in message

    def test_leading_whitespace_before_bracket_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="APPROVAL_ASSERTION_SECRETS"):
            reject_json_array('  ["k1","k2"]', "APPROVAL_ASSERTION_SECRETS")
