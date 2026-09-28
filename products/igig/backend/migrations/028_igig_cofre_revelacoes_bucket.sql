-- ============================================================================
-- IgIg — migration 028: the `igig` storage bucket, at last, and a persisted
-- Cofre reveal audit trail.
--
--   1. STORAGE BUCKET `igig` — peças and logos have written through this
--      bucket (`app/storage.py`, `Settings.igig_storage_bucket`, default
--      "igig") since migration 008, but no migration ever created the bucket
--      row itself; production has relied on someone clicking it into
--      existence by hand in the dashboard (00-plataforma achado #16). Unlike
--      `igig-cardhub` (migration 019), `igig` carries NO authenticated
--      `storage.objects` policies — every read/write goes through the
--      backend's SERVICE-ROLE client (`app/storage.py::get_storage` ->
--      `get_admin_client()`), so this migration only needs the bucket row.
--   2. `igig.cofre_revelacoes` — the Cofre's "who revealed this password and
--      when" used to live ONLY in a `logger.info` line
--      (`routers/marca_router.py::revelar_senha`). A log line rotates off
--      disk and answers no query; this is the durable audit row the Cofre's
--      own module docstring already promised ("Cada revelação fica
--      registrada"). Append-only by convention (no UPDATE/DELETE path in the
--      app) — no `updated_at` column.
--   3. `igig.apontamento.duracao_segundos` — the timer used to floor to whole
--      MINUTES per segment (achado 22), so three 40-second sessions recorded
--      0+0+0 = zero minutes instead of the 2 they actually add up to.
--      `minutos` stays (existing readers keep working unchanged); the new
--      column is the precise value `minutos_da_tarefa` now sums BEFORE
--      converting to minutes, so sub-minute sessions are no longer silently
--      discarded from the custo real / DRE input.
--
-- SQLite mirror: migrations/sqlite/028_igig_cofre_revelacoes_bucket.sql
-- (parity-tested by tests/test_schema_parity.py).
-- ============================================================================
SET search_path = igig, public;

INSERT INTO storage.buckets (id, name, public)
VALUES ('igig', 'igig', false)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS igig.cofre_revelacoes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    acesso_id    UUID NOT NULL REFERENCES igig.acesso (id) ON DELETE CASCADE,
    -- Nullable: `public.noctus_users` lives in another schema core owns, and
    -- IgIg's migrations must not FK across that boundary (same reasoning as
    -- `profissional.usuario_id`, migration 008).
    revelado_por UUID,
    revelado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The seam's generic `insert()` stamps `created_at` on every row
    -- (`RecordStore` convention, mirrored by every other igig table) —
    -- kept even though `revelado_em` is the field the app actually reads.
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_igig_cofre_revelacoes_org ON igig.cofre_revelacoes (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_cofre_revelacoes_acesso
    ON igig.cofre_revelacoes (org_id, acesso_id, revelado_em DESC);

ALTER TABLE igig.cofre_revelacoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cofre_revelacoes_org_isolation ON igig.cofre_revelacoes;
CREATE POLICY cofre_revelacoes_org_isolation ON igig.cofre_revelacoes FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id()))
    WITH CHECK (org_id = (SELECT public.current_org_id()));
DROP POLICY IF EXISTS cofre_revelacoes_service_role ON igig.cofre_revelacoes;
CREATE POLICY cofre_revelacoes_service_role ON igig.cofre_revelacoes FOR ALL TO service_role
    USING (true) WITH CHECK (true);

ALTER TABLE igig.apontamento ADD COLUMN IF NOT EXISTS duracao_segundos INTEGER;
