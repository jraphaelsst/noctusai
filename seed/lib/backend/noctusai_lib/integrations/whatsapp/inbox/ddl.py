"""DDL templates for the inbox tables (authoring-time helpers — a product
copies the output into its own migration, same as
``whatsapp_connections_table_ddl``).

Prerequisites on the target project: ``public.current_org_id()`` and
``<schema>.set_updated_at()`` (``noctusai_lib.domain.sql_templates.updated_at_function``),
and the ``whatsapp_connections`` table (``whatsapp_connections_table_ddl``).

Design (lifted from social-wiring migration 042, minus its SW coupling):

* ``whatsapp_chats`` PK ``(connection_id, chat_id)``; ``unread_count`` is a
  DERIVED value recomputed from ``whatsapp_messages`` (never incremented —
  ``message`` and ``message.any`` race for the same send, an increment loses
  updates silently).
* ``whatsapp_messages`` UNIQUE ``(connection_id, waha_message_id)`` is THE
  dedup guard (the Redis/in-memory pre-filter is only a cost optimisation).
* ``origin`` + ``new_chat_notified_at`` make ``on_new_chat`` exactly-once:
  the notification is CLAIMED by a conditional UPDATE, so a replayed webhook,
  a ``message``+``message.any`` pair, or a deleted downstream lead (the chat
  row persists) can never fire it twice.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    service_role_bypass,
    updated_at_trigger,
)

CHATS_TABLE = "whatsapp_chats"
MESSAGES_TABLE = "whatsapp_messages"
CONNECTIONS_TABLE = "whatsapp_connections"


def whatsapp_chats_table_ddl(
    schema: str,
    *,
    table: str = CHATS_TABLE,
    connections_table: str = CONNECTIONS_TABLE,
) -> str:
    select_policy = rls_subquery_policy(
        schema, table, f"{table}_select_own_org", "SELECT",
        using="org_id = current_org_id()",
    )
    return (
        f"CREATE TABLE {schema}.{table} (\n"
        f"    connection_id UUID NOT NULL REFERENCES {schema}.{connections_table}(id) ON DELETE CASCADE,\n"
        f"    chat_id TEXT NOT NULL,\n"
        f"    org_id UUID NOT NULL,\n"
        f"    name TEXT,\n"
        f"    phone TEXT,\n"
        f"    is_group BOOLEAN NOT NULL DEFAULT false,\n"
        f"    origin TEXT NOT NULL DEFAULT 'inbound'\n"
        f"        CHECK (origin IN ('inbound', 'outbound', 'backfill')),\n"
        f"    new_chat_notified_at TIMESTAMPTZ,\n"
        f"    last_message_at TIMESTAMPTZ,\n"
        f"    last_message_preview TEXT NOT NULL DEFAULT '',\n"
        f"    last_message_from_me BOOLEAN,\n"
        f"    unread_count INTEGER NOT NULL DEFAULT 0,\n"
        f"    last_read_at TIMESTAMPTZ,\n"
        f"    synced_through TIMESTAMPTZ,\n"
        f"    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    PRIMARY KEY (connection_id, chat_id)\n"
        f");\n\n"
        f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;\n\n"
        f"{select_policy}\n\n"
        f"{service_role_bypass(table, schema=schema)}\n\n"
        f"-- THE chat-list query: newest activity first, chat_id as the keyset tiebreak.\n"
        f"CREATE INDEX idx_{schema}_{table}_list\n"
        f"    ON {schema}.{table} (connection_id, last_message_at DESC, chat_id DESC);\n\n"
        f"{updated_at_trigger(schema, table)}"
    )


def whatsapp_messages_table_ddl(
    schema: str,
    *,
    table: str = MESSAGES_TABLE,
    chats_table: str = CHATS_TABLE,
) -> str:
    select_policy = rls_subquery_policy(
        schema, table, f"{table}_select_own_org", "SELECT",
        using="org_id = current_org_id()",
    )
    return (
        f"CREATE TABLE {schema}.{table} (\n"
        f"    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        f"    org_id UUID NOT NULL,\n"
        f"    connection_id UUID NOT NULL,\n"
        f"    chat_id TEXT NOT NULL,\n"
        f"    waha_message_id TEXT NOT NULL,\n"
        f"    from_me BOOLEAN NOT NULL,\n"
        f"    body TEXT NOT NULL DEFAULT '',\n"
        f"    type TEXT NOT NULL DEFAULT 'chat',\n"
        f"    media_url TEXT,\n"
        f"    media_mimetype TEXT,\n"
        f"    ack SMALLINT,\n"
        f"    acked_at TIMESTAMPTZ,\n"
        f"    sender_name TEXT,\n"
        f"    sender_phone TEXT,\n"
        f"    timestamp TIMESTAMPTZ NOT NULL,\n"
        f"    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    FOREIGN KEY (connection_id, chat_id)\n"
        f"        REFERENCES {schema}.{chats_table}(connection_id, chat_id) ON DELETE CASCADE,\n"
        f"    UNIQUE (connection_id, waha_message_id)\n"
        f");\n\n"
        f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;\n\n"
        f"{select_policy}\n\n"
        f"{service_role_bypass(table, schema=schema)}\n\n"
        f"-- THE thread query (and the unread recount).\n"
        f"CREATE INDEX idx_{schema}_{table}_thread\n"
        f"    ON {schema}.{table} (connection_id, chat_id, timestamp DESC, waha_message_id DESC);"
    )
