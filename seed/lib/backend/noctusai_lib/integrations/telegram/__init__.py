"""Telegram Bot API (publish-only) -- Protocol + Fake + Real + factory, with line store, webhook guard, rate wiring.

Public surface: ``TelegramClient`` Protocol, ``make_telegram_client`` (Real, or a declared refusal; Fake only
with ``allow_fake=True``), ``FakeTelegramClient``, ``HttpxTelegramClient``, typed errors, ``verify_bot_channel_admin``,
``verify_telegram_secret_token`` / ``connect_webhook`` (clobber guard), ``FakeTelegramLineStore`` /
``build_telegram_line_store``, ``make_telegram_line_event_sink``, ``telegram_tables_sql``.
KB: ``KB § PATTERNS/backend/seed-fake-real-adapter.md`` · ``KB § PATTERNS/integrations/integration-craft-canon.md``.
"""
from .channels import verify_bot_channel_admin
from .ddl import telegram_tables_sql
from .events import (
    FakeTelegramLineEventSink, LineEventPersistenceError, SupabaseTelegramLineEventSink, TelegramLineEvent,
    make_telegram_line_event_sink,
)
from .factory import make_telegram_client
from .fake_adapter import FakeTelegramClient
from .line_store import (
    FakeTelegramLineStore, SupabaseTelegramLineStore, TelegramLineConflictError, TelegramLineRecord,
    TelegramLineStore, TelegramLineStoreError, build_telegram_line_store,
)
from .real_adapter import HttpxTelegramClient
from .redact import mask_token, redact
from .types import *  # noqa: F401,F403 -- value objects, errors, Protocol
from .webhook import (
    SECRET_HEADER, connect_webhook, ensure_webhook_ours, require_telegram_secret_token,
    verify_telegram_secret_token, webhook_estrangeiro_http_exception,
)
