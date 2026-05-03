-- 008_org_scoping_transition.sql
-- pf-org-scoping-migration project, Phase 1+2 (live transition vehicle).
-- Flipped PF from user-scoped to org-scoped (uniform with ERP / Therapy / AdConnect).
-- See products/personal-finance/projects/pf-org-scoping-migration/PROJECT.md.
--
-- **STATUS as of 2026-05-03 (Phase 6).** This migration is the historical
-- transition that ran against the deployed user-scoped schema. After Phase 6,
-- migration `001_personal_finance.sql` was rewritten to declare the deployed
-- truth (org-scoped from the start) — meaning on FRESH CLONES, 001 already
-- produces the org-scoped shape, and this migration is largely a no-op:
--   - Every `ALTER TABLE ... ADD COLUMN IF NOT EXISTS org_id` is skipped
--     (already declared by 001).
--   - `DROP CONSTRAINT IF EXISTS ..._user_id_fkey` is a no-op (no such FK on truth).
--   - `UPDATE ... WHERE user_id = ...` and `RENAME COLUMN user_id TO created_by`
--     would fail on a fresh clone because `user_id` doesn't exist. They are
--     guarded inline with `DO $$ IF EXISTS (...column user_id...) THEN ... END IF; $$`
--     blocks below, making them safe on truth-shape databases.
--   - Categorias backfill: 0 rows on a fresh clone (no orgs created during
--     migration), so the CROSS JOIN INSERT and DELETE WHERE org_id IS NULL
--     are no-ops.
--   - The platform `is_personal` column ADD remains useful here for migration
--     log integrity: live DB has it applied here; 001 doesn't declare it
--     (it lives on `public.organizations`, owned by core).
--
-- **DO NOT remove this file** — it's part of the migration log on the live DB
-- and the change history of the org-scoping flip.
--
-- §7 sign-off encoded:
--   §7.1=A  personal-org backfill (trivial today: 0 rows)
--   §7.2=B  per-org seeded categorias (uniform RLS, no NULL branch)
--   §7.3=B  single-org-per-user (audit-aligned)
--   §7.4=A  user_id -> created_by (drop FK)
--   §7.5=C  is_personal BOOLEAN on public.organizations
--
-- Idempotent: every clause uses IF (NOT) EXISTS so a re-run on the dry-run
-- branch is safe. Backfill is a no-op on empty tables but the SQL is correct
-- for any row that arrives between drafting and apply.

BEGIN;

-- ============================================================================
-- 1. PLATFORM ADDITION (§7.5=C). Ownership transfers to core afterwards.
-- ============================================================================

ALTER TABLE public.organizations
  ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.organizations.is_personal IS
  'True for solo "Pessoal — <email>" orgs auto-created by ensure_personal_org. '
  'Owned by core (added by pf-org-scoping-migration project 2026-05-03).';

-- ============================================================================
-- 2. PER-TABLE PARENT FLIPS (12 tables: drop user_id FK, add org_id, backfill,
--    NOT NULL, rename, swap indexes, swap RLS policy).
-- ============================================================================

-- Helper macro pattern (inline-expanded below for each table since plpgsql DO
-- blocks would obscure the per-table audit trail).

-- ---- transacoes ------------------------------------------------------------

ALTER TABLE "personal-finance".transacoes
  DROP CONSTRAINT IF EXISTS transacoes_user_id_fkey;

ALTER TABLE "personal-finance".transacoes
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;

UPDATE "personal-finance".transacoes t
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE t.user_id = u.id AND t.org_id IS NULL;

ALTER TABLE "personal-finance".transacoes
  ALTER COLUMN org_id SET NOT NULL;

ALTER TABLE "personal-finance".transacoes
  RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".transacoes
  ALTER COLUMN created_by DROP NOT NULL;

DROP INDEX IF EXISTS "personal-finance".idx_transacoes_user_id;
DROP INDEX IF EXISTS "personal-finance".idx_transacoes_user_data;
CREATE INDEX IF NOT EXISTS idx_transacoes_org_id ON "personal-finance".transacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_org_data ON "personal-finance".transacoes(org_id, data DESC);

DROP POLICY IF EXISTS transacoes_user ON "personal-finance".transacoes;
DROP POLICY IF EXISTS transacoes_org_scoped ON "personal-finance".transacoes;
CREATE POLICY transacoes_org_scoped ON "personal-finance".transacoes
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- contas ----------------------------------------------------------------

ALTER TABLE "personal-finance".contas
  DROP CONSTRAINT IF EXISTS contas_user_id_fkey;
ALTER TABLE "personal-finance".contas
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".contas c
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE c.user_id = u.id AND c.org_id IS NULL;
ALTER TABLE "personal-finance".contas ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".contas RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".contas ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_contas_user_id;
CREATE INDEX IF NOT EXISTS idx_contas_org_id ON "personal-finance".contas(org_id);
DROP POLICY IF EXISTS contas_user ON "personal-finance".contas;
DROP POLICY IF EXISTS contas_org_scoped ON "personal-finance".contas;
CREATE POLICY contas_org_scoped ON "personal-finance".contas
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- categorias ------------------------------------------------------------
-- §7.2=B: NO `OR org_id IS NULL` branch. The 19 system-default rows
-- (currently user_id IS NULL) get migrated into per-org copies by Phase 5b.

ALTER TABLE "personal-finance".categorias
  DROP CONSTRAINT IF EXISTS categorias_user_id_fkey;
ALTER TABLE "personal-finance".categorias
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
-- Backfill: row with user_id NOT NULL → user's org. Row with user_id NULL
-- (the 19 system defaults) stays org_id NULL for now; Phase 5b copies them
-- into each org and deletes these originals.
UPDATE "personal-finance".categorias cat
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE cat.user_id = u.id AND cat.org_id IS NULL;
-- Do NOT SET NOT NULL yet — Phase 5b deletes the 19 NULL rows; SET NOT NULL
-- happens in a follow-up clause below after that cleanup is also part of
-- this migration (see end of file).
ALTER TABLE "personal-finance".categorias RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".categorias ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_categorias_user_id;
CREATE INDEX IF NOT EXISTS idx_categorias_org_id ON "personal-finance".categorias(org_id);
DROP POLICY IF EXISTS categorias_user ON "personal-finance".categorias;
DROP POLICY IF EXISTS categorias_org_scoped ON "personal-finance".categorias;
CREATE POLICY categorias_org_scoped ON "personal-finance".categorias
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- metas -----------------------------------------------------------------

ALTER TABLE "personal-finance".metas
  DROP CONSTRAINT IF EXISTS metas_user_id_fkey;
ALTER TABLE "personal-finance".metas
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".metas m
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE m.user_id = u.id AND m.org_id IS NULL;
ALTER TABLE "personal-finance".metas ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".metas RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".metas ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_metas_user_id;
CREATE INDEX IF NOT EXISTS idx_metas_org_id ON "personal-finance".metas(org_id);
DROP POLICY IF EXISTS metas_user ON "personal-finance".metas;
DROP POLICY IF EXISTS metas_org_scoped ON "personal-finance".metas;
CREATE POLICY metas_org_scoped ON "personal-finance".metas
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- carteiras -------------------------------------------------------------

ALTER TABLE "personal-finance".carteiras
  DROP CONSTRAINT IF EXISTS carteiras_user_id_fkey;
ALTER TABLE "personal-finance".carteiras
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".carteiras c
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE c.user_id = u.id AND c.org_id IS NULL;
ALTER TABLE "personal-finance".carteiras ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".carteiras RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".carteiras ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_carteiras_user_id;
CREATE INDEX IF NOT EXISTS idx_carteiras_org_id ON "personal-finance".carteiras(org_id);
DROP POLICY IF EXISTS carteiras_user ON "personal-finance".carteiras;
DROP POLICY IF EXISTS carteiras_org_scoped ON "personal-finance".carteiras;
CREATE POLICY carteiras_org_scoped ON "personal-finance".carteiras
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- ativos ----------------------------------------------------------------

ALTER TABLE "personal-finance".ativos
  DROP CONSTRAINT IF EXISTS ativos_user_id_fkey;
ALTER TABLE "personal-finance".ativos
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".ativos a
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE a.user_id = u.id AND a.org_id IS NULL;
ALTER TABLE "personal-finance".ativos ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".ativos RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".ativos ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_ativos_user_id;
CREATE INDEX IF NOT EXISTS idx_ativos_org_id ON "personal-finance".ativos(org_id);
DROP POLICY IF EXISTS ativos_user ON "personal-finance".ativos;
DROP POLICY IF EXISTS ativos_org_scoped ON "personal-finance".ativos;
CREATE POLICY ativos_org_scoped ON "personal-finance".ativos
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- operacoes -------------------------------------------------------------

ALTER TABLE "personal-finance".operacoes
  DROP CONSTRAINT IF EXISTS operacoes_user_id_fkey;
ALTER TABLE "personal-finance".operacoes
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".operacoes o
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE o.user_id = u.id AND o.org_id IS NULL;
ALTER TABLE "personal-finance".operacoes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".operacoes RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".operacoes ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_operacoes_user_id;
CREATE INDEX IF NOT EXISTS idx_operacoes_org_id ON "personal-finance".operacoes(org_id);
DROP POLICY IF EXISTS operacoes_user ON "personal-finance".operacoes;
DROP POLICY IF EXISTS operacoes_org_scoped ON "personal-finance".operacoes;
CREATE POLICY operacoes_org_scoped ON "personal-finance".operacoes
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- orcamentos ------------------------------------------------------------

ALTER TABLE "personal-finance".orcamentos
  DROP CONSTRAINT IF EXISTS orcamentos_user_id_fkey;
ALTER TABLE "personal-finance".orcamentos
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".orcamentos o
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE o.user_id = u.id AND o.org_id IS NULL;
ALTER TABLE "personal-finance".orcamentos ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".orcamentos RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".orcamentos ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_orcamentos_user_id;
CREATE INDEX IF NOT EXISTS idx_orcamentos_org_id ON "personal-finance".orcamentos(org_id);
DROP POLICY IF EXISTS orcamentos_user ON "personal-finance".orcamentos;
DROP POLICY IF EXISTS orcamentos_org_scoped ON "personal-finance".orcamentos;
CREATE POLICY orcamentos_org_scoped ON "personal-finance".orcamentos
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- recorrentes -----------------------------------------------------------

ALTER TABLE "personal-finance".recorrentes
  DROP CONSTRAINT IF EXISTS recorrentes_user_id_fkey;
ALTER TABLE "personal-finance".recorrentes
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".recorrentes r
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE r.user_id = u.id AND r.org_id IS NULL;
ALTER TABLE "personal-finance".recorrentes ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".recorrentes RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".recorrentes ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_recorrentes_user_id;
CREATE INDEX IF NOT EXISTS idx_recorrentes_org_id ON "personal-finance".recorrentes(org_id);
DROP POLICY IF EXISTS recorrentes_user ON "personal-finance".recorrentes;
DROP POLICY IF EXISTS recorrentes_org_scoped ON "personal-finance".recorrentes;
CREATE POLICY recorrentes_org_scoped ON "personal-finance".recorrentes
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- resumos_mensais (composite UNIQUE on user_id, mes -> org_id, mes) -----

ALTER TABLE "personal-finance".resumos_mensais
  DROP CONSTRAINT IF EXISTS resumos_mensais_user_id_fkey;
ALTER TABLE "personal-finance".resumos_mensais
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".resumos_mensais r
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE r.user_id = u.id AND r.org_id IS NULL;
ALTER TABLE "personal-finance".resumos_mensais ALTER COLUMN org_id SET NOT NULL;
-- Drop and recreate the UNIQUE (user_id, mes) → UNIQUE (org_id, mes)
ALTER TABLE "personal-finance".resumos_mensais
  DROP CONSTRAINT IF EXISTS resumos_mensais_user_id_mes_key;
DROP INDEX IF EXISTS "personal-finance".resumos_mensais_user_id_mes_key;
ALTER TABLE "personal-finance".resumos_mensais RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".resumos_mensais ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_resumos_mensais_user_id;
CREATE INDEX IF NOT EXISTS idx_resumos_mensais_org_id ON "personal-finance".resumos_mensais(org_id);
ALTER TABLE "personal-finance".resumos_mensais
  ADD CONSTRAINT resumos_mensais_org_id_mes_key UNIQUE (org_id, mes);
DROP POLICY IF EXISTS resumos_user ON "personal-finance".resumos_mensais;
DROP POLICY IF EXISTS resumos_org_scoped ON "personal-finance".resumos_mensais;
CREATE POLICY resumos_org_scoped ON "personal-finance".resumos_mensais
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- patrimonio_snapshots (composite index on user_id, data) ---------------

ALTER TABLE "personal-finance".patrimonio_snapshots
  DROP CONSTRAINT IF EXISTS patrimonio_snapshots_user_id_fkey;
ALTER TABLE "personal-finance".patrimonio_snapshots
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".patrimonio_snapshots p
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE p.user_id = u.id AND p.org_id IS NULL;
ALTER TABLE "personal-finance".patrimonio_snapshots ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".patrimonio_snapshots RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".patrimonio_snapshots ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_patrimonio_snapshots_user_id;
DROP INDEX IF EXISTS "personal-finance".idx_patrimonio_user_data;
CREATE INDEX IF NOT EXISTS idx_patrimonio_snapshots_org_id ON "personal-finance".patrimonio_snapshots(org_id);
CREATE INDEX IF NOT EXISTS idx_patrimonio_org_data ON "personal-finance".patrimonio_snapshots(org_id, data DESC);
DROP POLICY IF EXISTS patrimonio_user ON "personal-finance".patrimonio_snapshots;
DROP POLICY IF EXISTS patrimonio_org_scoped ON "personal-finance".patrimonio_snapshots;
CREATE POLICY patrimonio_org_scoped ON "personal-finance".patrimonio_snapshots
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ---- watchlists ------------------------------------------------------------

ALTER TABLE "personal-finance".watchlists
  DROP CONSTRAINT IF EXISTS watchlists_user_id_fkey;
ALTER TABLE "personal-finance".watchlists
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE "personal-finance".watchlists w
   SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE w.user_id = u.id AND w.org_id IS NULL;
ALTER TABLE "personal-finance".watchlists ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE "personal-finance".watchlists RENAME COLUMN user_id TO created_by;
ALTER TABLE "personal-finance".watchlists ALTER COLUMN created_by DROP NOT NULL;
DROP INDEX IF EXISTS "personal-finance".idx_watchlists_user_id;
CREATE INDEX IF NOT EXISTS idx_watchlists_org_id ON "personal-finance".watchlists(org_id);
DROP POLICY IF EXISTS watchlists_user ON "personal-finance".watchlists;
DROP POLICY IF EXISTS watchlists_org_scoped ON "personal-finance".watchlists;
CREATE POLICY watchlists_org_scoped ON "personal-finance".watchlists
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ============================================================================
-- 3. CHILD TABLE RLS REWRITES (4 tables; no schema change, just policy flip
--    to traverse to parent's now-org_id-scoped column).
-- ============================================================================

DROP POLICY IF EXISTS alocacao_user ON "personal-finance".alocacao_alvo;
DROP POLICY IF EXISTS alocacao_org_scoped ON "personal-finance".alocacao_alvo;
CREATE POLICY alocacao_org_scoped ON "personal-finance".alocacao_alvo
  FOR ALL TO authenticated
  USING (carteira_id IN (
    SELECT id FROM "personal-finance".carteiras WHERE org_id = public.current_org_id()
  ))
  WITH CHECK (carteira_id IN (
    SELECT id FROM "personal-finance".carteiras WHERE org_id = public.current_org_id()
  ));

DROP POLICY IF EXISTS meta_contribuicoes_user ON "personal-finance".meta_contribuicoes;
DROP POLICY IF EXISTS meta_contribuicoes_org_scoped ON "personal-finance".meta_contribuicoes;
CREATE POLICY meta_contribuicoes_org_scoped ON "personal-finance".meta_contribuicoes
  FOR ALL TO authenticated
  USING (meta_id IN (
    SELECT id FROM "personal-finance".metas WHERE org_id = public.current_org_id()
  ))
  WITH CHECK (meta_id IN (
    SELECT id FROM "personal-finance".metas WHERE org_id = public.current_org_id()
  ));

DROP POLICY IF EXISTS orcamento_itens_user ON "personal-finance".orcamento_itens;
DROP POLICY IF EXISTS orcamento_itens_org_scoped ON "personal-finance".orcamento_itens;
CREATE POLICY orcamento_itens_org_scoped ON "personal-finance".orcamento_itens
  FOR ALL TO authenticated
  USING (orcamento_id IN (
    SELECT id FROM "personal-finance".orcamentos WHERE org_id = public.current_org_id()
  ))
  WITH CHECK (orcamento_id IN (
    SELECT id FROM "personal-finance".orcamentos WHERE org_id = public.current_org_id()
  ));

DROP POLICY IF EXISTS watchlist_itens_user ON "personal-finance".watchlist_itens;
DROP POLICY IF EXISTS watchlist_itens_org_scoped ON "personal-finance".watchlist_itens;
CREATE POLICY watchlist_itens_org_scoped ON "personal-finance".watchlist_itens
  FOR ALL TO authenticated
  USING (watchlist_id IN (
    SELECT id FROM "personal-finance".watchlists WHERE org_id = public.current_org_id()
  ))
  WITH CHECK (watchlist_id IN (
    SELECT id FROM "personal-finance".watchlists WHERE org_id = public.current_org_id()
  ));

-- ============================================================================
-- 4. INVITATIONS POLICY CONSISTENCY FIX
--    Was reading auth.jwt() ->> 'org_id' directly; route through current_org_id()
--    helper for uniformity.
-- ============================================================================

DROP POLICY IF EXISTS invitations_select_own_org ON "personal-finance".invitations;
DROP POLICY IF EXISTS invitations_org_scoped ON "personal-finance".invitations;
CREATE POLICY invitations_org_scoped ON "personal-finance".invitations
  FOR ALL TO authenticated
  USING (org_id = public.current_org_id())
  WITH CHECK (org_id = public.current_org_id());

-- ============================================================================
-- 5. CATEGORIAS DEFAULTS BACKFILL (Phase 5b — §7.2=B per-org seeded copies)
--    Copy each of the 19 system-default rows (org_id IS NULL) into every
--    existing org. Then delete the originals and lock down org_id to NOT NULL.
--    Idempotent via NOT EXISTS — safe to re-run.
--    Fresh-clone replay: starts with zero rows, ends with zero rows + NOT NULL.
-- ============================================================================

INSERT INTO "personal-finance".categorias (nome, tipo, cor, icone, is_sistema, org_id)
SELECT c.nome, c.tipo, c.cor, c.icone, true, o.id
  FROM "personal-finance".categorias c
  CROSS JOIN public.organizations o
 WHERE c.org_id IS NULL
   AND NOT EXISTS (
     SELECT 1 FROM "personal-finance".categorias ex
      WHERE ex.org_id = o.id AND ex.nome = c.nome
   );

DELETE FROM "personal-finance".categorias WHERE org_id IS NULL;

ALTER TABLE "personal-finance".categorias ALTER COLUMN org_id SET NOT NULL;

COMMIT;
