"""Therapy AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 7 (2026-04-27). 2 features, both
**HIGH-RISK** (Art. 11 LGPD sensitive data — clinical text in prompt) and
therefore `default_granted=False` per §7.2 rubric — opt-in only.

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.

**LGPD redaction wiring (2026-05-11 — llm-tool-audit-rollout Phase 4).**
Each `register_feature(...)` call below pairs with a redactor entry in
`app.services.audit_hook.REDACTION_BY_FEATURE` keyed by the SAME feature
key. The dispatch site looks up the redactor via that key and scrubs
`arguments` + `result` BEFORE constructing the `AuditRecord`.

The seed `register_feature(...)` does NOT currently accept
`redact_arguments=` / `redact_result=` kwargs — Q2 in `projects/
llm-tool-audit-rollout/PROJECT.md` §7 captures the seed-side lift. Until
that ships, the redactors live in `audit_hook.REDACTION_BY_FEATURE` and
are referenced by feature_key — equivalent posture, lambdas-on-feature
shape pending. The cross-reference asserts (below) lock the bijection
so a future drop of a `register_feature` call without a matching
redactor (or vice-versa) is loud, not silent.

**Design note (2026-04-27 — surfaced during Phase 7 wiring):** the actual
guard placement (where `await require(...)` is called inside
`ai_pipeline`) is tracked separately as `therapy-consent-guard-wiring`
because it requires a design decision: is consent checked against the
**patient** (data subject — LGPD-correct) or the **therapist** (caller)?
Per §7.4 the answer is patient, but the integration into the background
ai_pipeline + the fallback behavior (silent skip / notification /
hard-block) needs interrogation. This file ships the catalog so users
see the features in `/api/me/consents`; the guards mount in the follow-up
project after the design questions are answered.
"""
from __future__ import annotations

from noctusai_lib.domain.ai import register_feature

# T-longitudinal — Longitudinal narrative regeneration (HIGH-RISK Art. 11)
# Redactor: see app.services.audit_hook.REDACTION_BY_FEATURE
# ["therapy.longitudinal_narrative"] — scrubs the multi-session aggregation
# (highest sensitivity surface in therapy: clinical text from ALL sessions).
register_feature(
    "therapy.longitudinal_narrative",
    title="Narrativa longitudinal por IA (clínica + pessoal)",
    rationale=(
        "A IA gera duas narrativas longitudinais sobre seu acompanhamento "
        "clínico: uma para o terapeuta (clínica), outra para você (pessoal). "
        "As narrativas consolidam temas e padrões a partir do histórico de "
        "sessões e observações. Conteúdo clínico de Art. 11 LGPD entra no "
        "provedor LLM. Opt-in: necessário consentir para que as narrativas "
        "sejam geradas."
    ),
    product="therapy",
    default_granted=False,
)

# T-session-summary — Per-session summary generation (HIGH-RISK Art. 11)
# Redactor: see app.services.audit_hook.REDACTION_BY_FEATURE
# ["therapy.session_summary"] — scrubs transcript + observations from the
# prompt; preserves only structural counts in audit row.
register_feature(
    "therapy.session_summary",
    title="Resumo de sessão por IA",
    rationale=(
        "A IA gera um resumo da sessão a partir da transcrição do áudio + "
        "observações do terapeuta. O resumo é usado para revisão clínica e "
        "compõe o histórico longitudinal. Conteúdo clínico de Art. 11 LGPD "
        "entra no provedor LLM. Opt-in: necessário consentir para que o "
        "resumo seja gerado após cada sessão."
    ),
    product="therapy",
    default_granted=False,
)


# ---------------------------------------------------------------------------
# Cross-reference assert — redactor coverage for every registered feature
# ---------------------------------------------------------------------------
#
# Loud failure at import-time if a `register_feature` call lands without a
# matching redactor in `audit_hook.REDACTION_BY_FEATURE`. This is the
# closest equivalent to "redact_* required" until the seed-side lift in
# PROJECT.md §7 Q2 ships.

def _assert_redactor_coverage() -> None:
    """Verify each registered therapy feature has a redactor wired."""
    # Local import — `audit_hook` imports `app.models.tool_call_audit` which
    # depends on app.models init; doing this at module top-level would create
    # an import order constraint. Late import is safe — this runs once at
    # boot after `register_feature` has populated the catalog.
    from app.services.audit_hook import REDACTION_BY_FEATURE
    from noctusai_lib.domain.ai import get_catalog

    therapy_features = {f.key for f in get_catalog() if f.product == "therapy"}
    missing = therapy_features - set(REDACTION_BY_FEATURE.keys())
    if missing:
        raise RuntimeError(
            "ai_consent_features: every therapy feature must have a redactor "
            f"in audit_hook.REDACTION_BY_FEATURE. Missing: {sorted(missing)}. "
            "Fix by adding the redactor pair, OR remove the register_feature "
            "call. See `projects/llm-tool-audit-rollout/PROJECT.md` §7 Q2."
        )


_assert_redactor_coverage()
