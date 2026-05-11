-- AdConnect: align `resgates_recompensa` with `RedemptionOut` schema
-- Phase R3 of `response-model-silent-drop-audit` follow-up — Option A: extend
-- the table to match the schema's intended shape (2026-05-11).
--
-- The audit (`projects/response-model-silent-drop-audit/PROJECT.md` §4 #1)
-- surfaced that `RedemptionOut` declares 9 fields not present in the table:
--   org_id, tipo, valor, pedido_ref, review_notes, reviewed_by,
--   reviewed_at, paid_at, requested_at.
--
-- Per the migration prelude convention (`feedback_migration_prelude_helpers`),
-- this ALTER uses the seed-lib `prelude("adconnect")` schema-lock. No new
-- updated_at trigger is required — the existing table doesn't track
-- updated_at (status transitions stamp `reviewed_at` / `paid_at` /
-- `processed_at` directly).

-- ============================================================================
-- AdConnect migration — schema-locked to `adconnect`
-- ============================================================================
SET search_path = adconnect, public;

ALTER TABLE adconnect.resgates_recompensa
    -- Brand-scoping (mirrors other adconnect tables; backfilled from the
    -- distributor's org_id at row-write time by `request_redemption` route).
    ADD COLUMN IF NOT EXISTS org_id UUID,
    -- Schema-declared category: cashback vs marketing budget. Existing
    -- rows default to 'cashback' (the historical sole use case).
    ADD COLUMN IF NOT EXISTS tipo TEXT
        CHECK (tipo IS NULL OR tipo IN ('cashback', 'verba_mkt')),
    -- Single-line redemption value (the schema models a single amount;
    -- existing `valor_total` stays as the canonical aggregate for the
    -- multi-source case the migration shipped with).
    ADD COLUMN IF NOT EXISTS valor NUMERIC(12, 2),
    -- Pedido cross-reference (FK omitted: the schema's intent is a free-form
    -- caller-supplied string; tighten to FK in a follow-up if needed).
    ADD COLUMN IF NOT EXISTS pedido_ref TEXT,
    -- Brand-admin review notes (separate from the requester's `observacoes`).
    ADD COLUMN IF NOT EXISTS review_notes TEXT,
    -- Reviewer audit fields.
    ADD COLUMN IF NOT EXISTS reviewed_by UUID,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    -- Stamped when status flips to 'pago'.
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ,
    -- Stamped at row creation by the route (distinct from `created_at`
    -- which is the DB-default insert time; `requested_at` is the
    -- caller's intended "request happened" timestamp).
    ADD COLUMN IF NOT EXISTS requested_at TIMESTAMPTZ;

-- Index supports the brand-admin "list redemptions for my org" query path.
CREATE INDEX IF NOT EXISTS idx_adconnect_resgates_org
    ON adconnect.resgates_recompensa(org_id)
    WHERE org_id IS NOT NULL;
