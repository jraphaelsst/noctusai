-- ============================================================================
-- 238 — clientes.email: the house provenance quintet
-- ============================================================================
-- WHY: a ficha cadastral prints each party's e-mail (the contract's signature
-- block needs it: derivacao.py PARTE_SEM_EMAIL), but nothing wrote it to
-- `clientes.email` (live e2e, 2026-10-10). The ficha apply now fills it
-- through the SAME D1 path as every other extracted field (fill empty
-- machine-pending; a different value is a conflict, never an overwrite), and
-- that path needs the quintet, like migration 193 gave the pacto columns.
-- `clientes.email` itself exists since 048/088. FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — apply via `noctus.dev.migrate_product`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS email_origem TEXT,
    ADD COLUMN IF NOT EXISTS email_documento_id UUID,
    ADD COLUMN IF NOT EXISTS email_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS email_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS email_confirmado_em TIMESTAMPTZ;

NOTIFY pgrst, 'reload schema';
