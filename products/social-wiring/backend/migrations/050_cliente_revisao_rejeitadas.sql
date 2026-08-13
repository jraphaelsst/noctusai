-- ============================================================================
-- Migration 050 -- (renumbered from 049 by the tech-lead: 049 was already
--   taken by 049_imoveis_place_name_collision_fix.sql, authored in a parallel
--   worktree and APPLIED before this slice landed. The pre-commit collision
--   check never fired because this work was staged, not committed.)
-- Migration 050 -- social_wiring: durable "manter separados" marker for the
-- `clientes` review queue.
--
-- lead-card-hub Phase 1 (contract `products/social-wiring/projects/
-- lead-card-hub-p1-PROJECT.md` §5), Slice B (routers). Slice A's `048`
-- created `clientes` / `cliente_touches` / `cliente_merges` but has no
-- column or table recording an operator's decision to KEEP a review
-- group's candidates separate (`POST /api/clientes/revisao/{grupo}/
-- manter-separados`). Slice A's own delivery note flags this explicitly:
-- "The review-queue's 'keep separate' outcome has no durable 'don't
-- resurface' marker in my schema ... flagged for Slice B / the tech-lead
-- to decide." Without one, `clientes_service.list_review_groups`
-- (untouched by this file -- see `app/routers/clientes_router.py`, which
-- filters its output against this table instead) would re-surface a
-- rejected group on every single page load, forever -- exactly the
-- "un-walkable queue" contract §5 calls the Phase 1 checkpoint failure.
--
-- WHY A NEW TABLE, NOT A COLUMN ON `clientes`
-- ---------------------------------------------
-- A review group is keyed by `chave_canonica`, shared across the group's
-- N candidate `clientes` rows (2 for C4/C5, 3+ for C6). A "keep separate"
-- decision is a property of the GROUP, not of any one candidate -- a
-- `clientes` column would need writing N times per decision, and has no
-- home for a group whose candidate set later changes (a new straggler
-- lands under the same key -- see `clientes_service.py`'s reconciliation
-- note). One row per (org_id, chave_canonica) here is authoritative for
-- the whole group and is looked up the same way `list_review_groups`
-- finds its groups: through the shared key, not through any one
-- candidate's row id.
--
-- WHY A NEW MIGRATION FILE, NOT AN EDIT TO 048
-- ------------------------------------------------
-- `048` is Slice A's file and its application is a separate, pending
-- human decision (contract §7) this migration does not touch or alter.
-- Like `048`, this file is ALSO unapplied to any database; it ships as
-- DDL only, purely additive, and forward-only (CREATE ... IF NOT
-- EXISTS), so it changes the go/no-go conversation not at all -- it is
-- one more file in the same pending batch, not a new decision point.
--
-- FORWARD-ONLY, IDEMPOTENT, matching every migration in this product.
-- 🔴 MIGRATION FILE ONLY -- not applied to any database by this change.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.cliente_revisao_rejeitadas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    -- The review group's identifying key -- the SAME value
    -- `cliente_touches.chave_canonica` carries and the `{grupo}` path
    -- segment in `POST /api/clientes/revisao/{grupo}/manter-separados`
    -- names. Deliberately NOT a foreign key to `clientes.chave_canonica`:
    -- every candidate's OWN `chave_canonica` is NULL by `048`'s design
    -- (see its header's "UNIQUE constraint also shapes how review groups
    -- are stored" section) -- this column stores the REAL shared key
    -- the candidates only ever hold on their `cliente_touches` rows.
    chave_canonica  TEXT NOT NULL,
    -- Recorded for audit only, at the classification current when the
    -- operator rejected the group. Not re-derived, not load-bearing for
    -- the "don't resurface" behaviour (that's the row's mere existence).
    motivo          TEXT CHECK (motivo IN ('C4', 'C5', 'C6')),
    rejeitado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One decision per (org, key) -- rejecting the same group twice is a
-- no-op (the router checks-then-inserts), never a second row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_revisao_rejeitadas_org_chave
    ON social_wiring.cliente_revisao_rejeitadas (org_id, chave_canonica);

ALTER TABLE social_wiring.cliente_revisao_rejeitadas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_revisao_rejeitadas_select_own_org" ON social_wiring.cliente_revisao_rejeitadas;
CREATE POLICY "cliente_revisao_rejeitadas_select_own_org" ON social_wiring.cliente_revisao_rejeitadas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_revisao_rejeitadas_service_role" ON social_wiring.cliente_revisao_rejeitadas;
CREATE POLICY "cliente_revisao_rejeitadas_service_role" ON social_wiring.cliente_revisao_rejeitadas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
