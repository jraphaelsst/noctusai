"""LGPD redaction tests for PF `register_feature` callables.

PF is finance-sensitive — transaction descriptions, account balances, and
income figures (raw values + aggregated receita/despesa/fluxo) MUST NOT land
in `tool_call_audits.arguments` / `.result`. These tests pin the redactor
contract per llm-tool-audit-rollout PROJECT.md §3 design principle #3
(LGPD-first) + §11 Phase 0 finding #2 (zero redaction wiring was the
highest-impact gap).

Each registered feature has matching `redact_arguments` + `redact_result`
callables; this file verifies the scrubbing behavior end-to-end (raw
prompt-shaped dict → JSON-friendly redacted dict, free of PII).
"""

from __future__ import annotations

import pytest

# Import the feature module so its `register_feature(...)` calls populate
# the seed catalog with redactor wiring.
import app.services.ai_consent_features  # noqa: F401
from noctusai_lib.domain.ai import get_feature


# ---------------------------------------------------------------------------
# pf.transaction_categorize
# ---------------------------------------------------------------------------


def test_categorize_redact_arguments_strips_descricao_and_valor():
    feature = get_feature("pf.transaction_categorize")
    assert feature is not None
    assert feature.redact_arguments is not None

    raw = {
        "tipo": "despesa",
        "descricao": "Pagamento de aluguel mensal apartamento 302",
        "comerciante": "Imobiliária ABC LTDA",
        "valor": 2500.0,
        "available_categories": [{"nome": "Moradia"}, {"nome": "Lazer"}],
        "org_id": "org_xyz",
    }
    scrubbed = feature.redact_arguments(raw)

    # PII fields gone.
    assert "descricao" not in scrubbed
    assert "comerciante" not in scrubbed
    assert "valor" not in scrubbed
    # Structural metadata preserved.
    assert scrubbed["tipo"] == "despesa"
    assert scrubbed["has_descricao"] is True
    assert scrubbed["has_comerciante"] is True
    assert scrubbed["available_category_count"] == 2
    assert scrubbed["org_id"] == "org_xyz"


def test_categorize_redact_result_strips_explanation_keeps_classification():
    feature = get_feature("pf.transaction_categorize")
    assert feature is not None
    assert feature.redact_result is not None

    raw_result = {
        "kind": "classification",
        "label": "Moradia",
        "chip": "MORADIA",
        "explanation": "Padrão recorrente mensal — provavelmente aluguel residencial fixo",
        "confidence": 0.95,
        "score": None,
        "model_version": "gpt-4o-mini",
        "prompt_version": "pf-categorize@v1",
        "matched_categoria_id": "cat_42",
    }
    scrubbed = feature.redact_result(raw_result)

    # Free-text explanation gone.
    assert "explanation" not in scrubbed
    # Classification metadata kept.
    assert scrubbed["kind"] == "classification"
    assert scrubbed["label"] == "Moradia"
    assert scrubbed["chip"] == "MORADIA"
    assert scrubbed["confidence"] == 0.95
    assert scrubbed["model_version"] == "gpt-4o-mini"
    assert scrubbed["prompt_version"] == "pf-categorize@v1"
    assert scrubbed["matched_categoria_id"] == "cat_42"


def test_categorize_redactors_tolerate_non_dict_input():
    feature = get_feature("pf.transaction_categorize")
    # Defensive — redactors must not crash on unexpected shapes.
    assert feature.redact_arguments("garbage") == {}
    assert feature.redact_arguments(None) == {}
    assert feature.redact_result("garbage") is None
    assert feature.redact_result(None) is None


# ---------------------------------------------------------------------------
# pf.recurring_flag
# ---------------------------------------------------------------------------


def test_recurring_redact_arguments_strips_descricao_valor_and_history():
    feature = get_feature("pf.recurring_flag")
    assert feature is not None

    raw = {
        "tipo": "despesa",
        "descricao": "Netflix Premium Mensal R$ 55.90",
        "valor": 55.9,
        "similar_history": [
            {"data": "2026-04-10", "valor": 55.9, "descricao": "Netflix abr"},
            {"data": "2026-03-10", "valor": 55.9, "descricao": "Netflix mar"},
        ],
        "org_id": "org_xyz",
    }
    scrubbed = feature.redact_arguments(raw)

    # PII fields gone — including per-history descricao + valor.
    assert "descricao" not in scrubbed
    assert "valor" not in scrubbed
    assert "similar_history" not in scrubbed
    # Structural metadata preserved.
    assert scrubbed["tipo"] == "despesa"
    assert scrubbed["has_descricao"] is True
    assert scrubbed["similar_history_count"] == 2
    assert scrubbed["org_id"] == "org_xyz"


def test_recurring_redact_result_keeps_flag_and_score():
    feature = get_feature("pf.recurring_flag")
    raw = {
        "kind": "flag",
        "label": "recorrente",
        "chip": "RECORRENTE",
        "score": 0.88,
        "confidence": 0.88,
        "explanation": "Cobranças idênticas a cada 30 dias do mesmo comerciante Netflix",
        "model_version": "gpt-4o-mini",
        "prompt_version": "pf-recurring@v1",
    }
    scrubbed = feature.redact_result(raw)

    assert "explanation" not in scrubbed
    assert scrubbed["label"] == "recorrente"
    assert scrubbed["chip"] == "RECORRENTE"
    assert scrubbed["score"] == 0.88
    assert scrubbed["model_version"] == "gpt-4o-mini"
    assert scrubbed["prompt_version"] == "pf-recurring@v1"


# ---------------------------------------------------------------------------
# pf.monthly_narrative — HIGH-RISK feature; the audit row keeps very little.
# ---------------------------------------------------------------------------


def test_monthly_narrative_redact_arguments_strips_all_amounts():
    feature = get_feature("pf.monthly_narrative")
    assert feature is not None

    raw = {
        "period_label": "Últimos 30 dias (2026-04-11 → 2026-05-11)",
        "period_days": 30,
        "receita": 8500.50,
        "despesa": 5230.10,
        "fluxo": 3270.40,
        "poupanca_pct": 38.5,
        "top_categorias": [
            {"nome": "Moradia", "total": 2500.0},
            {"nome": "Mercado", "total": 1100.0},
            {"nome": "Transporte", "total": 480.0},
        ],
        "transacoes_count": 87,
        "org_id": "org_xyz",
    }
    scrubbed = feature.redact_arguments(raw)

    # Every numeric financial amount must be gone.
    for forbidden_key in ("receita", "despesa", "fluxo", "poupanca_pct"):
        assert forbidden_key not in scrubbed, f"{forbidden_key} leaked into audit"
    # `total` values inside top_categorias entries gone — only `nome` retained
    # via `top_categoria_names`. The raw list is replaced.
    assert "top_categorias" not in scrubbed
    # Structural metadata kept (count + names enable BI rollups).
    assert scrubbed["period_label"].startswith("Últimos")
    assert scrubbed["period_days"] == 30
    assert scrubbed["transacoes_count"] == 87
    assert scrubbed["top_categoria_count"] == 3
    assert scrubbed["top_categoria_names"] == ["Moradia", "Mercado", "Transporte"]
    assert scrubbed["org_id"] == "org_xyz"


def test_monthly_narrative_redact_result_drops_full_narrative_text():
    feature = get_feature("pf.monthly_narrative")

    raw_narrative = (
        "Você teve um mês equilibrado com receita de R$ 8.500,50 e despesas "
        "de R$ 5.230,10, resultando em fluxo líquido positivo de R$ 3.270,40. "
        "Sua maior categoria de gasto foi Moradia (R$ 2.500). "
        "Considere reservar parte do fluxo positivo para investimentos."
    )
    scrubbed = feature.redact_result(raw_narrative)

    # The narrative text itself must NOT appear in the scrubbed payload.
    assert isinstance(scrubbed, dict)
    assert "R$" not in str(scrubbed)
    assert "Moradia" not in str(scrubbed)
    # Only a length-class signal survives.
    assert scrubbed.get("narrative_length_class") == "non-empty"


def test_monthly_narrative_redact_result_dict_keeps_only_versions():
    """When the dispatch wrapper passes a dict (alternate result shape),
    redaction strips everything except model + prompt version."""
    feature = get_feature("pf.monthly_narrative")
    raw = {
        "narrative": "História pessoal financeira longa...",
        "receita_total": 8500.50,
        "despesa_total": 5230.10,
        "model_version": "gpt-4o-mini",
        "prompt_version": "pf-monthly-narrative@v1",
    }
    scrubbed = feature.redact_result(raw)
    assert "narrative" not in scrubbed
    assert "receita_total" not in scrubbed
    assert "despesa_total" not in scrubbed
    assert scrubbed["model_version"] == "gpt-4o-mini"
    assert scrubbed["prompt_version"] == "pf-monthly-narrative@v1"


# ---------------------------------------------------------------------------
# Catalog-level invariants — every PF feature wires a redactor pair.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "feature_key",
    [
        "pf.transaction_categorize",
        "pf.recurring_flag",
        "pf.monthly_narrative",
    ],
)
def test_every_pf_feature_has_both_redactors_registered(feature_key):
    """Catalog invariant: any PF feature that hits an LLM dispatch site MUST
    register BOTH `redact_arguments` and `redact_result`. Defends against the
    Phase 0 finding (zero redaction wired across 35 register_feature calls
    platform-wide) by pinning the contract at the PF surface."""
    feature = get_feature(feature_key)
    assert feature is not None
    assert callable(feature.redact_arguments), (
        f"{feature_key} missing redact_arguments — LGPD gap"
    )
    assert callable(feature.redact_result), (
        f"{feature_key} missing redact_result — LGPD gap"
    )
