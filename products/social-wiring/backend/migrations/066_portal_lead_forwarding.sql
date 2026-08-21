-- 066_portal_lead_forwarding.sql
--
-- Store-and-forward outbox for inbound portal leads.
--
-- WHY AN OUTBOX AND NOT A BACKGROUND POST.
--
--   The Canal Pro "Receber leads no CRM" field holds exactly ONE URL. When
--   NoctusAI takes it over from an advertiser's previous CRM, that CRM stops
--   being fed by the vendor and starts being fed by us. From that moment we
--   own the delivery — and Grupo OLX considers the lead delivered the instant
--   we answer 2xx. It never resends, and there is no replay API.
--
--   So a forward that fails is a lead the downstream CRM NEVER receives.
--   An in-process retry loop loses it to any restart; a fire-and-forget POST
--   loses it to any blip. The body has to be durable before the first attempt,
--   and the attempt has to be resumable by a scheduled drain.
--
-- WHY NO CREDENTIAL COLUMN.
--
--   The obvious design stores the inbound `Authorization` header alongside the
--   body so the forward can replay it. That would put the Grupo OLX per-CRM
--   SECRET_KEY in every outbox row, in database backups, and in any operator's
--   psql scrollback — one shared secret, copied thousands of times.
--
--   `auth_mode='passthrough'` instead RE-DERIVES the header at send time from
--   the same configured secret the receiver already validates against. It is
--   by construction the identical value the vendor sent, and it is stored
--   exactly once, where it already lived.
--
-- WHY `auth_mode` HAS ONLY TWO VALUES TODAY.
--
--   `basic` and `bearer` are trivial header construction and are deliberately
--   NOT here. What the downstream endpoint actually accepts is an open
--   question sent to the vendor on 2026-08-19
--   (`projects/olx-portal-leads-ingestion/gate-1-lastro-request.md` §3). A
--   CHECK listing modes we have not been told are correct would be a guess
--   wearing a constraint's clothing. Adding one when the answer arrives is a
--   one-line migration.
--
-- MIGRATION NUMBER: authored as 054, renumbered to 066 at integration.
--   `dev` shipped its own `054_negociacoes_venda_collapse.sql` while this
--   branch was in flight, and `check_migration_number_collision` refused
--   the integrate — correctly: two files claiming one number leaves
--   apply-order undefined. Renumbered to the next free slot rather than
--   reordering anything already merged.
--
-- Additive: two new tables. No existing object is altered.
--
-- Apply to the noctusai Supabase (social_wiring schema) at deploy.

SET search_path = social_wiring, public;

-- ─── Where a lead gets forwarded to ───────────────────────────────────

CREATE TABLE IF NOT EXISTS social_wiring.portal_lead_forward_targets (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    -- Matches `portal_receiver_tokens.provider` and
    -- `integration_accounts.provider` so the three surfaces cannot drift
    -- into different spellings of the same portal.
    provider      TEXT NOT NULL CHECK (provider IN ('olx', 'imovelweb')),

    label         TEXT NOT NULL,
    url           TEXT NOT NULL,

    -- 'passthrough' — rebuild the vendor's own Basic header from our
    --                 configured secret (see the header note above).
    -- 'none'        — send no Authorization header at all.
    auth_mode     TEXT NOT NULL DEFAULT 'passthrough'
                  CHECK (auth_mode IN ('passthrough', 'none')),

    is_active     BOOLEAN NOT NULL DEFAULT true,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Several active targets per (org, provider) is allowed on purpose: an
-- advertiser may run two downstream systems during a migration, and each
-- gets its own outbox row and its own retry budget.
CREATE INDEX IF NOT EXISTS idx_sw_forward_targets_org_provider
    ON social_wiring.portal_lead_forward_targets (org_id, provider)
    WHERE is_active = true;

-- ─── The outbox ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS social_wiring.portal_lead_forwards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    target_id       UUID NOT NULL REFERENCES social_wiring.portal_lead_forward_targets(id) ON DELETE CASCADE,

    provider        TEXT NOT NULL CHECK (provider IN ('olx', 'imovelweb')),

    -- The vendor's lead id. Together with `target_id` it is what makes
    -- enqueue idempotent: the receiver is called more than once for the
    -- same lead by design (retries, 14-day store-and-forward), and each
    -- of those must not add a second forward.
    origin_lead_id  TEXT NOT NULL,

    -- The vendor's request body. On the live receive path these are the
    -- bytes Grupo OLX actually sent, carried down from the router: the
    -- downstream CRM is entitled to any field we do not model yet, and a
    -- round-trip through our parser would quietly drop it.
    --
    -- On the scheduler drain path the body is re-serialised from the
    -- stored payload — semantically identical JSON, not byte-identical.
    -- Stated rather than glossed, because "verbatim" is a claim someone
    -- will one day rely on.
    --
    -- 🔴 CONTAINS PII (name, email, phone, free-text message). NULLed on
    -- success by the drain — see `delivered_at` below.
    body            TEXT,

    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'delivered', 'failed', 'dead')),

    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    last_status_code INTEGER,
    last_error       TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at    TIMESTAMPTZ,

    -- One forward per lead per destination. This is the idempotency key,
    -- and it is a CONSTRAINT rather than a check-then-insert because the
    -- receiver can be called concurrently for the same originLeadId and
    -- a read-then-write would race.
    UNIQUE (target_id, origin_lead_id)
);

-- The drain's only query: due work, oldest first. Partial so the index
-- stays small — the steady state is an empty set.
CREATE INDEX IF NOT EXISTS idx_sw_portal_lead_forwards_due
    ON social_wiring.portal_lead_forwards (next_attempt_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_sw_portal_lead_forwards_org
    ON social_wiring.portal_lead_forwards (org_id, created_at DESC);

-- ─── RLS ──────────────────────────────────────────────────────────────

ALTER TABLE social_wiring.portal_lead_forward_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.portal_lead_forwards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "portal_lead_forward_targets_select_own_org"
    ON social_wiring.portal_lead_forward_targets;
CREATE POLICY "portal_lead_forward_targets_select_own_org"
    ON social_wiring.portal_lead_forward_targets
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

DROP POLICY IF EXISTS "portal_lead_forward_targets_write_own_org_admin"
    ON social_wiring.portal_lead_forward_targets;
CREATE POLICY "portal_lead_forward_targets_write_own_org_admin"
    ON social_wiring.portal_lead_forward_targets
    FOR ALL TO authenticated
    USING (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = social_wiring.portal_lead_forward_targets.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    )
    WITH CHECK (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = social_wiring.portal_lead_forward_targets.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

-- Read-only for org members: the outbox is an operator health surface,
-- not something a user edits. Only the drain (service-role) writes.
DROP POLICY IF EXISTS "portal_lead_forwards_select_own_org"
    ON social_wiring.portal_lead_forwards;
CREATE POLICY "portal_lead_forwards_select_own_org"
    ON social_wiring.portal_lead_forwards
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- The receiver enqueues and the drain delivers, both before any org
-- context exists — service-role, with the literal `service_role_bypass`
-- name the keeper `check_admin_endpoint_service_role_bypass` matches.
DROP POLICY IF EXISTS "portal_lead_forward_targets_service_role_bypass"
    ON social_wiring.portal_lead_forward_targets;
CREATE POLICY "portal_lead_forward_targets_service_role_bypass"
    ON social_wiring.portal_lead_forward_targets
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "portal_lead_forwards_service_role_bypass"
    ON social_wiring.portal_lead_forwards;
CREATE POLICY "portal_lead_forwards_service_role_bypass"
    ON social_wiring.portal_lead_forwards
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.portal_lead_forwards IS
    'Store-and-forward outbox for inbound portal leads. Durable because '
    'Grupo OLX considers a lead delivered once we answer 2xx and never '
    'resends: a failed forward is a lead the downstream CRM never gets. '
    '`body` holds vendor PII and is NULLed on successful delivery.';

COMMENT ON COLUMN social_wiring.portal_lead_forwards.body IS
    'Vendor request body VERBATIM (contains PII). NULLed by the drain once '
    'status=delivered — the row is kept because (target_id, origin_lead_id) '
    'is the idempotency key and deleting it would let a redelivery re-forward.';
