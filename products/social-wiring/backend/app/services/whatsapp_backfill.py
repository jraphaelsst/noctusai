"""WhatsApp inbox history backfill — walks WAHA chat history into Postgres.

Slice 4 (whatsapp-realtime-inbox, 2026-08-03) makes Postgres the read
source of truth for the chat inbox. The live webhook (``whatsapp_router.py``)
only ever sees NEW events, so a chat that already had history in WAHA
before its connection was created (or before this migration shipped) would
otherwise show up empty in the inbox until the next live message arrives.
This module fills that gap: for every configured connection, walk its
chats via the WAHA NOWEB store and persist history through the SAME two
stores the live webhook writes through (:class:`MessageStore` +
:class:`WhatsAppChatStore`), so a backfilled row is indistinguishable from
a live one.

SCHEDULING
----------
Registered on the shared seed APScheduler
(``noctusai_lib.api.scheduler``) from :func:`configure`, called at import
time from ``app/main.py`` (mirrors ``app.services.meta.scheduler``'s
``meta_insights_scheduler.configure()``) so the job lands on the scheduler
before ``app/lifespan.py``'s ``start_scheduler()`` fires.

``noctusai_lib.api.scheduler.register`` hard-codes ``max_instances=1`` —
enforced PER PROCESS. At one replica that's exactly "never overlap
itself." With more than one uvicorn worker / more than one container
replica, EACH process runs its own scheduler and its own ``max_instances=1``
job — i.e. the guarantee does NOT extend across replicas. This module does
not defend against that (no distributed lock); a multi-replica deployment
would need one before this job is safe to run everywhere. Documented here
rather than silently assumed, per the project's no-silent-errors rule.

ONE-SHOT PER CHAT, NOT TRUE INCREMENTAL CATCH-UP
--------------------------------------------------
The seed WAHA client's ``fetch_chat_messages(chat_id, limit=N)`` has no
pagination cursor (no ``before=``) — it always returns the newest ``N``
messages. Re-calling it on a later run would fetch the SAME window again,
not the next page back. So a chat's backfill is one-shot: once
``whatsapp_chats.synced_through`` is set for a ``(connection_id, chat_id)``
pair, later runs skip it. New chats (no row yet, or a row with
``synced_through IS NULL`` — e.g. one the live webhook just created)
DO get backfilled on the next run. True incremental catch-up would need a
``before=`` cursor added to the WAHA client — tracked as a
scoped-improvement, not built here.

``synced_through`` semantics: the OLDEST message timestamp actually
persisted, when the ``whatsapp_backfill_max_messages_per_chat`` cap was
hit before reaching the day cutoff (there may be older history beyond
what was fetched); otherwise the day-cutoff timestamp itself (we walked
all the way back to it and found — or persisted — everything newer).

READING ``synced_through``
---------------------------
:class:`WhatsAppChatStore` (a peer-owned file, out of this slice's
territory) does not expose ``synced_through`` on its public ``ChatSummary``
read surface. Rather than widen that store's contract on the peer's
behalf, this module reads the column directly via the admin client
(``_get_synced_through``). Contract-note: a follow-up should add a
proper accessor there so this becomes a real call instead of a raw
table read.

DEPTH CAP
---------
``whatsapp_backfill_days`` (default 90) AND
``whatsapp_backfill_max_messages_per_chat`` (default 500) — whichever
bound is hit first per chat. Implemented by requesting up to the message
cap from WAHA, then discarding anything older than the day cutoff.

DEGRADE, NEVER CRASH
---------------------
A WAHA failure at any level (session down, chat unreachable, malformed
message) is logged and the loop continues — one bad connection/chat must
never stall every other line's backfill, and the job wrapper itself
swallows everything so a bug in one run never de-registers the scheduled
job.

``session_id`` NOTE
--------------------
Backfilled rows use the raw WAHA chat JID as ``conversation_messages
.session_id`` — NOT the LID-resolved canonical session id
``WhatsAppIntakeService.canonical_session_id`` computes for live inbounds
(that resolution is an async WAHA identity call, too heavy to run per
historical message here). This is fine for the inbox surface (keyed by
``chat_id``/``raw_sender``), but means a backfilled row will not
necessarily key onto the same conversation as its live counterpart if the
sender later gets LID-resolved. Scoped-improvement, not a correctness bug
for THIS slice's scope (inbox population, not chatbot memory).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.whatsapp import get_whatsapp_client

from app.config import settings
from app.dependencies import get_admin_client
from app.services.credential_vault import EncryptionNotConfigured
from app.services.message_store import DuplicateMessage, MessageStore
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_connection_store import build_whatsapp_connection_store

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_CONNECTIONS_TABLE = "whatsapp_connections"
_CHATS_TABLE = "whatsapp_chats"


def _extract_waha_id(value: Any) -> str | None:
    """WAHA ids arrive either as a bare string or ``{"_serialized": "..."}``.

    Mirrors the shape ``whatsapp_connections_router._waha_chat_to_summary``
    / ``_waha_message_to_out`` already parse — kept as an independent copy
    here (those are a peer's private router helpers, not a shared seam)
    rather than importing across the file-territory boundary.
    """
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        serialized = value.get("_serialized") or value.get("id")
        return str(serialized) if serialized else None
    return None


def _epoch_to_datetime(ts: Any) -> datetime | None:
    """WAHA message timestamps are unix epoch seconds."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _list_all_connections(admin_client) -> list[dict[str, Any]]:
    """Every ``whatsapp_connections`` row, across ALL orgs/users.

    ``WhatsAppConnectionStore``'s public read surface is user-scoped by
    design (a per-request collaborator for the operator's own lines); the
    backfill job is a background sweep over EVERY connection, so it reads
    the raw rows directly through the admin/service-role client, then
    re-resolves each one through the store's own ``get_connection(decrypt
    =True)`` for the API key — never re-implements the Fernet decrypt.
    """
    response = (
        admin_client.schema(_SCHEMA)
        .table(_CONNECTIONS_TABLE)
        .select("id, org_id, user_id")
        .execute()
    )
    return list(response.data or [])


def _get_synced_through(admin_client, *, connection_id: UUID, chat_id: str) -> str | None:
    """Direct read of ``whatsapp_chats.synced_through`` — see the module
    docstring's "READING synced_through" section for why this bypasses
    ``WhatsAppChatStore``'s public surface instead of widening it."""
    response = (
        admin_client.schema(_SCHEMA)
        .table(_CHATS_TABLE)
        .select("synced_through")
        .eq("connection_id", str(connection_id))
        .eq("chat_id", chat_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0].get("synced_through") if rows else None


async def _backfill_chat(
    *,
    waha_client,
    message_store: MessageStore,
    chat_store: WhatsAppChatStore,
    connection_id: UUID,
    chat_id: str,
    title: str | None,
    cutoff: datetime,
    max_messages: int,
) -> None:
    """Pull + persist one chat's history, then advance its watermark.

    Depth: up to ``max_messages`` from WAHA (the client has no cursor —
    see the module docstring), filtered to ``created_at >= cutoff``.
    """
    try:
        raw_messages = await waha_client.fetch_chat_messages(chat_id, limit=max_messages)
    except Exception:
        logger.warning(
            "whatsapp_backfill: fetch_chat_messages failed for chat=%s — skipping",
            chat_id,
            exc_info=True,
        )
        return

    kept = 0
    oldest_kept: datetime | None = None
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        msg_dt = _epoch_to_datetime(raw.get("timestamp"))
        if msg_dt is None or msg_dt < cutoff:
            continue

        provider_message_id = _extract_waha_id(raw.get("id"))
        body = raw.get("body") or ""
        direction = "outbound" if raw.get("fromMe") else "inbound"
        created_at = msg_dt.isoformat()

        try:
            message_store.record(
                session_id=chat_id,
                raw_sender=chat_id,
                direction=direction,
                body=body,
                provider_message_id=provider_message_id,
                authorized=True,
                connection_id=connection_id,
                chat_id=chat_id,
                created_at=created_at,
            )
        except DuplicateMessage:
            # Already backfilled on a prior (interrupted) run, or already
            # live-ingested by the webhook — idempotent, not an error.
            pass
        except Exception:
            logger.warning(
                "whatsapp_backfill: message insert failed (chat=%s, provider_id=%s)",
                chat_id,
                provider_message_id,
                exc_info=True,
            )
            continue

        try:
            chat_store.record_message(
                connection_id=connection_id,
                chat_id=chat_id,
                direction=direction,
                body=body,
                created_at=created_at,
                title=title,
                has_media=bool(raw.get("hasMedia")),
            )
        except Exception:
            logger.warning(
                "whatsapp_backfill: whatsapp_chats upsert failed (chat=%s)",
                chat_id,
                exc_info=True,
            )

        kept += 1
        if oldest_kept is None or msg_dt < oldest_kept:
            oldest_kept = msg_dt

    # We may be truncating history WITHIN the cutoff window if WAHA
    # returned a full batch (there could be an (N+1)th message still
    # inside the window) — in that case the honest watermark is the
    # oldest message we actually got, not the full day-cutoff.
    hit_message_cap = len(raw_messages) >= max_messages
    synced_through = (
        oldest_kept if (hit_message_cap and oldest_kept is not None) else cutoff
    )
    try:
        chat_store.set_synced_through(
            connection_id=connection_id,
            chat_id=chat_id,
            synced_through=synced_through.isoformat(),
        )
    except Exception:
        logger.warning(
            "whatsapp_backfill: set_synced_through failed (chat=%s)",
            chat_id,
            exc_info=True,
        )

    logger.info(
        "whatsapp_backfill: chat=%s connection=%s kept=%d/%d",
        chat_id,
        connection_id,
        kept,
        len(raw_messages),
    )


async def run_backfill(*, cfg=None, admin_client=None) -> None:
    """Body of the scheduled backfill job.

    For every WhatsApp connection: list its chats (bounded by
    ``whatsapp_backfill_chat_limit``), and for each chat NOT already
    backfilled (``whatsapp_chats.synced_through IS NULL``), pull history
    per the depth cap and persist it. A WAHA failure for one
    connection/chat degrades (logged, loop continues) — never crashes the
    run; a single line's outage must not stall every other line's
    backfill.

    ``cfg`` / ``admin_client`` are the DI-test-seam (Class-B kwargs):
    default to the production settings singleton / admin client, so the
    scheduler's own call site (``_run_backfill_job``) is unchanged; tests
    pass explicit doubles instead of patching this module's globals.
    """
    cfg = cfg or settings
    if not cfg.whatsapp_backfill_enabled:
        logger.debug("whatsapp_backfill: disabled via settings — skipping run")
        return

    admin = admin_client or get_admin_client()
    if admin is None:
        logger.warning("whatsapp_backfill: no admin client — skipping run")
        return

    try:
        store = build_whatsapp_connection_store(admin, encryption_key=cfg.encryption_key)
    except EncryptionNotConfigured:
        logger.warning(
            "whatsapp_backfill: ENCRYPTION_KEY not configured — cannot decrypt "
            "connection API keys, skipping run"
        )
        return

    connections = _list_all_connections(admin)
    if not connections:
        logger.debug("whatsapp_backfill: no connections configured — nothing to do")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.whatsapp_backfill_days)

    for row in connections:
        try:
            connection_id = UUID(str(row["id"]))
            org_id = UUID(str(row["org_id"]))
        except (KeyError, ValueError, TypeError):
            logger.warning("whatsapp_backfill: malformed connection row %r — skipping", row)
            continue

        record = store.get_connection(
            connection_id=connection_id, org_id=org_id, decrypt=True,
        )
        if record is None or not record.api_key or not record.base_url:
            logger.debug(
                "whatsapp_backfill: connection %s not resolvable/configured — skipping",
                connection_id,
            )
            continue

        waha_client = get_whatsapp_client(
            base_url=record.base_url, api_key=record.api_key, session=record.session_name,
        )
        message_store = MessageStore(admin_supabase=admin, org_id=org_id)
        chat_store = WhatsAppChatStore(admin_supabase=admin, org_id=org_id)

        try:
            chats = await waha_client.list_chats(limit=cfg.whatsapp_backfill_chat_limit)
        except Exception:
            logger.warning(
                "whatsapp_backfill: list_chats failed for connection=%s — skipping",
                connection_id,
                exc_info=True,
            )
            continue

        for chat in chats:
            if not isinstance(chat, dict):
                continue
            chat_id = _extract_waha_id(chat.get("id"))
            if not chat_id:
                continue
            if _get_synced_through(admin, connection_id=connection_id, chat_id=chat_id):
                continue  # already backfilled once — see module docstring
            title = chat.get("name") or chat.get("pushName") or None
            await _backfill_chat(
                waha_client=waha_client,
                message_store=message_store,
                chat_store=chat_store,
                connection_id=connection_id,
                chat_id=chat_id,
                title=title,
                cutoff=cutoff,
                max_messages=cfg.whatsapp_backfill_max_messages_per_chat,
            )


async def _run_backfill_job() -> None:
    """Scheduler entrypoint — swallows ALL exceptions so a bug in one run
    never crashes the scheduler or de-registers the job."""
    try:
        await run_backfill()
    except Exception:
        logger.error("whatsapp_backfill: job run failed", exc_info=True)


def configure() -> None:
    """Register the backfill job on the seed-side scheduler.

    Called from ``app/main.py`` at import time (mirrors
    ``app.services.meta.scheduler``'s ``meta_insights_scheduler.configure()``
    call) so the job lands before ``start_scheduler()`` fires in
    ``app/lifespan.py``. Idempotent — ``noctusai_lib.api.scheduler.register``
    replaces the job on re-registration.
    """
    seed_scheduler.register(
        "whatsapp_backfill",
        _run_backfill_job,
        hours=settings.whatsapp_backfill_interval_hours,
    )
    logger.info(
        "whatsapp_backfill scheduler configured: every %dh",
        settings.whatsapp_backfill_interval_hours,
    )


__all__ = ["configure", "run_backfill"]
