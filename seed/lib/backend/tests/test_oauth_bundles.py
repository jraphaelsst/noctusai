"""Tests for `noctusai_lib.integrations.oauth_bundles` — named scope
bundles as single-sourced subsets of the provider kitchen-sink lists.

Pure-data module — no IO, no Fake (exemption test: a Fake would
exercise no different code than the constants). Network-free.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.google_scopes import GOOGLE_KITCHEN_SINK_SCOPES
from noctusai_lib.integrations.meta._meta_api import META_KITCHEN_SINK_SCOPES
from noctusai_lib.integrations.oauth_bundles import (
    GOOGLE_BUNDLE_COMMUNICATIONS,
    GOOGLE_BUNDLE_PRODUCTIVITY,
    META_BUNDLE_FULL_SOCIAL,
    META_BUNDLE_READ_ONLY,
    bundle_names,
    resolve_bundle,
)


class TestSubsetInvariant:
    """The load-bearing contract: every bundle ⊂ its kitchen-sink."""

    def test_google_productivity_subset_of_kitchen_sink(self) -> None:
        assert set(GOOGLE_BUNDLE_PRODUCTIVITY) <= set(
            GOOGLE_KITCHEN_SINK_SCOPES
        )

    def test_google_communications_subset_of_kitchen_sink(self) -> None:
        assert set(GOOGLE_BUNDLE_COMMUNICATIONS) <= set(
            GOOGLE_KITCHEN_SINK_SCOPES
        )

    def test_meta_read_only_subset_of_kitchen_sink(self) -> None:
        assert set(META_BUNDLE_READ_ONLY) <= set(META_KITCHEN_SINK_SCOPES)

    def test_meta_full_social_equals_kitchen_sink(self) -> None:
        assert set(META_BUNDLE_FULL_SOCIAL) == set(META_KITCHEN_SINK_SCOPES)

    def test_bundles_nonempty(self) -> None:
        for b in (
            GOOGLE_BUNDLE_PRODUCTIVITY,
            GOOGLE_BUNDLE_COMMUNICATIONS,
            META_BUNDLE_READ_ONLY,
            META_BUNDLE_FULL_SOCIAL,
        ):
            assert b, "bundle must not be empty"


class TestResolveBundle:
    def test_resolve_known_names(self) -> None:
        assert resolve_bundle("google_productivity") == (
            GOOGLE_BUNDLE_PRODUCTIVITY
        )
        assert resolve_bundle("META_READ_ONLY") == META_BUNDLE_READ_ONLY

    def test_resolve_returns_fresh_copy(self) -> None:
        got = resolve_bundle("meta_full_social")
        got.append("MUTATION")
        assert "MUTATION" not in META_BUNDLE_FULL_SOCIAL

    def test_unknown_name_raises_with_valid_list(self) -> None:
        with pytest.raises(ValueError, match="unknown OAuth scope bundle"):
            resolve_bundle("google_gmail")

    def test_bundle_names_sorted(self) -> None:
        names = bundle_names()
        assert names == sorted(names)
        assert "google_productivity" in names
        assert "meta_full_social" in names
