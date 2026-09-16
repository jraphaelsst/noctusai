-- ============================================================================
-- 046_permissions_fx_cost_ledger — Core platform tables for edicao-fotos R1
-- ============================================================================
--
-- Renumbered from the approved plan's "045" — `045_academia_agents_live_
-- scope.sql` landed on `origin/dev` first and is a HELD file belonging to
-- noctusai-36's consent-gated cutover (deliberately UNAPPLIED). See
-- `projects/edicao-fotos/PROJECT.md` §C3/§C9. This migration is
-- independent of that one; only the NUMBER moved.
--
-- Three platform-wide (not product-scoped) tables, all living at `public`
-- per Core's existing convention (no dedicated schema; see
-- `products/core/backend/app/main.py` `schema="public"`):
--
--   1. `public.user_permission_grants` + `public.has_permission()` — the
--      product-agnostic named-permission seam. First consumer is the
--      `photo_curator` grant (edicao-fotos), but this table/RPC carries no
--      product coupling — shape verified byte-for-byte against
--      `noctusai_lib.domain.permissions.repo.
--      RealSupabasePermissionGrantRepository`'s docstring (S6, this
--      project's Wave 1).
--   2. `public.fx_rates` — persisted BCB PTAX venda/fechamento bulletins.
--      Shape mirrors `noctusai_lib.integrations.fx.types.PtaxRate`
--      (S4, this project's Wave 1) — `rate` NUMERIC (never FLOAT — this is
--      money), `quote_date` the bulletin's REAL trading day (may be
--      earlier than requested — BCB publishes no weekend/holiday
--      bulletin), `bulletin_at` the full timestamp, `source` for
--      audit/debugging. `pair` is forward-looking (v1 is USD/BRL only,
--      per `PtaxRate`'s docstring) so a future non-USD pair never needs a
--      migration.
--   3. `public.cost_ledger` — native-currency cost rows (OpenAI edits +
--      vision, Supabase storage, payment fees) with an explicit
--      `fx_pending` state instead of a silent fallback conversion. Per
--      the plan §5/§6: "the `LLM_USD_TO_BRL=5.0` default is never used
--      silently" — a foreign-currency row is either fully resolved
--      (fx_rate + fx_quote_date + amount_brl all present) or explicitly
--      `fx_pending = true` (amount_brl/fx_rate left NULL until the
--      `fotos.fx_backfill` job resolves it against `fx_rates`). The CHECK
--      constraint below makes the half-resolved state impossible to
--      insert, not just discouraged by convention.
--
-- No `orgs` table exists in Core's schema to FK against (organizations are
-- resolved via `public.noctus_users.org_id`, not a normalized orgs table —
-- verified: no `CREATE TABLE public.orgs` anywhere in this migrations/).
-- `cost_ledger.org_id` is therefore a bare UUID, matching every other
-- org-scoped table in this codebase (e.g. `social_wiring.cliente_
-- documentos.org_id`).
--
-- FORWARD-ONLY. MIGRATION FILE ONLY — not applied to any database by this
-- change. Applying needs owner consent (`projects/edicao-fotos/PROJECT.md`
-- §5, item 1).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. user_permission_grants + has_permission()
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.user_permission_grants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    permission  TEXT NOT NULL,
    granted_by  UUID REFERENCES auth.users (id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, permission)
);

CREATE INDEX IF NOT EXISTS ix_user_permission_grants_permission
    ON public.user_permission_grants (permission);

-- `has_permission` — SQL function (not plpgsql), STABLE, SECURITY DEFINER
-- so it reads regardless of the caller's own RLS visibility. Shape is
-- byte-for-byte the one documented in
-- `noctusai_lib.domain.permissions.repo.RealSupabasePermissionGrantRepository`.
CREATE OR REPLACE FUNCTION public.has_permission(
    p_user_id UUID,
    p_permission TEXT
) RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.user_permission_grants
        WHERE user_id = p_user_id AND permission = p_permission
    );
$$;

ALTER TABLE public.user_permission_grants ENABLE ROW LEVEL SECURITY;

-- A user may see their own grants (e.g. an FE capabilities check); nobody
-- may see another user's grants except the platform admin. Issuance
-- (INSERT/UPDATE/DELETE) is a LATER slice's admin router — ships nothing
-- beyond SELECT + service_role here, same "ship nothing until a consumer
-- needs it" stance as `domain/jobs/migrations/jobs.sql.template`.
CREATE POLICY "user_permission_grants_select_own" ON public.user_permission_grants
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "user_permission_grants_select_platform_admin" ON public.user_permission_grants
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON public.user_permission_grants
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE public.user_permission_grants IS
    'Product-agnostic named-permission grants (e.g. photo_curator). See noctusai_lib.domain.permissions.';

-- ----------------------------------------------------------------------------
-- 2. fx_rates — persisted BCB PTAX venda/fechamento bulletins
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.fx_rates (
    id           BIGSERIAL PRIMARY KEY,
    pair         TEXT NOT NULL DEFAULT 'USD/BRL',
    quote_date   DATE NOT NULL,
    rate         NUMERIC(12, 5) NOT NULL CHECK (rate > 0),
    bulletin_at  TIMESTAMPTZ NOT NULL,
    source       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pair, quote_date)
);

CREATE INDEX IF NOT EXISTS ix_fx_rates_pair_quote_date
    ON public.fx_rates (pair, quote_date DESC);

ALTER TABLE public.fx_rates ENABLE ROW LEVEL SECURITY;

-- Exchange rates are not sensitive — readable platform-wide. Writes are
-- service_role only (the `fotos.fx_backfill` job / a future PTAX-sweep
-- scheduler), matching the "no authenticated write policy" shape used by
-- `fx_rates`' sibling tables in this file.
CREATE POLICY "fx_rates_select_authenticated" ON public.fx_rates
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY "service_role_bypass" ON public.fx_rates
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE public.fx_rates IS
    'Persisted BCB PTAX venda/fechamento bulletins. Written by service_role only. See noctusai_lib.integrations.fx.';

-- ----------------------------------------------------------------------------
-- 3. cost_ledger — native-currency cost rows with explicit fx_pending state
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.cost_ledger (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID NOT NULL,
    category        TEXT NOT NULL,     -- 'openai_edit' | 'openai_vision' | 'supabase_storage' | 'payment_fee' | ...
    step            TEXT,              -- pipeline step name, e.g. 'fotos.edit' (opaque, caller-defined)
    reference_type  TEXT,              -- e.g. 'llm_usage' — what `reference_id` points at
    reference_id    TEXT,              -- id in the referenced table/system; opaque, no FK (cross-schema)
    amount_native   NUMERIC(14, 6) NOT NULL,
    currency        TEXT NOT NULL,     -- ISO 4217, e.g. 'USD' | 'BRL'
    fx_rate         NUMERIC(12, 5),
    fx_quote_date   DATE,
    amount_brl      NUMERIC(14, 6),
    fx_pending      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A BRL-native row is its own conversion (amount_brl = amount_native,
    -- never pending). A foreign-currency row is EITHER fully resolved
    -- (fx_rate + fx_quote_date + amount_brl all present, fx_pending
    -- false) OR explicitly pending (all three NULL, fx_pending true) —
    -- the half-resolved state (e.g. amount_brl set but fx_rate NULL) is
    -- structurally impossible, not merely discouraged.
    CHECK (
        (currency = 'BRL' AND fx_pending = false AND amount_brl = amount_native
            AND fx_rate IS NULL AND fx_quote_date IS NULL)
        OR (currency <> 'BRL' AND fx_pending = true
            AND amount_brl IS NULL AND fx_rate IS NULL AND fx_quote_date IS NULL)
        OR (currency <> 'BRL' AND fx_pending = false
            AND amount_brl IS NOT NULL AND fx_rate IS NOT NULL AND fx_quote_date IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_cost_ledger_org_created
    ON public.cost_ledger (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_cost_ledger_category
    ON public.cost_ledger (category);
-- The `fotos.fx_backfill` job's read path: every unresolved row.
CREATE INDEX IF NOT EXISTS ix_cost_ledger_fx_pending
    ON public.cost_ledger (fx_pending)
    WHERE fx_pending = true;

ALTER TABLE public.cost_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY "cost_ledger_select_own_org" ON public.cost_ledger
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "cost_ledger_select_platform_admin" ON public.cost_ledger
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON public.cost_ledger
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE public.cost_ledger IS
    'Native-currency cost rows (OpenAI, storage, payment fees) with explicit fx_pending state. Never falls back to a silent USD/BRL default.';
