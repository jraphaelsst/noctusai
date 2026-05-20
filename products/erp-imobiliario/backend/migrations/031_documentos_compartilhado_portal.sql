-- ============================================================================
-- 031_documentos_compartilhado_portal.sql — Portal-cliente sharing gate (LGPD)
-- ============================================================================
--
-- Adds `erp.documentos.compartilhado_portal boolean NOT NULL DEFAULT FALSE`
-- as the LGPD-aligned per-document sharing flag for the public bearer-token
-- portal endpoint `GET /api/portal/{portal_token}/documentos`.
--
-- Why this migration exists. `app/routers/portal_externo.py:portal_documentos`
-- returns ALL `erp.documentos` rows for a portal-cliente bearer token, filtered
-- only by `org_id + cliente_id`. Documents carry CPF, contract scans, ID
-- copies, sensitive financial annexes — LGPD Art. 5 + Art. 11 surface. ERP-P6
-- (erp-wiring Phase 6) audit surfaced this as the highest-severity item in
-- that batch. The fix is gated on a per-document share flag; this migration
-- ships the column the production filter consumes.
--
-- Backfill policy decision (architect, 2026-05-20): default FALSE — safer-by-
-- default; cliente explicitly authorizes sharing per-document via admin
-- toggle. Risk: portal users lose immediate access until admin marks docs.
-- Mitigation: surface a one-time admin alert post-deploy (FE wave). The
-- alternative (default TRUE preserving current behavior) was rejected on
-- LGPD grounds — Art. 7 §3 + Art. 18 (cliente has data-subject right to know
-- exposure history); a leaky default plus opt-out runs counter to the
-- minimum-necessary-data principle.
--
-- Audit-log coverage (architect, 2026-05-20): every portal-side READ +
-- every admin-side toggle logged via `log_action()` per Art. 18. Adds rows
-- to `erp.user_actions_log` with `tipo_entidade='documento_portal_acesso'`
-- (portal-side reads) and `tipo_entidade='documento_compartilhamento'`
-- (admin-side toggles). No schema change required for the audit log itself
-- (existing table absorbs both shapes).
--
-- Backwards compatibility. Existing migrations `001_erp_imobiliario.sql:1656`
-- and `004_mvp_expansion.sql:282` define `erp.documentos` without this
-- column. The test fixture in `test_portal_externo_router.py:TestPortalDocumentos`
-- already sets `compartilhado_portal: True` on rows — the test contract was
-- ahead of the production schema. This migration aligns the schema to the
-- test contract; the parallel router/test changes in this dispatch align
-- the production code path to consume it.
-- ============================================================================

SET search_path = erp, public;

ALTER TABLE erp.documentos
  ADD COLUMN IF NOT EXISTS compartilhado_portal boolean NOT NULL DEFAULT false;

-- Index supports the hot portal-cliente read path:
--   SELECT ... FROM erp.documentos
--    WHERE org_id = ? AND cliente_id = ? AND compartilhado_portal = true
-- Partial index on TRUE only (sharing is opt-in; most rows stay FALSE post-
-- deploy until admin reviews).
CREATE INDEX IF NOT EXISTS idx_documentos_compartilhado_portal
  ON erp.documentos (org_id, cliente_id)
  WHERE compartilhado_portal = true;
