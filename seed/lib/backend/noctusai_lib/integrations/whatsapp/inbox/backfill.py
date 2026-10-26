"""History backfill from the WAHA NOWEB store (+ the scheduler job).

TRAPS (read before touching):

* **NOWEB store required.** ``list_chats`` / ``fetch_chat_messages`` only work
  on a session started with ``store.enabled`` + ``fullSync`` (the seed's
  ``start_session`` / ``restart_session`` do that by default). WAHA answers
  HTTP 400 otherwise -> the run reports ``noweb_store_required`` instead of
  pretending it synced nothing.
* **Single-flight is PER PROCESS.** ``_IN_FLIGHT`` is an in-memory set; the
  seed scheduler's ``max_instances=1`` is per process too. With >1 uvicorn
  worker / container replica each process may backfill the same connection
  concurrently. That is SAFE (the ``UNIQUE (connection_id, waha_message_id)``
  guard makes inserts idempotent) but wasteful; a distributed lock is the fix
  - NOC-REMEDIATE[wa-inbox-backfill-distributed-lock]: deferred, no multi-
  replica consumer yet - 2026-10-26.
* **One-shot per chat.** ``fetch_chat_messages`` has no ``before=`` cursor, so
  it always returns the newest N. ``synced_through`` marks a chat done;
  later runs skip it unless ``force=True``.
* Backfilled chats are ``origin='backfill'``: they NEVER fire ``on_new_chat``
  and start with ``last_read_at=now`` (history is not "unread").
* @lid chats are canonicalised through the lid cache only (no per-chat WAHA
  call over history); an unknown @lid stays an @lid chat id.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional
from uuid import UUID

import httpx
from starlette.concurrency import run_in_threadpool

from noctusai_lib.integrations.whatsapp.connection_store import (
    WhatsAppConnectionRecord,
    WhatsAppConnectionStore,
)
from noctusai_lib.integrations.whatsapp.inbox.ingest import parse_waha_message, resolve_chat_identity
from noctusai_lib.integrations.whatsapp.inbox.store import WhatsAppChatStore, parse_ts
from noctusai_lib.integrations.whatsapp.inbox.types import ORIGIN_BACKFILL
from noctusai_lib.integrations.whatsapp.lid_auth import LidPhoneCache
from noctusai_lib.integrations.whatsapp.mappers import normalize_waha_id

logger = logging.getLogger(__name__)

_IN_FLIGHT: set[str] = set()
_IN_FLIGHT_LOCK = threading.Lock()

STATUS_OK = "ok"
STATUS_ALREADY_RUNNING = "already_running"
STATUS_NOWEB_REQUIRED = "noweb_store_required"
STATUS_ERROR = "error"


@dataclass
class BackfillReport:
    connection_id: UUID
    status: str = STATUS_OK
    chats_seen: int = 0
    chats_synced: int = 0
    chats_skipped: int = 0
    messages_inserted: int = 0
    errors: list[str] = field(default_factory=list)


def is_backfill_running(connection_id: UUID) -> bool:
    with _IN_FLIGHT_LOCK:
        return str(connection_id) in _IN_FLIGHT


async def backfill_connection(
    *,
    record: WhatsAppConnectionRecord,
    chat_store: WhatsAppChatStore,
    waha_client: Any,
    lid_cache: Optional[LidPhoneCache] = None,
    days: int = 90,
    max_messages_per_chat: int = 500,
    chat_limit: int = 200,
    force: bool = False,
) -> BackfillReport:
    """Pull one connection's WAHA history into the inbox tables. Never raises
    for a WAHA failure - the outcome is in the report (a bad chat must not
    stall the others)."""
    key = str(record.id)
    report = BackfillReport(connection_id=record.id)
    with _IN_FLIGHT_LOCK:
        if key in _IN_FLIGHT:
            report.status = STATUS_ALREADY_RUNNING
            return report
        _IN_FLIGHT.add(key)
    try:
        await _run(
            report, record=record, chat_store=chat_store, waha_client=waha_client, lid_cache=lid_cache,
            cutoff=datetime.now(timezone.utc) - timedelta(days=days),
            max_messages=max_messages_per_chat, chat_limit=chat_limit, force=force,
        )
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT.discard(key)
    return report


async def _list_all_chats(waha_client: Any, limit: int) -> list[dict[str, Any]]:
    page = min(limit, 100)
    chats: list[dict[str, Any]] = []
    offset = 0
    while len(chats) < limit:
        batch = await waha_client.list_chats(limit=page, offset=offset)
        chats.extend(c for c in batch if isinstance(c, dict))
        if len(batch) < page:
            break
        offset += page
    return chats[:limit]


async def _run(
    report: BackfillReport, *, record: WhatsAppConnectionRecord, chat_store: WhatsAppChatStore,
    waha_client: Any, lid_cache: Optional[LidPhoneCache], cutoff: datetime, max_messages: int,
    chat_limit: int, force: bool,
) -> None:
    try:
        chats = await _list_all_chats(waha_client, chat_limit)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            report.status = STATUS_NOWEB_REQUIRED
            report.errors.append(
                "WAHA store not enabled: start the session with the NOWEB store (store.enabled + fullSync)"
            )
            logger.warning("inbox backfill: connection=%s needs the NOWEB store (HTTP 400)", record.id)
        else:
            report.status = STATUS_ERROR
            report.errors.append(f"list_chats HTTP {exc.response.status_code}")
            logger.warning("inbox backfill: list_chats failed connection=%s", record.id, exc_info=True)
        return
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        report.status = STATUS_ERROR
        report.errors.append(f"list_chats failed: {type(exc).__name__}")
        logger.warning("inbox backfill: list_chats failed connection=%s", record.id, exc_info=True)
        return

    for chat in chats:
        jid = normalize_waha_id(chat.get("id"))
        if not jid:
            continue
        report.chats_seen += 1
        identity = await resolve_chat_identity(
            jid, push_name=chat.get("name") or chat.get("pushName"), lid_cache=lid_cache
        )
        if not force and await run_in_threadpool(lambda: chat_store.get_synced_through(
            org_id=record.org_id, connection_id=record.id, chat_id=identity.chat_id,
        )):
            report.chats_skipped += 1
            continue
        try:
            raw = await waha_client.fetch_chat_messages(jid, limit=max_messages)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"fetch_chat_messages failed: {type(exc).__name__}")
            logger.warning("inbox backfill: fetch failed connection=%s chat=%s", record.id, jid, exc_info=True)
            continue
        await run_in_threadpool(lambda: chat_store.ensure_chat(
            org_id=record.org_id, connection_id=record.id, chat_id=identity.chat_id,
            name=identity.name, phone=identity.phone, is_group=identity.is_group, origin=ORIGIN_BACKFILL,
        ))
        kept_oldest: Optional[datetime] = None
        newest = None
        for item in raw:
            if not isinstance(item, dict):
                continue
            parsed = parse_waha_message(item, chat_jid=jid)
            if parsed is None:
                continue
            ts = parse_ts(parsed.message.timestamp)
            if ts is None or ts < cutoff:
                continue
            message = replace(parsed.message, chat_id=identity.chat_id)
            inserted = await run_in_threadpool(lambda m=message: chat_store.insert_message(
                org_id=record.org_id, connection_id=record.id, message=m,
            ))
            report.messages_inserted += int(inserted)
            kept_oldest = ts if kept_oldest is None or ts < kept_oldest else kept_oldest
            if newest is None or ts >= parse_ts(newest.timestamp):
                newest = message
        if newest is not None:  # ONE derived refresh per chat (preview, unread), not per message
            await run_in_threadpool(lambda: chat_store.refresh_chat_after_message(
                org_id=record.org_id, connection_id=record.id, chat_id=identity.chat_id,
                message=newest, name=identity.name, phone=identity.phone,
            ))
        # Honest watermark: when WAHA returned a full window there may be older
        # history beyond it, so record the oldest message actually kept.
        watermark = kept_oldest if (len(raw) >= max_messages and kept_oldest) else cutoff
        await run_in_threadpool(lambda: chat_store.set_synced_through(
            org_id=record.org_id, connection_id=record.id, chat_id=identity.chat_id,
            synced_through=watermark.isoformat(),
        ))
        report.chats_synced += 1


# ─── scheduler wiring ───────────────────────────────────────────────────────

ConnectionLister = Callable[[], Iterable[tuple[UUID, UUID]]]


def make_connection_lister(client: Any, *, schema: str, table: str = "whatsapp_connections") -> ConnectionLister:
    """``() -> [(org_id, connection_id)]`` over an admin client - the
    connection store itself only lists per org."""
    def _list() -> list[tuple[UUID, UUID]]:
        rows = client.schema(schema).table(table).select("id, org_id").execute().data or []
        return [(UUID(str(r["org_id"])), UUID(str(r["id"]))) for r in rows]

    return _list


async def run_backfill_all(
    *,
    list_connections: ConnectionLister,
    connection_store: WhatsAppConnectionStore,
    chat_store: WhatsAppChatStore,
    waha_client_factory: Callable[[WhatsAppConnectionRecord], Any],
    lid_cache: Optional[LidPhoneCache] = None,
    **backfill_kwargs: Any,
) -> list[BackfillReport]:
    """Backfill every connection (scheduler body). Per-connection failures
    are reports, not exceptions."""
    reports: list[BackfillReport] = []
    for org_id, connection_id in list_connections():
        record = await run_in_threadpool(lambda: connection_store.get_connection(
            connection_id=connection_id, org_id=org_id, decrypt=True,
        ))
        if record is None or not record.api_key:
            continue
        reports.append(await backfill_connection(
            record=record, chat_store=chat_store, waha_client=waha_client_factory(record),
            lid_cache=lid_cache, **backfill_kwargs,
        ))
    return reports


def register_inbox_backfill_job(
    runner: Callable[[], Awaitable[Any]], *, hours: int = 6, name: str = "whatsapp_inbox_backfill"
) -> None:
    """Register ``runner`` (typically a ``functools.partial`` of
    :func:`run_backfill_all`) on the seed scheduler. The wrapper swallows
    everything so one bad run never de-registers the job."""
    from noctusai_lib.api import scheduler as seed_scheduler

    async def _job() -> None:
        try:
            await runner()
        except Exception:  # noqa: BLE001
            logger.error("whatsapp inbox backfill job failed", exc_info=True)

    seed_scheduler.register(name, _job, hours=hours)
