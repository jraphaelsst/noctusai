"""WhatsApp inbox organ - conversations pipeline (webhook -> chats/messages
tables -> realtime) lifted out of `social-wiring` without its Julia/chatbot/
auto-reply/lead-intake behaviour.

Public surface:
- DDL: ``whatsapp_chats_table_ddl``, ``whatsapp_messages_table_ddl``.
- Types: ``InboxChat``, ``InboxMessage``.
- Store: ``WhatsAppChatStore`` Protocol + ``FakeWhatsAppChatStore`` +
  ``SupabaseWhatsAppChatStore`` + ``build_whatsapp_chat_store`` (fake-or-refuse).
- Ingest: ``ingest_waha_event`` (``message`` / ``message.any`` / ``message.ack`` /
  ``session.status``; fires ``on_new_chat`` exactly once per new non-group chat).
- Backfill: ``backfill_connection`` / ``run_backfill_all`` /
  ``register_inbox_backfill_job`` (NOWEB store; single-flight per process).
- Realtime: ``InboxRealtime`` + ``build_inbox_realtime`` (Redis or explicit
  in-process) and the ``EVENT_*`` vocabulary.

The FastAPI router factory lives in the framework:
``noctusai_seed.whatsapp_inbox_router.create_whatsapp_inbox_router``.
See ``KB § CONTEXT/INTEGRATIONS/whatsapp.md`` (inbox section).
"""
from noctusai_lib.integrations.whatsapp.inbox.backfill import (
    BackfillReport,
    backfill_connection,
    is_backfill_running,
    make_connection_lister,
    register_inbox_backfill_job,
    run_backfill_all,
)
from noctusai_lib.integrations.whatsapp.inbox.ddl import (
    whatsapp_chats_table_ddl,
    whatsapp_messages_table_ddl,
)
from noctusai_lib.integrations.whatsapp.inbox.ingest import (
    IngestResult,
    OnNewChat,
    ParsedMessage,
    ingest_waha_event,
    parse_waha_message,
    resolve_chat_identity,
)
from noctusai_lib.integrations.whatsapp.inbox.realtime import (
    EVENT_CHAT_READ,
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_NEW,
    EVENT_SESSION_STATUS,
    INBOX_EVENTS,
    InboxRealtime,
    InboxRealtimeNotConfigured,
    build_inbox_realtime,
    inbox_scope,
)
from noctusai_lib.integrations.whatsapp.inbox.store import (
    FakeWhatsAppChatStore,
    InboxStoreNotConfigured,
    SupabaseWhatsAppChatStore,
    WhatsAppChatStore,
    build_whatsapp_chat_store,
)
from noctusai_lib.integrations.whatsapp.inbox.types import ChatState, InboxChat, InboxMessage

__all__ = [
    "BackfillReport",
    "ChatState",
    "EVENT_CHAT_READ",
    "EVENT_CHAT_UPSERT",
    "EVENT_MESSAGE_ACK",
    "EVENT_MESSAGE_NEW",
    "EVENT_SESSION_STATUS",
    "FakeWhatsAppChatStore",
    "INBOX_EVENTS",
    "InboxChat",
    "InboxMessage",
    "InboxRealtime",
    "InboxRealtimeNotConfigured",
    "InboxStoreNotConfigured",
    "IngestResult",
    "OnNewChat",
    "ParsedMessage",
    "SupabaseWhatsAppChatStore",
    "WhatsAppChatStore",
    "backfill_connection",
    "build_inbox_realtime",
    "build_whatsapp_chat_store",
    "inbox_scope",
    "ingest_waha_event",
    "is_backfill_running",
    "make_connection_lister",
    "parse_waha_message",
    "register_inbox_backfill_job",
    "resolve_chat_identity",
    "run_backfill_all",
    "whatsapp_chats_table_ddl",
    "whatsapp_messages_table_ddl",
]
