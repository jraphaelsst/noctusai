"""IgIg AI consent features — registered at app boot.

Two features:

  - **`igig.assistente_negocio`** (HIGH-RISK, opt-in). The negócio card's
    "Assistente IA" panel (`POST /api/comercial/negocios/{id}/assistente`,
    `app/routers/assistente_router.py`) sends the lead's name/empresa +
    the negócio's stage/value/timeline/orçamentos to Anthropic to draft a
    resumo / próxima ação / rascunho de mensagem. That is personal data of
    a named lead transiting a third-party LLM provider, so it is gated by
    the platform's canonical AI-consent mechanism
    (`noctusai_lib.domain.ai.consent_required`) — same pattern as
    `products/daily-life/backend/app/routers/ai.py` and
    `products/core/backend/app/routers/audit_digest.py`.
    `default_granted=False`: the user must opt in via `/settings/ai`
    before the panel works.

  - **`igig.assistente_ajuda`** (locked-on, `toggleable=False`). The
    always-available help-chat bubble (`POST /api/ajuda/chat`,
    `app/routers/ajuda_router.py`, seed organ
    `noctusai_lib.domain.help_chat`) never receives customer/lead data —
    its ENTIRE context is the static platform knowledge guide
    (`app/knowledge/guia-igig.md`) plus the operator's own question.
    Registered here purely for billing/token-use transparency (the
    catalog entry appears in `/settings/ai` as always-on infrastructure);
    it is intentionally NOT wired to `consent_required(...)` anywhere —
    gating a feature that never touches personal data would just add a
    dead click with no LGPD benefit.

Imported once by `app.main` via
`consent_features="app.services.ai_consent_features"` so these
`register_feature(...)` calls populate the platform-wide consent catalog
at boot.

**LGPD redaction** (`redact_arguments` / `redact_result` on
`igig.assistente_negocio`). IgIg has no `tool_call_audits` sink wired yet
(no Postgres/SQLAlchemy audit-writer wiring — same gap noted in
`products/community/backend/app/services/ai_consent_features.py`), but
the redactors are registered now so a future audit-writer wiring is
correct-by-construction from day one: only structural metadata
(`acao`, `canal`, `negocio_id`, `org_id`) survives; the lead/negócio
context sent to the model and the generated text are dropped entirely.
See `KB § PATTERNS/llm-tool-audit.md § LGPD redaction`.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.ai import register_feature

_REDACTED = "[REDACTED]"


def _redact_assistente_arguments(arguments: Any) -> dict[str, Any]:
    """`assistente_negocio` arguments -> keep only structural routing
    metadata; drop `contexto` (lead name, empresa, notas, timeline) entirely."""
    if not isinstance(arguments, dict):
        return {}
    return {
        "acao": arguments.get("acao"),
        "canal": arguments.get("canal"),
        "negocio_id": arguments.get("negocio_id"),
        "org_id": arguments.get("org_id"),
    }


def _redact_assistente_result(result: Any) -> Any:
    """`assistente_negocio` result -> the generated text is drafted FROM
    the lead's personal data (name, empresa, negotiation notes) — drop it
    entirely, keep nothing."""
    if isinstance(result, dict):
        return {k: _REDACTED for k in result if k == "texto"} or None
    if isinstance(result, str):
        return _REDACTED
    return None


register_feature(
    "igig.assistente_negocio",
    title="Assistente IA do negócio",
    rationale=(
        "A IA lê os dados do lead e do negócio (nome, empresa, etapa, valor, "
        "propostas, histórico) para gerar um resumo, sugerir a próxima ação "
        "ou rascunhar uma mensagem. Esses dados pessoais transitam pelo "
        "provedor de IA (Anthropic). Opt-in: ative em Configurações > IA "
        "para usar o botão Assistente no card do negócio."
    ),
    product="igig",
    default_granted=False,
    toggleable=True,
    redact_arguments=_redact_assistente_arguments,
    redact_result=_redact_assistente_result,
)

register_feature(
    "igig.assistente_ajuda",
    title="Assistente de ajuda (chat de suporte)",
    rationale=(
        "O balão de ajuda responde perguntas sobre como usar o IgIg usando "
        "apenas o guia estático da plataforma — nunca dados de clientes, "
        "leads ou negócios. Aparece aqui apenas para transparência do uso "
        "de tokens de IA; não pode ser desativado individualmente."
    ),
    product="igig",
    default_granted=True,
    toggleable=False,
)
