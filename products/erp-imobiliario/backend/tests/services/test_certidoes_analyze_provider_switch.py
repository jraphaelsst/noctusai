"""The manual chat-provider switch on `_analyze_with_ai`.

LLM-provider-dependency-sweep (2026-09-18): `resolve_llm_provider` must
actually decide which vendor + model + credential this call uses, not just
exist unused. A separate file from `test_certidoes_service.py` because that
suite already patches several of this module's OWN functions as test seams
for `_process_single_certidao` — appending here would trip the
self-monkeypatch guard on an unrelated, pre-existing pattern.

🔴 Manual switch, not a fallback — see `resolve_llm_provider`'s module
docstring. `provider_resolver` is a real DI seam (a bound default
`_analyze_with_ai` accepts), never a patch of the module's own attribute —
`chat_completion` / `resolve_credential` ARE legitimate patch targets here
because both are external-boundary integrations (the seed LLM wrapper and
the platform credential chain), the same class of seam
`test_certidoes_service.py::TestAnalyzeWithAi` already uses.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.certidoes_service import _analyze_with_ai


class TestAnalyzeWithAiProviderSwitch:
    @pytest.mark.asyncio
    async def test_unset_org_setting_resolves_to_openai_key_and_model(self):
        """Behaviour-preserving: no test seam override means the real
        `resolve_llm_provider` runs, reads an unset `org_settings` row, and
        returns "openai" — the pre-existing key name and model this call
        site used before the switch existed."""
        captured: dict = {}

        async def _capturing_chat(**kwargs):
            captured.update(kwargs)
            return "Situação regular, sem débitos."

        with patch(
            "app.services.certidoes_service.resolve_credential",
            side_effect=lambda key, org_id=None: "sk-test" if key == "openai_api_key" else None,
        ), patch(
            "app.services.certidoes_service.chat_completion",
            side_effect=_capturing_chat,
        ):
            result = await _analyze_with_ai("texto da certidão")

        assert result == "Situação regular, sem débitos."
        assert captured["provider"] == "openai"
        assert captured["model"] == "gpt-4.1-mini"

    @pytest.mark.asyncio
    async def test_a_chosen_vendor_selects_its_own_key_and_model(self):
        """The lever the operator actually pulls: an `org_settings` row for
        `llm_chat_provider` routes both the credential lookup AND the model
        pin to the chosen vendor — a mismatched model+vendor pair 404s at
        the provider, which is exactly the failure `ANALYSIS_MODELS` (a map,
        not a string) exists to prevent."""
        captured: dict = {}

        async def _capturing_chat(**kwargs):
            captured.update(kwargs)
            return "Análise via Claude."

        with patch(
            "app.services.certidoes_service.resolve_credential",
            side_effect=lambda key, org_id=None: "sk-ant-test" if key == "anthropic_api_key" else None,
        ), patch(
            "app.services.certidoes_service.chat_completion",
            side_effect=_capturing_chat,
        ):
            result = await _analyze_with_ai(
                "texto da certidão",
                provider_resolver=lambda capability, org_id, **kw: "anthropic",
            )

        assert result == "Análise via Claude."
        assert captured["provider"] == "anthropic"
        assert captured["model"] == "claude-opus-5"

    @pytest.mark.asyncio
    async def test_the_chosen_vendors_own_key_is_what_gets_checked(self):
        """A missing key must report against the SELECTED vendor, not a
        hardcoded "OpenAI" — otherwise an operator who configured Anthropic
        and switched to it sees an OpenAI-shaped message pointing at the
        wrong settings field."""
        with patch("app.services.certidoes_service.resolve_credential", return_value=None):
            result = await _analyze_with_ai(
                "texto da certidão",
                provider_resolver=lambda capability, org_id, **kw: "anthropic",
            )
        assert "anthropic" in result
        assert "não disponível" in result

    @pytest.mark.asyncio
    async def test_an_injected_resolver_is_the_only_thing_that_moves_the_vendor(self):
        """No auto-failover: a `chat_completion` exception does not make a
        second attempt at a different provider — the existing
        `[Erro na análise IA: ...]` fallback still fires once, unchanged."""
        with patch(
            "app.services.certidoes_service.resolve_credential", return_value="sk-test"
        ), patch(
            "app.services.certidoes_service.chat_completion",
            side_effect=Exception("API down"),
        ):
            result = await _analyze_with_ai(
                "texto da certidão",
                provider_resolver=lambda capability, org_id, **kw: "gemini",
            )
        assert "Erro na análise IA" in result
