"""Tests for `noctusai_lib.domain.chatbot.prompt_fragments` — the shared
URL-immutability system-prompt fragment + idempotent compose helper.
"""

from __future__ import annotations

from noctusai_lib.domain.chatbot import (
    URL_IMMUTABILITY_FRAGMENT,
    with_url_immutability,
)
from noctusai_lib.domain.chatbot.prompt_fragments import (
    URL_IMMUTABILITY_FRAGMENT as DIRECT_FRAGMENT,
)


class TestFragmentConstant:
    def test_exported_from_package(self) -> None:
        # Re-exported via the package __init__ AND importable directly.
        assert URL_IMMUTABILITY_FRAGMENT is DIRECT_FRAGMENT

    def test_non_empty_and_generic(self) -> None:
        assert URL_IMMUTABILITY_FRAGMENT
        assert len(URL_IMMUTABILITY_FRAGMENT) > 50
        low = URL_IMMUTABILITY_FRAGMENT.lower()
        # generic (not Google-specific): mentions the general hazard.
        assert "character-for-character" in low
        assert "/u/0/" in URL_IMMUTABILITY_FRAGMENT
        assert "immutable" in low


class TestWithUrlImmutability:
    def test_appends_to_existing_prompt(self) -> None:
        out = with_url_immutability("You are a helpful bot.")
        assert out.startswith("You are a helpful bot.")
        assert URL_IMMUTABILITY_FRAGMENT in out

    def test_blank_prompt_yields_fragment_alone(self) -> None:
        assert with_url_immutability("") == URL_IMMUTABILITY_FRAGMENT
        assert with_url_immutability("   ") == URL_IMMUTABILITY_FRAGMENT

    def test_idempotent_no_double_append(self) -> None:
        once = with_url_immutability("Base prompt.")
        twice = with_url_immutability(once)
        assert once == twice
        assert twice.count(URL_IMMUTABILITY_FRAGMENT) == 1
