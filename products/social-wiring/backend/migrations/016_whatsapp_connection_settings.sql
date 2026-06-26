-- 016_whatsapp_connection_settings.sql — per-connection intake configuration
--
-- Project: wa-conn-config (2026-06-26). Adds two per-WhatsApp-connection
-- lists that gate the intake agent:
--
--   authorized_numbers — phone numbers / JIDs allowed to trigger the agent.
--                        Empty list = ALL numbers allowed (per-connection
--                        semantics — differs from the global env var where
--                        empty means DISABLED).
--   bound_chats        — specific chats (by JID) the agent listens to.
--                        Empty list = ALL chats listened to.
--
-- Both are stored as JSONB so they can be edited via a future FE without a
-- migration, and so PostgREST can validate them at the API layer.
--
-- Design decisions:
--   - DEFAULT '[]' so existing rows without these columns behave as
--     "allow all" / "listen to all" — no blast radius on deploy.
--   - Code reads defensively (row.get("authorized_numbers") or []) so an
--     un-migrated DB row (column absent) degrades gracefully, never crashes.
--   - The per-connection semantics for authorized_numbers intentionally
--     differ from the global env var:
--       env  empty → DISABLED (the global default; intake service returns None)
--       conn empty → ALLOW ALL (the per-connection default; easier onboarding)
--     This is documented here so the distinction is not lost.
--
-- Forward-only + idempotent (ADD COLUMN IF NOT EXISTS). Apply after 015.
-- The tech-lead applies this via noctus.dev.migrate_product with explicit
-- consent — DO NOT apply directly to the live DB from this file.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS authorized_numbers jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS bound_chats jsonb NOT NULL DEFAULT '[]'::jsonb;
