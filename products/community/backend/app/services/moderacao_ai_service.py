"""AI-flagged moderation — contract §3 "AI-flag hand-off".

Runs AFTER the ingest transaction commits (never inline in the webhook —
see `app.services.ingest_service.handle_inbound`), so a slow/failing LLM
call never makes WAHA retry the webhook delivery. One `mensagem_flags`
row per flagged message; the hand-off to a human moderator IS the row —
this module never auto-resolves anything.

**Consent posture (design decision — surfaced, not silently assumed).**
`noctusai_lib.domain.ai.consent_required(...)` is a FastAPI router
dependency keyed on an AUTHENTICATED platform user (`Depends(...)` reads
a JWT). This pipeline has no authenticated caller — it runs off a
webhook, and the data subject is a WhatsApp community MEMBER, who very
often never becomes a Supabase auth user at all (`membros.user_id` stays
null until they sign in — module 1). Gating a background job behind
"whichever manager happens to be logged in when a webhook fires"
would be nonsensical, not LGPD-correct. The member's actual legal basis
is the join-time consent text (contract §6 / D1's precondition), not a
per-request AI toggle. This module therefore registers the feature as
`toggleable=False` (locked-on infrastructure, visible in the catalog for
transparency) in `app.services.ai_consent_features`, and relies on its
`redact_arguments` / `redact_result` for the "message text never reaches
a tool-audit log" requirement — it does NOT call `consent_required(...)`
as a dependency. See the delivery note's drift-found footer.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from noctusai_lib.integrations.llm import chat_completion, get_llm_config

logger = logging.getLogger(__name__)

_MENSAGEM_FLAGS = "mensagem_flags"
FEATURE_KEY = "community.moderacao_whatsapp"
_PROMPT_VERSION = "v1"
_VALID_SEVERIDADES = ("baixa", "media", "alta")

_SYSTEM_PROMPT = (
    "Você modera mensagens de grupos de WhatsApp de uma comunidade paga. "
    "Analise a mensagem do usuário e responda APENAS com um objeto JSON "
    "no formato exato: "
    '{"flagged": bool, "categoria": string ou null, '
    '"severidade": "baixa"|"media"|"alta", "justificativa": string ou null}. '
    "Marque flagged=true apenas para conteúdo que precise de revisão humana "
    "(assédio, spam comercial não autorizado, discurso de ódio, conteúdo "
    "ilegal). Mensagens normais de conversa devem ter flagged=false."
)


def _parse_response(raw: str) -> dict | None:
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("moderacao_ai: resposta não é JSON válido")
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


async def avaliar_mensagem(client: Any, *, org_id, mensagem: dict) -> dict | None:
    """Classify one ingested message; insert a `mensagem_flags` row when
    the model flags it. Returns the inserted row, or `None` when nothing
    was flagged (a normal outcome — not every message needs review) or
    the message carries no text (`MODO_INGEST='metrica'`)."""
    conteudo = mensagem.get("conteudo")
    if not conteudo:
        return None

    config = get_llm_config()
    modelo = config.default_chat_model
    try:
        resposta = await chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": conteudo},
            ],
            org_id=str(org_id),
            response_format={"type": "json_object"},
            cache=False,
        )
    except Exception:
        # Structural metadata only — never the message text (LGPD §6).
        logger.warning(
            "moderacao_ai: chat_completion falhou mensagem_id=%s",
            mensagem.get("id"), exc_info=True,
        )
        return None

    parsed = _parse_response(resposta)
    if not parsed or not parsed.get("flagged"):
        return None

    severidade = parsed.get("severidade")
    if severidade not in _VALID_SEVERIDADES:
        severidade = "baixa"

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "mensagem_id": mensagem["id"],
        "categoria": parsed.get("categoria"),
        "severidade": severidade,
        "justificativa": parsed.get("justificativa"),
        "modelo": modelo,
        "prompt_versao": _PROMPT_VERSION,
        "estado": "aberta",
    }
    result = client.table(_MENSAGEM_FLAGS).insert(row).execute()
    return result.data[0] if result.data else None
