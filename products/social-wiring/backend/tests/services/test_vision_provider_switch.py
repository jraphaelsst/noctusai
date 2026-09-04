"""The manual OpenAI ↔ Anthropic switch for document transcription.

🔴 MANUAL, NOT A FALLBACK — that is the design, not an omission.
Nothing in this product moves an org from one vendor to the other on its
own. A silent switch would change which model transcribed a legal document
with no record that it happened, and "why does this matrícula read
differently from last month's" is not a question the logs could answer
afterwards. The operator picks in Settings → Chaves de API; the pick is
visible on the screen and in every failure message.

What is pinned here is the SEAM between the stored choice and the seed
transcriber: `resolve_vision_provider` must always hand
`make_document_transcriber(provider=...)` a value that vendor dispatch can
actually route, because a bad one surfaces much later as "no credential
resolved" — which reads like a missing key rather than a bad setting.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.transcription import OCR_MODELS

from app.services.api_keys_store import (
    API_KEY_SPECS,
    MANAGED_API_KEYS,
    VISION_PROVIDER_KEY,
    get_spec,
    resolve_vision_provider,
)

ORG = "11111111-1111-1111-1111-111111111111"


def _resolvido_como(valor):
    """`resolve_vision_provider` with both tiers stubbed through its OWN DI
    seams: an explicit `store=None` skips the encrypted tier (no Fernet, no
    Supabase), and `resolver` stands in for the platform chain.

    Passed, not monkeypatched. `resolver` is a bound default inside
    `resolve_api_key_detail`, so patching this module's `resolve_credential`
    attribute leaves the real chain in place — the first version of this
    test did exactly that and reported `openai` for every input.
    """
    return lambda org_id: resolve_vision_provider(
        org_id, store=None, resolver=lambda name, org=None: valor
    )


class TestTheSwitchIsWiredEndToEnd:
    def test_both_vendors_are_managed_keys(self) -> None:
        """The switch is useless if the key it selects cannot be saved.

        `main.py` registers the product's encrypted store as tier 0 of
        `resolve_credential` and gates that on `get_spec(key) is not None`,
        so a vendor absent from the specs is a vendor whose UI-entered key
        is invisible to the transcriber.
        """
        assert "openai_api_key" in MANAGED_API_KEYS
        assert "anthropic_api_key" in MANAGED_API_KEYS

    def test_every_option_names_a_provider_the_seed_can_route(self) -> None:
        """🔴 The UI's options and the seed's model map must not drift.

        An option the seed has no model for would fall back to OpenAI's
        model name under a non-OpenAI provider — a 404 that reads like a
        broken key.
        """
        spec = get_spec(VISION_PROVIDER_KEY)
        assert spec is not None
        assert spec.allowed_values, "a choice with no options is not a choice"
        for provider in spec.allowed_values:
            assert provider in OCR_MODELS, provider
            assert get_spec(f"{provider}_api_key") is not None, provider

    def test_the_default_is_openai_so_nothing_moves_on_upgrade(self) -> None:
        spec = get_spec(VISION_PROVIDER_KEY)
        assert spec.default == "openai"
        assert spec.default in spec.allowed_values

    def test_the_choice_is_not_stored_as_a_secret(self) -> None:
        """A masked provider name would show as `...ropic` on the screen
        that exists to tell the operator which vendor is live."""
        spec = get_spec(VISION_PROVIDER_KEY)
        assert spec.is_secret is False

    def test_only_this_one_spec_is_a_choice(self) -> None:
        """Guards the frontend's branch: it renders a switch iff `options`
        is non-empty, so an API key that grew options would silently lose
        its write-only input."""
        com_opcoes = [s.name for s in API_KEY_SPECS if s.options]
        assert com_opcoes == [VISION_PROVIDER_KEY]


class TestResolveVisionProvider:
    def test_unset_falls_back_to_the_documented_default(self) -> None:
        assert _resolvido_como(None)(ORG) == "openai"

    def test_a_saved_choice_is_honoured(self) -> None:
        assert _resolvido_como("anthropic")(ORG) == "anthropic"

    def test_whitespace_around_a_saved_value_does_not_break_it(self) -> None:
        assert _resolvido_como("  anthropic\n")(ORG) == "anthropic"

    def test_an_unknown_value_degrades_to_the_default_loudly(self, caplog) -> None:
        """🔴 Degrade, but never silently.

        The write path validates, so this can only happen if a row was
        written around it or an option was retired while an org still
        pointed at it. Running on the documented default is the honest
        move; handing an unroutable name to the LLM stack would fail one
        layer down with a message about a missing key.
        """
        with caplog.at_level("WARNING"):
            assert _resolvido_como("cohere")(ORG) == "openai"
        assert "cohere" in caplog.text

    def test_an_org_less_call_still_answers(self) -> None:
        """The transcriber factory is also reachable from paths with no org
        (a sweep, a CLI); it must get a routable provider, not a crash."""
        assert _resolvido_como(None)(None) == "openai"
