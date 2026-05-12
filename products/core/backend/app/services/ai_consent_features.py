"""Core AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 6 (2026-04-27). Single feature today:
audit-log digest (admin-tier, low-risk — only aggregated event counts +
privileged-action highlights enter the prompt; no per-user PII).

Imported once by `app.main` so its `register_feature(...)` calls populate
the platform-wide consent catalog at boot.

**LGPD redaction (per `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`).**
The seed `register_feature(...)` does not accept redaction lambdas today —
the canonical pattern is to declare per-feature redaction callables next
to the feature registration and apply them at the AuditRecord-construction
site. The `REDACT_AUDIT_DIGEST_*` callables below scrub aggressively
because core's audit digest touches org metadata, user IDs, and (if a
billing event ever enters the highlight set) billing-action labels.

Project `llm-tool-audit-rollout` Q2 + Phase 0 finding 2 track lifting
redaction into `register_feature(...)` as a seed-side enhancement; until
that lands, every product co-locates its lambdas here.
"""
from __future__ import annotations

import re
from typing import Any

from noctusai_lib.domain.ai import register_feature

# ---------------------------------------------------------------------------
# Feature registration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# LGPD redaction for the audit-digest dispatch site
# ---------------------------------------------------------------------------
# Applied at `app/services/audit_digest_service.py` before the AuditRecord is
# constructed. Scrub aggressively because the audit-digest LLM call touches:
#
#   - org_id / org_name        → identifies a customer
#   - user_id / user IDs       → identifies individuals
#   - email addresses          → PII (LGPD Art. 5 I)
#   - billing.* action labels  → financial signal
#
# The intent: only operational aggregates (action counts, period_days,
# total_events, narrative_chars) survive into `tool_call_audits.arguments`
# and `.result`. Anything that could re-identify a person or a customer is
# replaced with a `[REDACTED]` sentinel.

_REDACT_KEYS = frozenset({
    "org_id",
    "org_name",
    "user_id",
    "user_ids",
    "email",
    "emails",
    "recipients",
    "user_email",
    "user",
    "users",
})

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def _scrub_string(value: str) -> str:
    """Replace emails + UUIDs in a free-text string with `[REDACTED]`."""
    value = _EMAIL_RE.sub("[REDACTED]", value)
    value = _UUID_RE.sub("[REDACTED]", value)
    return value


def _scrub_value(value: Any) -> Any:
    """Recursively scrub a JSON-shaped value. Tuples are coerced to lists
    so JSONB serialization stays clean."""
    if value is None:
        return None
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k in _REDACT_KEYS else _scrub_value(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_value(item) for item in value]
    # Numbers, bools — safe as-is.
    return value


def REDACT_AUDIT_DIGEST_ARGUMENTS(arguments: dict[str, Any] | None) -> dict[str, Any] | None:
    """Scrub the `arguments` field for a `core.audit_digest` AuditRecord.

    Replaces every sensitive key (org_id, user_id, email, …) with the
    `[REDACTED]` sentinel and scrubs embedded emails + UUIDs inside
    string values. Operational aggregates (action counts, period_days,
    total_events) pass through untouched.

    Best-effort: any exception during scrubbing yields `None` so the
    audit row still lands without leaking raw data.
    """
    if arguments is None:
        return None
    try:
        scrubbed = _scrub_value(arguments)
        if isinstance(scrubbed, dict):
            return scrubbed
        return {"_repr": "[REDACTED]"}
    except Exception:
        return None


def REDACT_AUDIT_DIGEST_RESULT(result: Any) -> Any:
    """Scrub the `result` field for a `core.audit_digest` AuditRecord.

    The audit-digest narrative is free text the LLM authored from
    aggregated counts — it should not contain PII by construction, but
    we still scrub embedded emails + UUIDs defensively. Long narratives
    are truncated to the leading 1000 chars (the BI consumer only needs
    enough to know what was said; full text lives in the digest email).
    """
    if result is None:
        return None
    try:
        scrubbed = _scrub_value(result)
        if isinstance(scrubbed, str) and len(scrubbed) > 1000:
            return scrubbed[:1000] + "…[truncated]"
        return scrubbed
    except Exception:
        return None


__all__ = [
    "REDACT_AUDIT_DIGEST_ARGUMENTS",
    "REDACT_AUDIT_DIGEST_RESULT",
]
