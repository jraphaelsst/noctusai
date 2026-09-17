"""WhatsApp inbound-message ingest — contract §3 item 19 + the
engagement + AI-flag hand-offs.

Mounted as the `on_message` callable the seed's
`create_whatsapp_webhook_router(...)` calls after signature verification
+ the Redis dedup pre-filter (see `app/routers/whatsapp_webhook_router.py`).
`handle_inbound` is this product's ENTIRE webhook business logic — no
second WAHA client, no second webhook verifier, no second dedup.

LGPD (contract §6): never logs `conteudo`, `autor_jid`/`participante_jid`,
member phones, invite links, the WAHA API key, the webhook HMAC secret,
the raw webhook body, or the LLM prompt/completion. Logs only
`(grupo_id, provider_message_id, membro_id, resultado)`-shaped facts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from noctusai_lib.domain.engagement import (
    DuplicateEvent,
    EngagementEvent,
    PointRule,
    RuleSet,
    evaluate,
    make_points_ledger,
)
from noctusai_lib.integrations.whatsapp.lid_auth import normalize_phone
from noctusai_lib.integrations.whatsapp.types import WhatsAppInboundMessage
from noctusai_lib.primitives.tasks import schedule_coro

from app.config import settings
from app.dependencies import get_admin_client, resolve_public_org_id

logger = logging.getLogger(__name__)

_GRUPOS = "grupos"
_GRUPO_MEMBROS = "grupo_membros"
_GRUPO_MENSAGENS = "grupo_mensagens"

# Placeholder engagement rule pending an owner-configurable rules table
# (out of this module's scope — see the delivery note's scoped-improvement
# footer). One point per group message, capped per UTC day so a chatty
# member can't farm the leaderboard.
_ENGAGEMENT_RULES = RuleSet.from_rules([
    PointRule(source="whatsapp", action="mensagem_grupo", points=1, daily_cap=20),
])

_UNIQUE_VIOLATION_CODE = "23505"


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "code", None) == _UNIQUE_VIOLATION_CODE


async def handle_inbound(
    inbound: WhatsAppInboundMessage,
    *,
    moderar_em_background: bool = True,
    org_id: Any = None,
    client: Any = None,
    modo_ingest: str | None = None,
    points_ledger: Any = None,
) -> None:
    """`on_message` callable for the seed's WhatsApp webhook router.

    Drops any message whose `group_id is None` (a DM to the community
    number is not this module's business) and any `group_id` not known
    to `grupos` (contract §3 item 19).

    `org_id` / `client` / `modo_ingest` / `points_ledger` are injectable
    collaborators (default to the real resolvers when omitted) — the
    seam tests use to run this function deterministically without
    patching this module's own code
    (`KB § PATTERNS/backend/di-test-seam.md`).
    """
    if inbound.group_id is None:
        return

    org_id = org_id if org_id is not None else resolve_public_org_id()
    client = client if client is not None else get_admin_client()
    modo_ingest = modo_ingest if modo_ingest is not None else settings.modo_ingest

    grupo = (
        client.table(_GRUPOS).select("*")
        .eq("org_id", str(org_id)).eq("chat_id", inbound.group_id)
        .maybe_single().execute().data
    )
    if not grupo:
        logger.debug("ingest: unknown group grupo_id=%s — dropped", inbound.group_id)
        return

    autor_jid = inbound.author_id
    membro_id = None
    if autor_jid:
        roster_row = (
            client.table(_GRUPO_MEMBROS).select("membro_id")
            .eq("org_id", str(org_id)).eq("grupo_id", grupo["id"])
            .eq("participante_jid", autor_jid)
            .maybe_single().execute().data
        )
        if roster_row:
            membro_id = roster_row.get("membro_id")

    conteudo = inbound.text if modo_ingest == "moderacao" else None
    now = datetime.now(timezone.utc)
    mensagem_row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "grupo_id": grupo["id"],
        "provider_message_id": inbound.provider_message_id or str(uuid4()),
        "autor_jid": autor_jid,
        "membro_id": membro_id,
        "conteudo": conteudo,
        "tem_midia": inbound.media is not None,
        "recebida_em": now.isoformat(),
    }
    try:
        result = client.table(_GRUPO_MENSAGENS).insert(mensagem_row).execute()
    except Exception as exc:  # noqa: BLE001 — narrowed below
        if _is_unique_violation(exc):
            logger.debug(
                "ingest: duplicate provider_message_id grupo_id=%s — DB backstop no-op",
                grupo["id"],
            )
            return
        raise
    if not result.data:
        logger.warning("ingest: insert returned no row grupo_id=%s", grupo["id"])
        return
    mensagem = result.data[0]

    if membro_id:
        await _award_engagement(
            client, org_id=org_id, membro_id=membro_id,
            provider_message_id=mensagem_row["provider_message_id"], occurred_at=now,
            points_ledger=points_ledger,
        )

    coro = _flag_message_best_effort(client, org_id=org_id, mensagem=mensagem)
    if moderar_em_background:
        schedule_coro(coro, logger=logger, name=f"moderacao-{mensagem['id']}")
    else:
        await coro


async def _award_engagement(
    client: Any, *, org_id, membro_id, provider_message_id: str, occurred_at: datetime,
    points_ledger: Any = None,
) -> None:
    ledger = points_ledger if points_ledger is not None else make_points_ledger(
        supabase_client=client, schema_name="community", table_name="engajamento_pontos",
    )
    event = EngagementEvent(
        member_id=str(membro_id), source="whatsapp", action="mensagem_grupo",
        occurred_at=occurred_at, idempotency_key=f"wa:{provider_message_id}",
    )
    history = ledger.history(str(membro_id), source="whatsapp", action="mensagem_grupo")
    outcome = evaluate(event, _ENGAGEMENT_RULES, history)
    if isinstance(outcome, DuplicateEvent):
        logger.debug("ingest: duplicate engagement event membro_id=%s", membro_id)
        return
    for award in outcome:
        ledger.record(award)


async def _flag_message_best_effort(client: Any, *, org_id, mensagem: dict) -> None:
    """Best-effort AI-flag hand-off — never raises into the caller
    (fire-and-forget in prod; a synchronous await in tests)."""
    try:
        from app.services.moderacao_ai_service import avaliar_mensagem

        await avaliar_mensagem(client, org_id=org_id, mensagem=mensagem)
    except Exception:
        logger.warning(
            "ingest: moderacao_ai_service failed for mensagem_id=%s",
            mensagem.get("id"), exc_info=True,
        )
