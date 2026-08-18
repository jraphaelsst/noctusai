-- 053_portal_receiver_tokens.sql
--
-- Per-advertiser receiver tokens for inbound portal-lead webhooks.
--
-- WHY THIS TABLE EXISTS AT ALL, given `social_wiring.api_tokens` already
-- resolves an opaque token to an org:
--
--   `api_tokens` rows are BEARER credentials. Nothing in the seed
--   (`noctusai_lib.api.auth.session`) or in this backend consults
--   `AuthContext.scopes` for authorization — the field is populated at
--   resolve time and read by nobody — so a `pk_*` token is an
--   all-or-nothing org-scoped API credential.
--
--   A receiver token does not live in an Authorization header. It lives
--   in a URL that the advertiser pastes into Canal Pro, which means it is
--   stored in Grupo OLX's database, rendered in their web UI, kept in
--   browser history, and written to vendor-side request logs. Minting
--   that as an `api_tokens` row would hand full product-caller API access
--   to every one of those surfaces.
--
--   So: same shape, deliberately different table, because the exposure
--   profile is different. This is NOT a candidate for a later "DRY these
--   two together" refactor. `KB § PATTERNS/common/accept-with-rationale.md`.
--
-- WHY `provider`, and not an `olx_` table: ImovelWeb (direct OpenNavent,
-- parked on `feat/imovelweb-portal-leads`) needs exactly this, and so does
-- any portal after it. A per-portal token table is the "per-product X"
-- language slip that replication-to-seed-symmetry names — the right count
-- is one table, N providers.
--
-- MIGRATION NUMBER: 052 is deliberately skipped. It is taken by
-- `052_imovelweb_portal_leads.sql` on the parked `feat/imovelweb-portal-leads`
-- branch (15 commits, unpushed as of 2026-08-18). Taking 053 lets that
-- branch merge without renumbering.
--
-- Additive: one new table. No existing object is altered.
--
-- Apply to the noctusai Supabase (social_wiring schema) at deploy.

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.portal_receiver_tokens (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    -- The provider whose receiver this token routes. Values match the
    -- `integration_accounts.provider` vocabulary so the two surfaces
    -- cannot drift into different spellings of the same portal.
    provider      TEXT NOT NULL CHECK (provider IN ('olx', 'imovelweb')),

    -- SHA-256 hex of the URL path segment, never the segment itself.
    -- Storing the plaintext would put a live routing credential in
    -- database backups and in every operator's psql scrollback.
    token_hash    TEXT NOT NULL UNIQUE,

    -- First 8 chars of the plaintext, for display only ("…ends in 3f2a"
    -- style identification in the UI and in logs). Not a secret, and not
    -- enough to reconstruct the token.
    token_prefix  TEXT NOT NULL,

    label         TEXT NOT NULL,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,

    -- Bumped best-effort on every resolved delivery. The operator card
    -- reads it to answer "is this URL actually receiving anything?", which
    -- is the question a silent misconfiguration otherwise hides.
    last_seen_at  TIMESTAMPTZ,

    revoked_at    TIMESTAMPTZ
);

-- MORE THAN ONE ACTIVE TOKEN PER (org, provider) IS INTENTIONAL, and the
-- reason there is no partial-unique index forbidding it: switching the URL
-- in Canal Pro is not atomic. Rotation is issue-new → paste-new → confirm
-- traffic moved → revoke-old, and a uniqueness constraint would make the
-- overlap window impossible, forcing a revoke-then-paste order that drops
-- every lead in between. Grupo OLX does not replay those.
CREATE INDEX IF NOT EXISTS idx_sw_portal_receiver_tokens_org_provider
    ON social_wiring.portal_receiver_tokens (org_id, provider)
    WHERE revoked_at IS NULL;

ALTER TABLE social_wiring.portal_receiver_tokens ENABLE ROW LEVEL SECURITY;

-- Org-scoped read for authenticated members. `token_hash` is a digest, so
-- exposing the row does not expose the token; the plaintext is returned
-- exactly once, at mint time, and never stored.
DROP POLICY IF EXISTS "portal_receiver_tokens_select_own_org"
    ON social_wiring.portal_receiver_tokens;
CREATE POLICY "portal_receiver_tokens_select_own_org"
    ON social_wiring.portal_receiver_tokens
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

-- Mint + revoke are owner/admin only — the same bar `api_tokens` sets for
-- the same reason: a token minted here routes real customer PII.
DROP POLICY IF EXISTS "portal_receiver_tokens_insert_own_org_admin"
    ON social_wiring.portal_receiver_tokens;
CREATE POLICY "portal_receiver_tokens_insert_own_org_admin"
    ON social_wiring.portal_receiver_tokens
    FOR INSERT TO authenticated
    WITH CHECK (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = social_wiring.portal_receiver_tokens.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

DROP POLICY IF EXISTS "portal_receiver_tokens_update_own_org_admin"
    ON social_wiring.portal_receiver_tokens;
CREATE POLICY "portal_receiver_tokens_update_own_org_admin"
    ON social_wiring.portal_receiver_tokens
    FOR UPDATE TO authenticated
    USING (
        org_id = current_org_id()
        AND EXISTS (
            SELECT 1 FROM public.noctus_users nu
            WHERE nu.id = (SELECT auth.uid())
              AND nu.org_id = social_wiring.portal_receiver_tokens.org_id
              AND nu.org_role IN ('owner', 'admin')
        )
    );

-- The receiver resolves tokens BEFORE any org context exists — resolution
-- IS the tenant-identification step — so it runs on the service-role
-- client and needs an explicit bypass policy.
--
-- Named with the literal string `service_role_bypass`: the keeper
-- `check_admin_endpoint_service_role_bypass` matches that literal, and
-- 051's `olx_lead_events_service_role` / `olx_leads_service_role` are
-- invisible to it for exactly that reason (finding carried from
-- `feat/imovelweb-portal-leads`, still open against 051).
DROP POLICY IF EXISTS "portal_receiver_tokens_service_role_bypass"
    ON social_wiring.portal_receiver_tokens;
CREATE POLICY "portal_receiver_tokens_service_role_bypass"
    ON social_wiring.portal_receiver_tokens
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE social_wiring.portal_receiver_tokens IS
    'Per-advertiser opaque tokens embedded in inbound portal-lead webhook '
    'URLs. Deliberately NOT api_tokens rows: these live in vendor-visible '
    'URLs, and api_tokens are bearer credentials whose scopes nothing '
    'enforces. See the header of migration 053 for the full rationale.';

COMMENT ON COLUMN social_wiring.portal_receiver_tokens.token_hash IS
    'SHA-256 hex of the URL path segment. The plaintext is shown once at '
    'mint time and never stored.';
