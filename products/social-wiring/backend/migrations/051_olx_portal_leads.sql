-- 051_olx_portal_leads.sql — Grupo OLX portal-lead ingestion
--
-- Adds the inbound side of the Grupo OLX lead pipe (ZAP · VivaReal · OLX ·
-- ImovelWeb · Casa Mineira — one webhook for all of them):
--
--   olx_lead_events  durable delivery inbox   (mirrors meta_webhook_events)
--   olx_leads        lossless vendor ledger   (mirrors meta_ads_leads)
--   leads.external_source / external_lead_id  GENERIC idempotency key
--
-- Why the generic key rather than an `olx_lead_id` column: migration 041
-- added `meta_lead_id` + a partial unique index for Meta. A second
-- per-source column here makes it a pattern, and the third portal makes it
-- a mess — N columns, N indexes, N near-identical lookups. One
-- (external_source, external_lead_id) pair carries every present and future
-- source. `meta_lead_id` is left in place and backfilled into the new pair;
-- nothing is dropped, so this is additive and reversible.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ─── leads: the generic external-id idempotency key ─────────────────────
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS external_source  TEXT,
    ADD COLUMN IF NOT EXISTS external_lead_id TEXT;

COMMENT ON COLUMN social_wiring.leads.external_source IS
    'Which upstream produced this lead (''grupo-olx'', ''meta-lead-ads'', …). '
    'Together with external_lead_id it is the cross-source idempotency key. '
    'NULL for spreadsheet/manual leads, which key on (source_sheet, source_row).';
COMMENT ON COLUMN social_wiring.leads.external_lead_id IS
    'The upstream''s OWN id for this lead (OLX originLeadId, Meta leadgen_id). '
    'Vendors re-deliver: OLX retries 3x and stores 14 days, so a repeat is '
    'normal traffic, not an error.';

-- Backfill the Meta rows so the generic key is complete from day one — a
-- half-populated key is worse than none (a lookup would miss the older
-- rows and happily insert a duplicate).
UPDATE social_wiring.leads
   SET external_source = 'meta-lead-ads',
       external_lead_id = meta_lead_id
 WHERE meta_lead_id IS NOT NULL
   AND external_lead_id IS NULL;

-- Partial, so the index only covers rows that actually have an external id
-- (the vast majority are spreadsheet imports that never will).
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_external_lead
    ON social_wiring.leads (org_id, external_source, external_lead_id)
    WHERE external_lead_id IS NOT NULL;

-- ─── olx_lead_events — the delivery inbox ───────────────────────────────
-- Persist-then-200. OLX judges delivery ONLY by our status code, retries a
-- non-2xx 3x, then discards the lead after 14 days with no replay API. So
-- the durable row — not the status code — is what makes a processing
-- failure recoverable.
CREATE TABLE IF NOT EXISTS social_wiring.olx_lead_events (
    id            TEXT PRIMARY KEY,          -- OLX originLeadId (natural dedup key)
    org_id        UUID,                      -- NULL ⇒ status='unresolved' (never guessed)
    client_listing_id TEXT,                  -- OUR listing id; the org-resolution hook
    lead_origin   TEXT,                      -- 'Grupo OLX' | 'MCMV_OLX'
    lead_type     TEXT,                      -- extraData.leadType
    payload       JSONB NOT NULL,            -- the verified body, lossless
    status        TEXT NOT NULL DEFAULT 'received',
    error         TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ,
    CONSTRAINT olx_lead_events_status_chk CHECK (
        status IN ('received', 'processed', 'error', 'unresolved', 'ignored')
    )
);

ALTER TABLE social_wiring.olx_lead_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "olx_lead_events_select_own_org" ON social_wiring.olx_lead_events;
CREATE POLICY "olx_lead_events_select_own_org" ON social_wiring.olx_lead_events
    FOR SELECT
    TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "olx_lead_events_service_role" ON social_wiring.olx_lead_events;
CREATE POLICY "olx_lead_events_service_role" ON social_wiring.olx_lead_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- The retry job's exact predicate: pending work, oldest first. Partial so
-- the index stays small — steady state is nearly everything 'processed'.
CREATE INDEX IF NOT EXISTS idx_sw_olx_lead_events_pending
    ON social_wiring.olx_lead_events (status, received_at)
    WHERE status IN ('received', 'error', 'unresolved');

CREATE INDEX IF NOT EXISTS idx_sw_olx_lead_events_org_time
    ON social_wiring.olx_lead_events (org_id, received_at DESC);

COMMENT ON TABLE social_wiring.olx_lead_events IS
    'Durable inbox for inbound Grupo OLX lead deliveries. PK = originLeadId '
    '(replay dedup). org_id NULL ⇒ unresolved: the tenant could not be '
    'determined and nothing was written, rather than guessed.';

-- ─── olx_leads — the lossless vendor ledger ─────────────────────────────
-- Typed core + JSONB tail, the same shape as meta_ads_leads: the columns we
-- query on are promoted, and `raw` keeps everything the vendor sent —
-- including fields our contract does not know about yet.
CREATE TABLE IF NOT EXISTS social_wiring.olx_leads (
    id                TEXT PRIMARY KEY,      -- OLX originLeadId
    org_id            UUID NOT NULL,
    lead_origin       TEXT,
    origin_listing_id TEXT,
    client_listing_id TEXT,
    name              TEXT,
    email             TEXT,
    phone             TEXT,
    message           TEXT,
    temperature       TEXT,
    transaction_type  TEXT,
    lead_type         TEXT,
    lead_timestamp    TIMESTAMPTZ,
    extra_data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw               JSONB NOT NULL,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.olx_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "olx_leads_select_own_org" ON social_wiring.olx_leads;
CREATE POLICY "olx_leads_select_own_org" ON social_wiring.olx_leads
    FOR SELECT
    TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "olx_leads_service_role" ON social_wiring.olx_leads;
CREATE POLICY "olx_leads_service_role" ON social_wiring.olx_leads
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_olx_leads_org_time
    ON social_wiring.olx_leads (org_id, lead_timestamp DESC);

-- `clientListingId` is our own listing code, and it is the primary hook for
-- resolving which org a lead belongs to (see the receiver's resolution
-- chain) as well as the natural "leads for this property" query.
CREATE INDEX IF NOT EXISTS idx_sw_olx_leads_client_listing
    ON social_wiring.olx_leads (client_listing_id);

COMMENT ON TABLE social_wiring.olx_leads IS
    'Lossless ledger of Grupo OLX lead deliveries — exactly what the vendor '
    'sent. `raw` is the whole body; the typed columns are the queried subset. '
    'The unified `leads` projection is derived from this, never the reverse.';

-- ─── integration_accounts: allow the olx provider ───────────────────────
-- The CHECK is a hand-maintained list, so it has to be widened explicitly
-- before the FE can offer OLX in the connect-an-account picker.
--
-- Constraint dropped by DYNAMIC LOOKUP, not by name — migration 005
-- declared it inline, so its name is whatever Postgres auto-generated on
-- that particular database. Migration 024 learned this the same way; a
-- named `DROP CONSTRAINT IF EXISTS` silently no-ops against the real
-- constraint and the ADD then fails on a duplicate.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'social_wiring'
          AND rel.relname = 'integration_accounts'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%provider%'
    LOOP
        EXECUTE format(
            'ALTER TABLE social_wiring.integration_accounts DROP CONSTRAINT IF EXISTS %I',
            r.conname
        );
    END LOOP;
END $$;

ALTER TABLE social_wiring.integration_accounts
    ADD CONSTRAINT integration_accounts_provider_check
    CHECK (provider IN (
        'youtube', 'google_drive', 'gmail', 'meta', 'n8n', 'instagram', 'olx'
    ));
