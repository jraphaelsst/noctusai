-- ============================================================================
-- Migration 058 -- social_wiring: D16, the 180-day inactivity rule.
--
-- lead-card-hub roadmap (`project-history/roadmaps/lead-card-hub-2026-08.md`)
-- D16: "Inactivity threshold: 180 days, configurable in the UI." P1.5 shipped
-- only the manual half -- `048` gave `clientes` its `ativo` / `inativo_em` /
-- `arquivado_em` columns and the router lets an operator flip them by hand,
-- but nothing ever SETS `inativo_em` automatically, and no threshold is
-- stored anywhere. This migration adds the two things the automatic sweep
-- (`app/services/clientes_inactivity_service.py`) needs that `048` didn't
-- anticipate:
--
--   1. `clientes_inactivity_config` -- one row per org, the configurable
--      threshold D16 asks for. A per-org table, NOT a reuse of
--      `app_integration_config` (022): that store is documented, in its own
--      migration header and in `noctusai_lib.security.app_config`'s module
--      docstring, as "single row per config KEY (not per-org)" -- it holds
--      ONE Meta App credential pair for the whole deployment, never a
--      per-tenant value. Namespacing a per-org key into that Fernet-
--      encrypted table would (a) violate its documented contract, (b)
--      encrypt a non-secret integer for no reason, and (c) give this table
--      no natural place to enforce `threshold_days >= 0`. A dedicated,
--      RLS-scoped, org_id-keyed table is the correct extension of "this
--      product's per-org config" -- it mirrors `clientes`/`clients`'
--      already-established `org_id`-keyed-row convention, not a new one.
--
--      threshold_days semantics (made explicit here so it is never an
--      accident): NO ROW for an org -> the org has never configured a
--      value -> the sweep uses the platform default (180,
--      `settings.clientes_inactivity_threshold_days_default`). A row WITH
--      threshold_days = 0 -> the org explicitly disabled the sweep. These
--      are deliberately different states -- collapsing "unconfigured" and
--      "disabled" into the same signal would make "reset to default" and
--      "turn off forever" indistinguishable at the API layer.
--
--   2. Two new `clientes` columns the sweep and its counterpart (reactivation
--      on a new touch) need, neither of which `048` had a reason to add:
--
--      - `reativado_em` -- set whenever a cliente the SWEEP had put to
--        sleep becomes active again, either because a human restored it by
--        hand (`PATCH /api/clientes/{id}` with `ativo=true`) or because a
--        fresh `cliente_touches` row attached to it
--        (`clientes_service._attach_touches` -> `_reactivate_if_inactive`).
--        This is what makes "manual restore wins" durable: the sweep's
--        silence computation is `GREATEST(ultimo_contato_em, reativado_em)`,
--        not `ultimo_contato_em` alone -- so a restored cliente whose most
--        recent REAL touch is still 200 days old does not get swept right
--        back to inactive on the very next tick just because nothing new
--        actually happened. See `clientes_inactivity_service.py`'s module
--        docstring for the full state table.
--      - `inativo_threshold_dias` -- the threshold that ACTUALLY applied
--        when the sweep flagged this specific cliente inactive, snapshotted
--        at that moment rather than re-read from the org's CURRENT config.
--        Org config can change after the fact (D16 requirement: it's
--        editable); if a card only ever showed "inactive since <inativo_em>"
--        next to today's config value, changing the org's threshold later
--        would silently rewrite the history of every already-inactive card.
--        Cleared back to NULL alongside `inativo_em` on any reactivation.
--
-- Neither addition changes existing behaviour: both columns default to
-- NULL, every existing `clientes` row already has `ativo = true` with both
-- new columns unset, so nothing already stored is reinterpreted.
--
-- FORWARD-ONLY, IDEMPOTENT (CREATE ... IF NOT EXISTS / ADD COLUMN IF NOT
-- EXISTS), matching every migration in this product. 🔴 MIGRATION FILE
-- ONLY -- not applied to any database by this change. Apply via
-- `noctus.dev.migrate_product` only with explicit tech-lead/user
-- go-ahead, same as every migration in this file's neighbourhood.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes -- the sweep's own bookkeeping columns
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS reativado_em TIMESTAMPTZ;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS inativo_threshold_dias INTEGER;

COMMENT ON COLUMN social_wiring.clientes.reativado_em IS
    'Set on manual restore (PATCH ativo=true) or automatic reactivation '
    '(a new touch lands on a sweep-inactivated cliente). The sweep''s '
    'silence check reads GREATEST(ultimo_contato_em, reativado_em) so a '
    'restore is not immediately undone by the next scheduled tick. Never '
    'set for a MANUALLY archived cliente (arquivado_em IS NOT NULL) -- '
    'that is a deliberate human decision the sweep/reactivation path does '
    'not override.';

COMMENT ON COLUMN social_wiring.clientes.inativo_threshold_dias IS
    'The threshold_days value the sweep actually used when it set '
    'inativo_em on THIS row -- a snapshot, not a live read of the org''s '
    'current clientes_inactivity_config, so a later config change does '
    'not rewrite the stated reason for a past inactivation. NULL unless '
    'ativo = false AND inativo_em IS NOT NULL (i.e. auto-swept, not '
    'manually archived).';

-- ----------------------------------------------------------------------------
-- 2. clientes_inactivity_config -- the per-org, configurable threshold (D16)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.clientes_inactivity_config (
    org_id          UUID PRIMARY KEY,
    -- 0 = sweep explicitly disabled for this org. No row at all = never
    -- configured, sweep falls back to the platform default (180). See
    -- the header for why these are kept distinct.
    threshold_days  INTEGER NOT NULL DEFAULT 180 CHECK (threshold_days >= 0),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.clientes_inactivity_config ENABLE ROW LEVEL SECURITY;

-- Admin-only, same RLS shape as `app_integration_config` (022): this table
-- is never read directly via PostgREST from an authenticated end-user
-- session, only through the admin-gated `GET/PUT /api/settings/
-- clientes-inactivity` endpoints (`app/routers/settings_router.py`), which
-- both resolve through `get_admin_client()` -- the same client the sweep
-- itself uses. No `authenticated` policy is intentional, not an omission.
DROP POLICY IF EXISTS "clientes_inactivity_config_service_role" ON social_wiring.clientes_inactivity_config;
CREATE POLICY "clientes_inactivity_config_service_role" ON social_wiring.clientes_inactivity_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
