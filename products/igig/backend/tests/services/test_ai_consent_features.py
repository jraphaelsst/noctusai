"""LGPD consent-catalog unit tests for `app/services/ai_consent_features.py`.

Pins:
  - `igig.assistente_negocio` is registered opt-in (`default_granted=False`,
    `toggleable=True`) and its redactors drop the personal-data-bearing
    fields (`contexto`, the generated `texto`) while keeping structural
    routing metadata (`acao`, `canal`, `negocio_id`, `org_id`).
  - `igig.assistente_ajuda` is registered locked-on (`toggleable=False`) —
    transparency only, never gated (see `app/routers/ajuda_router.py`).
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.ai import get_feature


@pytest.fixture(autouse=True)
def _register_igig_features():
    import app.services.ai_consent_features  # noqa: F401
    yield


class TestAssistenteNegocioCatalog:
    def test_is_registered_opt_in(self):
        feature = get_feature("igig.assistente_negocio")
        assert feature is not None
        assert feature.default_granted is False
        assert feature.toggleable is True
        assert feature.product == "igig"
        assert feature.title
        assert feature.rationale

    def test_redact_arguments_keeps_only_structural_fields(self):
        feature = get_feature("igig.assistente_negocio")
        assert feature.redact_arguments is not None

        args = {
            "acao": "resumo",
            "canal": "whatsapp",
            "negocio_id": "neg-1",
            "org_id": "org-1",
            "contexto": {
                "lead": {"nome": "João", "email": "joao@sol.com", "empresa": "Padaria Sol"},
                "timeline": ["Nota: cliente pediu desconto"],
            },
        }
        scrubbed = feature.redact_arguments(args)

        assert scrubbed == {
            "acao": "resumo",
            "canal": "whatsapp",
            "negocio_id": "neg-1",
            "org_id": "org-1",
        }
        assert "contexto" not in scrubbed

    def test_redact_arguments_handles_non_dict_input(self):
        feature = get_feature("igig.assistente_negocio")
        assert feature.redact_arguments(None) == {}
        assert feature.redact_arguments("not-a-dict") == {}

    def test_redact_result_drops_generated_text_string(self):
        feature = get_feature("igig.assistente_negocio")
        assert feature.redact_result is not None
        assert feature.redact_result("Resumo: lead quente, pediu desconto de 10%.") == "[REDACTED]"

    def test_redact_result_drops_generated_text_dict(self):
        feature = get_feature("igig.assistente_negocio")
        scrubbed = feature.redact_result({"texto": "Rascunho pessoal com dados do lead"})
        assert scrubbed == {"texto": "[REDACTED]"}

    def test_redact_result_handles_none(self):
        feature = get_feature("igig.assistente_negocio")
        assert feature.redact_result(None) is None


class TestAssistenteAjudaCatalog:
    def test_is_registered_locked_on(self):
        feature = get_feature("igig.assistente_ajuda")
        assert feature is not None
        assert feature.toggleable is False
        assert feature.product == "igig"
        assert feature.title
        assert feature.rationale
