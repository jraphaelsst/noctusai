-- 052_imovelweb_portal_leads.sql — ImovelWeb / OpenNavent portal-lead ingestion
--
-- The SECOND portal pipe, beside 051's Grupo OLX. A different vendor:
-- ImovelWeb · Wimoveis · Casa Mineira belong to Navent (Grupo QuintoAndar),
-- not to Grupo OLX — which also ships an ImovelWeb bridge, so one human
-- enquiry can reach us down both pipes. See the duplicate note below.
--
--   imovelweb_lead_events  durable delivery inbox (callback AND reconcile)
--   imovelweb_leads        lossless vendor ledger
--   imovelweb_agencies     agency code → org: the tenant-resolution key
--
-- Three vendor facts drive the shape:
--   * 1.5 SECONDS to answer a delivery, or it is scored an error. So the
--     receiver persists once and answers; everything else is background.
--   * 72 HOURS of retries, then the callback goes VENCIDO. Combined with the
--     pull API, a miss is RECOVERABLE — which is why `source` distinguishes
--     'callback' from 'reconcile' below.
--   * The dedup key is the vendor's `eventId`, which identifies the
--     DELIVERY. `originLeadId` is the CONTACT and legitimately fans out to
--     several events (a phone reveal, then a message, on the same listing).
--     Keying on the contact would silently collapse distinct leads.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ─── leads: the generic external-id idempotency key ─────────────────────
-- Already added by 051. Repeated with IF NOT EXISTS so this migration is
-- correct whether 051 ran, will run, or never runs — and so NO third
-- per-source column is created. 041 added `meta_lead_id`; 051 replaced that
-- approach with the generic pair; a third would make it a pattern.
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS external_source  TEXT,
    ADD COLUMN IF NOT EXISTS external_lead_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_external_lead
    ON social_wiring.leads (org_id, external_source, external_lead_id)
    WHERE external_lead_id IS NOT NULL;

-- ⚠️ This index does NOT catch a cross-pipe duplicate. An advertiser live on
-- both Grupo OLX's ImovelWeb bridge and our direct integration receives the
-- same enquiry twice, with two different vendor ids and two different
-- `external_source` values ('grupo-olx' and 'imovelweb'). That is a real
-- possibility, and it is deliberately NOT solved with a fuzzy key here:
-- surfacing a duplicate-SUSPECT count on (email|phone, listing, ±30 min) is
-- advisory, and merging is a human decision. A fuzzy unique index would
-- silently drop genuinely distinct leads.

-- ─── imovelweb_lead_events — the delivery inbox ─────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imovelweb_lead_events (
    id                TEXT PRIMARY KEY,   -- the vendor's eventId: the DELIVERY
    org_id            UUID,               -- NULL ⇒ status='unresolved' (never guessed)
    event_type        TEXT,               -- CONTACTO | CONTACTO_MENSAJE | AVISO_* | CREDITO
    codigo_imobiliaria TEXT,              -- the agency code WE assigned: the org hook
    client_listing_id TEXT,               -- our listing code, the fallback org hook
    lead_origin       TEXT,               -- Imovelweb | Wimoveis | CasaMineira (EN2 only)
    callback_language TEXT,               -- EN | EN2 | EN_SF | ES | PT
    source            TEXT NOT NULL DEFAULT 'callback',
    payload           JSONB NOT NULL,     -- the verified body, lossless
    status            TEXT NOT NULL DEFAULT 'received',
    error             TEXT,
    attempts          INTEGER NOT NULL DEFAULT 0,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at      TIMESTAMPTZ,
    CONSTRAINT imovelweb_lead_events_status_chk CHECK (
        status IN ('received', 'processed', 'error', 'unresolved', 'ignored')
    ),
    CONSTRAINT imovelweb_lead_events_source_chk CHECK (
        source IN ('callback', 'reconcile')
    )
);

ALTER TABLE social_wiring.imovelweb_lead_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovelweb_lead_events_select_own_org"
    ON social_wiring.imovelweb_lead_events;
CREATE POLICY "imovelweb_lead_events_select_own_org"
    ON social_wiring.imovelweb_lead_events
    FOR SELECT
    TO authenticated
    USING (org_id = public.current_org_id());

-- Literal name `service_role_bypass` — the check_admin_endpoint_service_role_bypass
-- keeper matches on the NAME, so a descriptive one (051 used
-- `olx_lead_events_service_role`) is invisible to it.
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.imovelweb_lead_events;
CREATE POLICY "service_role_bypass" ON social_wiring.imovelweb_lead_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- The drain's exact predicate. Partial, so it stays near-empty in steady
-- state where nearly everything is 'processed'.
CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_lead_events_pending
    ON social_wiring.imovelweb_lead_events (status, received_at)
    WHERE status IN ('received', 'error', 'unresolved');

CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_lead_events_org_time
    ON social_wiring.imovelweb_lead_events (org_id, received_at DESC);

-- Tenant resolution reads this on every delivery.
CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_lead_events_agency
    ON social_wiring.imovelweb_lead_events (codigo_imobiliaria);

COMMENT ON TABLE social_wiring.imovelweb_lead_events IS
    'Durable inbox for ImovelWeb deliveries. PK = the vendor eventId (the '
    'DELIVERY, not the contact — one contact fans out to several events). '
    'org_id NULL ⇒ unresolved: the tenant could not be determined and nothing '
    'was written, rather than guessed.';

COMMENT ON COLUMN social_wiring.imovelweb_lead_events.source IS
    'How this event reached us: ''callback'' (the vendor pushed it) or '
    '''reconcile'' (we pulled it after a missed delivery). A RISING reconcile '
    'share is the operator-visible symptom of blowing the 1.5s response '
    'budget — the leads still arrive, just late and by the slower path.';

COMMENT ON COLUMN social_wiring.imovelweb_lead_events.callback_language IS
    'Which language variant the body arrived in. The registered '
    'lenguajeCallbackBody decides the vendor''s FIELD NAMES, so this is the '
    'only forensic record if someone changes it vendor-side and bodies '
    'quietly start arriving in another shape.';

-- 🔴 LGPD. This column can contain `identificationId` — a CPF — because it is
-- the lossless body. It is NOT projected into a typed column, NOT copied into
-- `leads`, and MUST NOT be selected into any API response: the events route
-- returns an explicit column list, never `select("*")`. Retention is answered
-- by a scheduled job that NULLs `payload` on processed rows past the horizon
-- and KEEPS the row — the id is the dedup key, and deleting it would let a
-- late redelivery re-ingest the lead. → KB § PATTERNS/security/lgpd.md
COMMENT ON COLUMN social_wiring.imovelweb_lead_events.payload IS
    'The lossless vendor body. MAY CONTAIN A CPF (identificationId) — treat as '
    'personal data: never selected into an API response, never logged, and '
    'NULLed (row kept) by the retention job.';

-- ─── imovelweb_leads — the lossless vendor ledger ───────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imovelweb_leads (
    id                     TEXT PRIMARY KEY,   -- eventId
    org_id                 UUID NOT NULL,
    event_type             TEXT,
    contact_type_id        INTEGER,
    contact_type           TEXT,
    origin_lead_id         TEXT,               -- the CONTACT id; fans out
    message_id             BIGINT,
    lead_origin            TEXT,
    origin_listing_id      TEXT,
    client_listing_id      TEXT,
    internal_reference     TEXT,
    codigo_imobiliaria     TEXT,
    id_navplat_development BIGINT,
    development_code       TEXT,
    name                   TEXT,
    email                  TEXT,
    ddd                    TEXT,
    phone                  TEXT,
    phone_number           TEXT,
    message                TEXT,
    user_id_navplat        TEXT,
    lead_timestamp         TIMESTAMPTZ,
    smartlead              JSONB,              -- nullable: enrichment, fetched later
    raw                    JSONB NOT NULL,
    synced_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 🔴 There is deliberately NO `identification_id` column. The CPF is parsed
-- so the contract stays honest about what arrives, and then dropped: LGPD
-- minimization (Art. 6.III) says do not store what no feature uses. If a
-- feature ever needs it, that is a tech-lead decision with a dedicated
-- column, a documented TTL and a column GRANT — not a default.

ALTER TABLE social_wiring.imovelweb_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovelweb_leads_select_own_org" ON social_wiring.imovelweb_leads;
CREATE POLICY "imovelweb_leads_select_own_org" ON social_wiring.imovelweb_leads
    FOR SELECT
    TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.imovelweb_leads;
CREATE POLICY "service_role_bypass" ON social_wiring.imovelweb_leads
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_leads_org_time
    ON social_wiring.imovelweb_leads (org_id, lead_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_leads_client_listing
    ON social_wiring.imovelweb_leads (client_listing_id);

-- The contact→events fan-in: "every event from this person".
CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_leads_origin_lead
    ON social_wiring.imovelweb_leads (origin_lead_id);

-- Reconciliation dedup. A pulled `Mensaje` carries no eventId, so the
-- reconcile path looks up by message_id before inserting.
CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_leads_message
    ON social_wiring.imovelweb_leads (message_id);

COMMENT ON TABLE social_wiring.imovelweb_leads IS
    'Lossless ledger of ImovelWeb lead deliveries — exactly what the vendor '
    'sent. The unified `leads` projection is derived from this, never the '
    'reverse.';

COMMENT ON COLUMN social_wiring.imovelweb_leads.raw IS
    'The whole vendor body. MAY CONTAIN A CPF (identificationId) — treat as '
    'personal data: never selected into an API response, never logged.';

COMMENT ON COLUMN social_wiring.imovelweb_leads.smartlead IS
    'Buyer-intent enrichment, fetched AFTER the durable write. Nullable on '
    'purpose: enrichment failing is a degradation, never a lost lead. '
    'Behavioural profiling of an identified person — LGPD Art. 20 engages if '
    'a lead is ever scored or routed on it.';

-- ─── imovelweb_agencies — the tenant-resolution key ─────────────────────
-- A third table beyond the two-per-vendor shape, and it earns it: this IS
-- the org-resolution map, it is per-org and multi-row, and it therefore
-- cannot live in app-wide config. WE choose `codigo_imobiliaria` at
-- onboarding (it goes in the vendor's login-button URL), which is what makes
-- resolution a pure lookup instead of a guess.
CREATE TABLE IF NOT EXISTS social_wiring.imovelweb_agencies (
    codigo_imobiliaria TEXT PRIMARY KEY,
    org_id             UUID NOT NULL,
    razao_social       TEXT,
    authorized_at      TIMESTAMPTZ,
    last_seen_at       TIMESTAMPTZ,
    raw                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.imovelweb_agencies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovelweb_agencies_select_own_org"
    ON social_wiring.imovelweb_agencies;
CREATE POLICY "imovelweb_agencies_select_own_org" ON social_wiring.imovelweb_agencies
    FOR SELECT
    TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.imovelweb_agencies;
CREATE POLICY "service_role_bypass" ON social_wiring.imovelweb_agencies
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- NOT unique: one org legitimately holds several agency codes (a group with
-- several imobiliárias, or one per brand).
CREATE INDEX IF NOT EXISTS idx_sw_imovelweb_agencies_org
    ON social_wiring.imovelweb_agencies (org_id);

COMMENT ON TABLE social_wiring.imovelweb_agencies IS
    'Which ImovelWeb agency code belongs to which org. THE tenant-resolution '
    'key: a lead carrying a code absent from this table parks as unresolved '
    'rather than being attributed to a guess. The reconcile job runs on the '
    'admin client and bypasses RLS, so this map is the isolation boundary — a '
    'bug here is a cross-tenant leak.';

-- ─── integration_accounts: allow the imovelweb provider ─────────────────
-- Same dynamic-lookup drop as 051 and 024: migration 005 declared the CHECK
-- inline, so its name is whatever Postgres generated on that database and a
-- named `DROP CONSTRAINT IF EXISTS` silently no-ops.
--
-- ⚠️ ORDERING: 051 and this migration both rewrite this CHECK by dynamic
-- lookup, and the LATER one wins outright. So this list must be a SUPERSET of
-- 051's — dropping 'olx' here would break the OLX picker the moment 052 runs.
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
        'youtube', 'google_drive', 'gmail', 'meta', 'n8n', 'instagram',
        'olx', 'imovelweb'
    ));

-- ─── lead_sources: NO change ────────────────────────────────────────────
-- `imovel-web` and `casa-mineira` already ship in
-- app/modules/leads/seed_data.py::CANONICAL_SOURCES, so attribution resolves
-- without a migration. `wimoveis` is deliberately NOT minted: no BR lead has
-- ever been observed carrying it, and a slug for a value we have not seen is
-- a dimension nobody can explain. It folds into `imovel-web` with the true
-- value preserved in the ledger's `lead_origin`.
