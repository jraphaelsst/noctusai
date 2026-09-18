"""The lightweight manual provider switch — `resolve_llm_provider`.

Sibling of `products/social-wiring/backend/tests/services/
test_vision_provider_switch.py`: same behaviour, generalised. `resolver`
is passed as a DI seam (never monkeypatched) — see
`KB § PATTERNS/backend/di-test-seam.md`.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm.provider_choice import resolve_llm_provider

ORG = "11111111-1111-1111-1111-111111111111"
_CHAT_VENDORS = ("openai", "anthropic", "gemini")
_EMBEDDING_VENDORS = ("openai", "gemini")


def _resolved_as(valor, *, allowed=_CHAT_VENDORS, default="openai"):
    return lambda org_id=ORG, capability="chat": resolve_llm_provider(
        capability,
        org_id,
        allowed=allowed,
        default=default,
        resolver=lambda key, org=None: valor,
    )


class TestUnsetAndValidChoices:
    def test_unset_falls_back_to_the_default(self) -> None:
        assert _resolved_as(None)() == "openai"

    def test_a_saved_choice_is_honoured(self) -> None:
        assert _resolved_as("anthropic")() == "anthropic"

    def test_whitespace_around_a_saved_value_does_not_break_it(self) -> None:
        assert _resolved_as("  anthropic\n")() == "anthropic"

    def test_an_org_less_call_still_answers(self) -> None:
        assert _resolved_as(None)(None) == "openai"


class TestUnknownValueDegradesLoudly:
    def test_an_unknown_value_falls_back_to_the_default(self, caplog) -> None:
        with caplog.at_level("WARNING"):
            assert _resolved_as("cohere")() == "openai"
        assert "cohere" in caplog.text

    def test_the_warning_names_the_capability_and_setting_key(self, caplog) -> None:
        with caplog.at_level("WARNING"):
            resolve_llm_provider(
                "vision", ORG, allowed=_CHAT_VENDORS,
                resolver=lambda key, org=None: "cohere",
            )
        assert "llm_vision_provider" in caplog.text
        assert "vision" in caplog.text


class TestEmbeddingNeverOffersAnthropic:
    def test_anthropic_chosen_for_embedding_degrades_to_default(self, caplog) -> None:
        """A stored value outside `allowed` degrades exactly like any other
        unroutable vendor — this is the concrete case the module docstring
        warns about: an org's `llm_embedding_provider` row cannot hold
        "anthropic" as a WRITE, but a hand-edited/retired row could, and
        must not reach `generate_embedding(provider="anthropic")`."""
        with caplog.at_level("WARNING"):
            got = resolve_llm_provider(
                "embedding", ORG, allowed=_EMBEDDING_VENDORS,
                resolver=lambda key, org=None: "anthropic",
            )
        assert got == "openai"
        assert "anthropic" in caplog.text

    def test_gemini_is_a_valid_embedding_choice(self) -> None:
        got = resolve_llm_provider(
            "embedding", ORG, allowed=_EMBEDDING_VENDORS,
            resolver=lambda key, org=None: "gemini",
        )
        assert got == "gemini"


class TestKeyShape:
    def test_reads_the_llm_prefixed_capability_suffixed_key(self) -> None:
        seen = {}

        def _resolver(key, org=None):
            seen["key"] = key
            seen["org"] = org
            return None

        resolve_llm_provider("chat", ORG, allowed=_CHAT_VENDORS, resolver=_resolver)
        assert seen["key"] == "llm_chat_provider"
        assert seen["org"] == ORG


class TestDefaultMustBeAllowed:
    def test_a_default_outside_allowed_is_a_call_site_bug(self) -> None:
        with pytest.raises(AssertionError):
            resolve_llm_provider(
                "embedding", ORG, allowed=_EMBEDDING_VENDORS, default="anthropic",
                resolver=lambda key, org=None: None,
            )
