"""Therapy AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 7 (2026-04-27). 2 features, both
**HIGH-RISK** (Art. 11 LGPD sensitive data — clinical text in prompt) and
therefore `default_granted=False` per §7.2 rubric — opt-in only.

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.

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
