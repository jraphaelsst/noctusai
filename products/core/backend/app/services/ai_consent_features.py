"""Core AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 6 (2026-04-27). Single feature today:
audit-log digest (admin-tier, low-risk — only aggregated event counts +
privileged-action highlights enter the prompt; no per-user PII).

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.
"""
from __future__ import annotations

from noctusai_lib.domain.ai import register_feature

# C2 — Audit-log digest (admin-tier, low-risk: only event-count aggregates
# + privileged-action highlights enter the prompt; no per-user PII)
register_feature(
    "core.audit_digest",
    title="Resumo de auditoria por IA",
    rationale=(
        "A IA gera um resumo narrativo de 3 parágrafos sobre os eventos de "
        "auditoria da sua organização nos últimos N dias — contagens por "
        "ação, contagens por usuário (anonimizadas) e destaques de ações "
        "privilegiadas. Os dados que entram no prompt são apenas estatísticas "
        "agregadas, sem PII individual. Acessível apenas para administradores."
    ),
    product="core",
    default_granted=True,
)
