-- Migration: 117_notification_catalog
-- Schema: public (core)
-- Project: owner-notifications.
--
-- WHAT: the platform catalog of owner-facing notifications (the WhatsApp scripted messages the owner receives when
-- a process "warns" him), with a per-product, per-kind on/off switch and a send ledger.
--   * public.notification_kinds — one row per (product, kind). Each product DECLARES its kinds in code
--     (`noctusai_lib.domain.notification_catalog`) and upserts them at startup, so the catalog lists every created
--     notification without anyone typing it in. `enabled` is the owner's switch (core admin "Notificações" page);
--     the upsert never touches it, so a redeploy never re-enables a kind the owner turned off.
--   * public.notification_sends — one row per dispatch decision (sent / failed / suppressed-by-switch / no recipient),
--     so the page can show how each notification actually behaves day to day (last sent, 30-day counts).
--     Counts, ids and a short reason only — never the message text or a phone number (LGPD: operator metadata).
-- Additive only; the previous images never read these tables. Apply BEFORE the new images (a missing table makes the
-- seed gate log an ERROR and SEND anyway — fail toward warning the owner, never toward silence).
-- Re-runnable: IF NOT EXISTS / DROP-then-CREATE POLICY.
-- NOC-REMEDIATE[notification-sends-retention]: purge notification_sends older than 180 days once volume is measured — 2026-12-09
SET search_path = public, public;
SET lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS public.notification_kinds (
    product        TEXT NOT NULL CHECK (length(product) BETWEEN 1 AND 100),
    kind           TEXT NOT NULL CHECK (kind ~ '^[a-z0-9_]{1,80}$'),
    titulo         TEXT NOT NULL CHECK (length(titulo) BETWEEN 1 AND 160),
    descricao      TEXT NOT NULL CHECK (length(descricao) BETWEEN 1 AND 1000),
    gatilho        TEXT NOT NULL CHECK (length(gatilho) BETWEEN 1 AND 500),
    canais         TEXT[] NOT NULL DEFAULT ARRAY['whatsapp']::TEXT[],
    enabled        BOOLEAN NOT NULL DEFAULT true,
    toggled_at     TIMESTAMPTZ,
    toggled_by     UUID,
    registered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product, kind)
);
-- Owner-facing notification kinds declared by each product + the owner's on/off switch. Service role only.
COMMENT ON TABLE public.notification_kinds IS 'tier:service';

CREATE TABLE IF NOT EXISTS public.notification_sends (
    id          BIGSERIAL PRIMARY KEY,
    product     TEXT NOT NULL CHECK (length(product) BETWEEN 1 AND 100),
    kind        TEXT NOT NULL CHECK (kind ~ '^[a-z0-9_]{1,80}$'),
    org_id      UUID,
    status      TEXT NOT NULL CHECK (status IN ('sent', 'partial', 'failed', 'suppressed', 'no_recipient')),
    recipients  INTEGER NOT NULL DEFAULT 0 CHECK (recipients >= 0),
    delivered   INTEGER NOT NULL DEFAULT 0 CHECK (delivered >= 0),
    reason      TEXT CHECK (reason IS NULL OR length(reason) <= 300),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One row per owner-notification dispatch decision (no message text, no phone numbers). Service role only.
COMMENT ON TABLE public.notification_sends IS 'tier:service';
CREATE INDEX IF NOT EXISTS ix_notification_sends_kind_created
    ON public.notification_sends (product, kind, created_at DESC);

ALTER TABLE public.notification_kinds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_sends ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_kinds FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_sends FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.notification_kinds TO service_role;
GRANT ALL ON public.notification_sends TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.notification_sends_id_seq TO service_role;

DROP POLICY IF EXISTS "service_role_bypass" ON public.notification_kinds;
CREATE POLICY "service_role_bypass" ON public.notification_kinds
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON public.notification_sends;
CREATE POLICY "service_role_bypass" ON public.notification_sends
    FOR ALL TO service_role USING (true) WITH CHECK (true);
