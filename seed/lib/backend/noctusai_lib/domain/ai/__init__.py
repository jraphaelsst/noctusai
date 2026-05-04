"""
AI helpers — shared types + persistence for per-entity AI outputs.

Shipped 2026-04-25 by ai-expansion Tier 2 Phase 3 (P1 pattern). The
`AIOutput` shape is the canonical contract between any product's AI
service (which writes one row per AI inference per entity) and the
shared `<AIIndicator>` component (which fetches + displays them).

Usage from a product service:

    from noctusai_lib.domain.ai import AIOutput, persist_output

    out = AIOutput(
        ref_type="ativo",
        ref_id=imovel_id,
        kind="classification",
        label="Categoria: Mercado",
        score=0.92,
        chip="Mercado",
        explanation="Texto contém 'mercado' e 'lista'",
        confidence=0.92,
        prompt_version="erp-categorize@v1",
    )
    persist_output(db_client, schema="erp", out)

Usage from a frontend component (TypeScript):

    <AIIndicator refType="ativo" refId={imovel.id} />

Display-shape contract: services SHOULD pass `chip` for short-form badge
text (≤20 chars). `score` is a 0-1 confidence-like float OR an arbitrary
domain scalar — interpret per `kind`. `explanation` is for hover/expand;
keep it ≤140 chars.
"""
from .consent import (
    AIConsentRequired,
    ConsentFeature,
    MandatoryFeatureCannotBeToggled,
    configure_consent_module,
    consent_required,
    fetch_user_decisions,
    get_catalog,
    get_feature,
    is_consent_module_configured,
    is_granted,
    list_user_consent_view,
    pending_count,
    register_feature,
    require,
    reset_catalog_for_test,
    reset_consent_module_for_test,
    upsert_decision,
)
from .outputs import AIOutput, persist_output, fetch_outputs_for, safe_persist_indicator

__all__ = [
    # P1 indicator pattern (Phase 3)
    "AIOutput",
    "persist_output",
    "fetch_outputs_for",
    # AI-plumbing absorption (ai-plumbing-seed-absorption, 2026-05-04)
    "safe_persist_indicator",
    # X6 consent pattern (Phase 19)
    "AIConsentRequired",
    "MandatoryFeatureCannotBeToggled",
    "ConsentFeature",
    "register_feature",
    "get_feature",
    "get_catalog",
    "fetch_user_decisions",
    "is_granted",
    "require",
    "upsert_decision",
    "list_user_consent_view",
    "pending_count",
    "reset_catalog_for_test",
    # X6 router-level guard (consent-guard-rollout Phase 1, 2026-04-27)
    "consent_required",
    "configure_consent_module",
    "is_consent_module_configured",
    "reset_consent_module_for_test",
]
