-- ============================================================================
-- Migration 023 — Extend audit-log enums for the Vista CRM showcase
-- ============================================================================
-- Purpose
--   The `vista-crm-wiring` project (Phase 2) writes one row to
--   `erp.user_actions_log` per outbound Vista API call so admin access to
--   external CRM personal data is auditable (LGPD requirement — see
--   `products/erp-imobiliario/projects/vista-crm-wiring/PROJECT.md` § 5).
--
--   Existing `erp.tipo_acao` / `erp.tipo_entidade` enums don't have values
--   that fit "external integration lookup" — using the existing 'criar' /
--   'cliente' would lie about what happened. This migration adds two new
--   enum values.
--
-- Idempotency
--   `ADD VALUE IF NOT EXISTS` lets the migration replay safely.
-- ============================================================================

ALTER TYPE erp.tipo_acao ADD VALUE IF NOT EXISTS 'consulta_externa';
ALTER TYPE erp.tipo_entidade ADD VALUE IF NOT EXISTS 'integracao_vista';
