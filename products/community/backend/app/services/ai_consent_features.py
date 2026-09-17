"""Community AI consent features — registered at app boot.

One feature (module 3, community-m3-contract.md §3 "AI-flag hand-off"):
AI-flagged moderation of WhatsApp group messages. `toggleable=False`
(locked-on infrastructure, visible in the catalog for transparency) —
see `app.services.moderacao_ai_service`'s module docstring for why this
is NOT gated via `consent_required(...)`: the data subject is a WhatsApp
community member, who does not always have an authenticated platform
identity to gate against. The member's legal basis is the join-time
consent text (contract §6), obtained out-of-band from this catalog.

Imported once by `app.main` via `consent_features=
"app.services.ai_consent_features"` so this `register_feature(...)` call
populates the platform-wide consent catalog at boot — and so the
redactors below are wired for LGPD-safe audit logging if/when this
product gains a `tool_call_audits` sink (NOC-REMEDIATE note below).

**LGPD redaction.** `redact_arguments` / `redact_result` scrub message
text before anything would reach an audit trail — only structural
metadata (category, severity, model/prompt version) survives.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.ai import register_feature


def _redact_avaliar_arguments(arguments: Any) -> dict[str, Any]:
    """`avaliar_mensagem` arguments -> keep structural metadata only;
    drop the message text (`conteudo`) entirely."""
    if not isinstance(arguments, dict):
        return {}
    return {
        "org_id": arguments.get("org_id"),
        "mensagem_id": (arguments.get("mensagem") or {}).get("id")
        if isinstance(arguments.get("mensagem"), dict) else None,
        "has_conteudo": bool(
            isinstance(arguments.get("mensagem"), dict)
            and arguments["mensagem"].get("conteudo")
        ),
    }


def _redact_avaliar_result(result: Any) -> Any:
    """`avaliar_mensagem` result -> keep categoria/severidade/model
    metadata; drop `justificativa` (free-text, may echo message content)."""
    if not isinstance(result, dict):
        return None
    return {
        "categoria": result.get("categoria"),
        "severidade": result.get("severidade"),
        "modelo": result.get("modelo"),
        "prompt_versao": result.get("prompt_versao"),
        "estado": result.get("estado"),
    }


register_feature(
    "community.moderacao_whatsapp",
    title="Moderação de mensagens de WhatsApp por IA",
    rationale=(
        "A IA analisa mensagens enviadas nos grupos oficiais de WhatsApp da "
        "comunidade para sinalizar conteúdo que precise de revisão humana "
        "(assédio, spam, discurso de ódio, conteúdo ilegal). O consentimento "
        "do membro é obtido no momento da entrada na comunidade — ver o "
        "texto de consentimento do contrato §6."
    ),
    product="community",
    default_granted=True,
    toggleable=False,
    redact_arguments=_redact_avaliar_arguments,
    redact_result=_redact_avaliar_result,
)

# NOC-REMEDIATE[community-tool-call-audit]: this product has no
# `tool_call_audits` sink yet (no Postgres/SQLAlchemy wiring — Supabase
# admin/user clients are the only DB path today). The redactors above are
# registered so a future audit-writer wiring is correct-by-construction
# from day one, matching PF/therapy's `ai_consent_features.py` shape —
# but no row is written anywhere yet. — 2026-09-17
