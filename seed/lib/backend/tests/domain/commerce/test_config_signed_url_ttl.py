"""CommerceConfig enforces the storage seam's signed-URL TTL rule at construction (security standard S1)."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce.config import CommerceConfig


def test_default_media_ttl_carries_its_reason() -> None:
    cfg = CommerceConfig(schema="shop")
    assert cfg.signed_url_ttl_seconds == 3600
    assert cfg.signed_url_ttl_reason and cfg.signed_url_ttl_reason.strip()


def test_ttl_over_600_without_reason_is_refused_at_construction() -> None:
    with pytest.raises(ValueError):
        CommerceConfig(schema="shop", signed_url_ttl_seconds=900, signed_url_ttl_reason=None)


def test_ttl_over_the_ceiling_is_refused_even_with_a_reason() -> None:
    with pytest.raises(ValueError):
        CommerceConfig(schema="shop", signed_url_ttl_seconds=3601)


def test_short_ttl_needs_no_reason() -> None:
    assert CommerceConfig(schema="shop", signed_url_ttl_seconds=600, signed_url_ttl_reason=None).signed_url_ttl_seconds == 600
