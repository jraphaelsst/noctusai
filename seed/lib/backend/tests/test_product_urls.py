"""Tests for `noctusai_lib.config.product_urls` — environment-aware product
URL resolution. The resolver replaces hardcoded ``http://localhost:<port>``
URLs with per-product / pattern-driven URLs that adapt to the deploy host
without DB edits.
"""
from __future__ import annotations

import pytest

from noctusai_lib.config.product_urls import resolve_product_url


class TestResolveProductUrl:
    """Resolution order: per-product env > pattern env > db_url_base.
    Empty/missing → raise ValueError (no silent fallback)."""

    def test_per_product_env_wins_over_pattern_and_db(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SAMPLE_PRODUCT", "https://ms.example.com")
        monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.fallback.com")
        result = resolve_product_url(
            "sample-product",
            db_url_base="http://localhost:8140",
        )
        assert result == "https://ms.example.com"

    def test_pattern_used_when_no_per_product_env(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SAMPLE_PRODUCT", raising=False)
        monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctus.ai")
        result = resolve_product_url(
            "sample-product",
            db_url_base="http://localhost:8140",
        )
        assert result == "https://sample-product.noctus.ai"

    def test_pattern_substitutes_underscored_slug(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SAMPLE_PRODUCT", raising=False)
        monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://app.example.com/{slug_underscored}")
        result = resolve_product_url("sample-product")
        assert result == "https://app.example.com/sample_product"

    def test_pattern_handles_both_placeholders_in_one_string(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SAMPLE_PRODUCT", raising=False)
        monkeypatch.setenv(
            "PRODUCT_URL_PATTERN",
            "https://{slug}.example.com/api/{slug_underscored}",
        )
        result = resolve_product_url("sample-product")
        assert result == "https://sample-product.example.com/api/sample_product"

    def test_db_fallback_when_no_env(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SAMPLE_PRODUCT", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        result = resolve_product_url(
            "sample-product",
            db_url_base="http://localhost:8140",
        )
        assert result == "http://localhost:8140"

    def test_raises_when_all_sources_missing(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_SAMPLE_PRODUCT", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        with pytest.raises(ValueError) as exc:
            resolve_product_url("sample-product", db_url_base=None)
        # Error message must surface the env var name to fix it AND the
        # alternatives — silent fallback is forbidden, so the caller has
        # everything they need to fix the gap.
        assert "PRODUCT_URL_SAMPLE_PRODUCT" in str(exc.value)
        assert "PRODUCT_URL_PATTERN" in str(exc.value)
        assert "url_base" in str(exc.value)

    def test_raises_when_db_url_base_is_empty_string(self, monkeypatch):
        # Empty string is treated identically to None — both indicate "no
        # value", neither should be silently used as a URL.
        monkeypatch.delenv("PRODUCT_URL_SAMPLE_PRODUCT", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        with pytest.raises(ValueError):
            resolve_product_url("sample-product", db_url_base="")

    def test_raises_on_empty_slug(self):
        with pytest.raises(ValueError) as exc:
            resolve_product_url("")
        assert "non-empty" in str(exc.value)

    def test_strips_trailing_slash_from_per_product_env(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_X", "https://x.example.com/")
        assert resolve_product_url("x") == "https://x.example.com"

    def test_strips_trailing_slash_from_pattern_result(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_X", raising=False)
        monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.example.com/")
        assert resolve_product_url("x") == "https://x.example.com"

    def test_strips_trailing_slash_from_db_fallback(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_X", raising=False)
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        assert (
            resolve_product_url("x", db_url_base="http://localhost:8000/")
            == "http://localhost:8000"
        )

    def test_slug_with_multiple_hyphens_canonicalized(self, monkeypatch):
        # Hyphens → underscores in env var name; canonicalization is
        # idempotent for slugs that already contain only one segment.
        monkeypatch.setenv("PRODUCT_URL_FOO_BAR_BAZ", "https://foo-bar-baz.example.com")
        result = resolve_product_url("foo-bar-baz")
        assert result == "https://foo-bar-baz.example.com"
