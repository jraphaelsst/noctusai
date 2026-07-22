-- 028_leads_edited_at_and_batch_diagnostics.sql — never silently
-- overwrite a human's manual lead edit on re-import; surface skip
-- reasons in the import batch record.
--
-- THE PROBLEM THIS FIXES
-- ───────────────────────
-- `importer.import_service.commit`'s update branch writes the FULL
-- field set derived from the spreadsheet onto an already-existing lead
-- (matched by `(org_id, source_sheet, source_row)`). If a human has
-- since corrected that lead via `PATCH /api/leads/{id}` (fixed the
-- name, reassigned the corretor, cleared `needs_review`), a later
-- re-import (a new month's sheet is added and the importer walks EVERY
-- sheet again, not just the new one; or the same workbook is
-- re-uploaded after a spreadsheet correction) silently REVERTS every
-- one of those edits back to the spreadsheet values, with no warning
-- and no diff — `rows_updated` just goes up. This is the only finding
-- in this fixes batch that destroys data outright.
--
-- THE FIX
-- ───────
-- `leads.edited_at` — stamped by `leads_service.update_lead` on every
-- real PATCH (any field, including a bare `needs_review` toggle — see
-- that function's docstring). `import_service.commit` now checks it
-- before ever overwriting an existing row: `edited_at IS NOT NULL` ->
-- skip the update entirely, count it as both `rows_skipped` (the
-- existing counter) AND the new `rows_skipped_edited` (so the UI can
-- show "N preserved because manually edited" distinctly from "N
-- skipped, unparseable date"). `lead_import_batches.warnings` persists
-- the per-run reviewable message list (unparseable-date skips from
-- `xlsx_reader.parse_sheet`, previously computed but discarded by
-- `commit` — see that module's docstring) so it survives past the
-- single HTTP response and is visible on `GET /api/leads/import/batches`.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.
-- Forward-only + idempotent (ADD COLUMN IF NOT EXISTS).

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;

-- Two separate statements (not one comma-separated ALTER) — the
-- migration-schema-cache parser (`noctusai_lib.testing.migration_parser`)
-- matches one `ADD COLUMN` per `ALTER TABLE ... ADD COLUMN` occurrence;
-- keeping each column its own statement is the portable shape.
ALTER TABLE social_wiring.lead_import_batches
    ADD COLUMN IF NOT EXISTS rows_skipped_edited INTEGER NOT NULL DEFAULT 0;

ALTER TABLE social_wiring.lead_import_batches
    ADD COLUMN IF NOT EXISTS warnings TEXT[] NOT NULL DEFAULT '{}';
