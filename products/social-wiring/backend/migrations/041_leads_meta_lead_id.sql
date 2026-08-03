-- 041_leads_meta_lead_id.sql — idempotency key for the Meta Lead-Ads ->
-- unified-leads ingest (roadmap `meta-ads-console-2026-07`, Slice 3).
--
-- WHY THIS EXISTS
-- ────────────────
-- `app/modules/leads/services/meta_ingest_service.py` maps a
-- `social_wiring.meta_ads_leads` row (the lossless raw ledger, migration
-- 033) onto a `social_wiring.leads` row (the one base with origem /
-- corretor / analytics every other lead already lives in). That mapping
-- runs from a per-lead webhook call AND a one-off bulk backfill of the
-- rows synced before the mapping existed — both must be safe to re-run
-- without ever producing a second `leads` row for the same Meta lead.
--
-- `leads` already has exactly this shape for the spreadsheet importer:
-- `UNIQUE (org_id, source_sheet, source_row) WHERE source_sheet IS NOT
-- NULL` (migration 025). This column/index is the same idea for the
-- Meta path — Meta's own lead id (`meta_ads_leads.id`, globally unique,
-- TEXT) becomes the natural re-run key, scoped by org for the same
-- reason every other dimension on this table is: a shared lead id
-- across two orgs must never collide.
--
-- NO NEW TABLE, NO NEW RLS POLICY
-- ────────────────────────────────
-- This is a column on an EXISTING table. `leads_select_own_org` /
-- `leads_service_role` (migration 025) are table-level policies — they
-- already cover every column, including this one, with no additional
-- grant. Inventing a new policy here would be exactly the un-asked-for
-- policy the tech-lead's correction on this brief warned against.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.
-- Forward-only + idempotent (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF
-- NOT EXISTS).

SET search_path = social_wiring, public;

-- One column, its own ALTER TABLE statement — the migration-schema-cache
-- parser (`noctusai_lib.testing.migration_parser`) matches one
-- `ADD COLUMN` per `ALTER TABLE ... ADD COLUMN` occurrence (see migration
-- 028's header for the same convention).
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS meta_lead_id TEXT;

COMMENT ON COLUMN social_wiring.leads.meta_lead_id IS
    'Meta''s own lead id (social_wiring.meta_ads_leads.id) when this row '
    'was ingested from a Meta Lead-Ads (Instant Form) submission via '
    'app/modules/leads/services/meta_ingest_service.py. NULL for every '
    'other lead source (spreadsheet import, manual entry). Re-running the '
    'ingest for the same Meta lead is a no-op guarded by '
    'uq_sw_leads_org_meta_lead_id, not an application-side check alone.';

-- Idempotency key for the ingest: unique WHEN PRESENT, mirroring
-- `uq_sw_leads_org_sheet_row`'s partial-index shape exactly — manually
-- created leads and spreadsheet-imported leads (`meta_lead_id IS NULL`)
-- are exempt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_meta_lead_id
    ON social_wiring.leads (org_id, meta_lead_id)
    WHERE meta_lead_id IS NOT NULL;

-- PostgREST must re-read the schema to see the new column.
NOTIFY pgrst, 'reload schema';
