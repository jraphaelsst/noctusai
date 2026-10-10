"""Validation regexes must reject a trailing newline (``$`` accepts it)."""
import pytest

from noctusai_lib.integrations.meta.mappers import (
    business_discovery_fields_param,
    normalize_ig_handle,
)


def test_inner_newline_in_handle_rejected_surrounding_whitespace_stripped():
    with pytest.raises(ValueError):
        normalize_ig_handle("ab\ncd")
    assert normalize_ig_handle("abc\n") == "abc"


def test_field_with_trailing_newline_rejected():
    with pytest.raises(ValueError):
        business_discovery_fields_param("abc", ["id\n"])


def test_cursor_with_trailing_newline_rejected():
    with pytest.raises(ValueError):
        business_discovery_fields_param("abc", ["id"], after="QVFI\n")
    assert "QVFI" in business_discovery_fields_param("abc", ["id"], after="QVFI")
