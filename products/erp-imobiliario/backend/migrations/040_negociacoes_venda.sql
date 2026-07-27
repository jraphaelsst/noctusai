-- ============================================================================
-- Migration 040 -- erp.negociacoes_venda: negociação as a first-class entity
--
-- WHY THIS EXISTS
-- ---------------
-- The Funil board groups `erp.clientes` by `clientes.etapa_atual`, so a
-- cliente holds exactly ONE stage. The user requires MULTIPLE CONCURRENT DEALS
-- per cliente (roadmap `project-history/roadmaps/erp-processos-venda-2026-07.md`,
-- decision log 2026-07-16), which that shape structurally cannot represent.
-- Funil cards must therefore become NEGOCIAÇÕES, not clientes.
--
-- `erp.negociacoes` CANNOT serve: it is the PERMUTA (property-swap) table
-- (ativo_origem_id + ativo_destino_id + cliente_proprietario_id +
-- cliente_ofertante_id + valor_permuta) -- no single cliente_id, every row
-- demands two properties and two parties. This is a SIBLING entity; the
-- permuta table is untouched. The similar naming is a known readability
-- hazard, flagged in the roadmap anti-goals.
--
-- WHAT IT DOES
--   1. `erp.status_negociacao_venda` enum -- the terminal-state vocabulary
--      (roadmap Q2: cycle-time statistics need a real closed state, not
--      "absent from the board").
--   2. `erp.negociacoes_venda` table + RLS + indexes.
--   3. The seeded "Agência" profile -- the default corretor for an
--      unassigned deal (roadmap Q7).
--   4. Widens `erp.clientes` INSERT RLS so the agency default is actually
--      insertable (see AGENCY DEFAULT ⇄ RLS COLLISION below).
--   5. `erp.funil_movimentos.negociacao_venda_id` -- the stage-transition
--      log becomes negociação-grained (roadmap P1.5.3).
--   6. Zero-loss backfill: every existing `clientes` row gets EXACTLY ONE
--      negociação carrying its current etapa/valores/kanban_pos.
--
-- MIGRATION ORDERING HAZARD (roadmap, explicit)
--   `clientes.etapa_atual` stops being the source of truth but is NOT dropped
--   here -- it stays written-but-ignored for one release so a rollback has
--   somewhere to land. Removal is its own later slice.
--
-- AGENCY DEFAULT ⇄ RLS COLLISION (discovered against the live schema)
--   `erp.clientes`'s INSERT policy is `WITH CHECK (auth.uid() = usuario_id)`.
--   Defaulting an unassigned cliente to the agency profile would therefore be
--   REFUSED by RLS for every non-admin corretor -- the decided behavior and
--   the live policy are in direct conflict. Step 4 widens that policy to also
--   admit the agency sentinel. Nothing else about the policy changes.
--
-- 🔴 SINGLE-AGENCY / MULTI-ORG CAVEAT -- READ BEFORE EXTENDING
--   This seeds ONE global agency profile with `org_id IS NULL`, not one per
--   org. That is coherent with TODAY's schema and no wider than it:
--   `erp.clientes` carries NO org_id and its RLS is
--   `has_role(uid,'admin') OR uid = usuario_id` -- i.e. clientes are ALREADY
--   cross-org for any admin (pre-existing; migration 039 names
--   `erp.clientes` as out-of-scope for the org fan-out and defers it to an
--   `erp-rls-org-scope-redesign` follow-up). `negociacoes_venda` deliberately
--   mirrors its parent's scoping rather than inventing tighter-but-false
--   guarantees (roadmap anti-goal: "No org_id on a child table unless
--   erp.clientes gets one" -- a child scoped tighter than its parent is a
--   false guarantee).
--   WHEN `erp.clientes` GAINS `org_id`, this agency singleton must become
--   per-org in the SAME slice, or unassigned deals will pool across tenants.
--
-- IDEMPOTENT: IF NOT EXISTS / ON CONFLICT DO NOTHING / DROP POLICY IF EXISTS
-- throughout. Safe to re-run.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Status enum (roadmap Q2 -- RESOLVED: a real terminal state + closed_at)
-- ----------------------------------------------------------------------------
-- `aberta`  -- live on the Funil board
-- `aceita`  -- proposal accepted; execution moved to Processos de Venda
-- `perdida` -- deal lost; off the board, retained for conversion statistics
--
-- A separate enum from the permuta table's `erp.status_negociacao`. An ENUM
-- (not a CHECK constraint) because a CHECK blocks adding a value later
-- without a table rewrite, while `ALTER TYPE ... ADD VALUE` does not.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'status_negociacao_venda' AND n.nspname = 'erp'
  ) THEN
    CREATE TYPE erp.status_negociacao_venda AS ENUM ('aberta', 'aceita', 'perdida');
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- 2. The seeded "Agência" profile (roadmap Q7 -- RESOLVED)
-- ----------------------------------------------------------------------------
-- `erp.profiles.id` is an FK to `auth.users(id)`, so the agency needs a real
-- auth.users row. It is a SYNTHETIC NON-LOGIN identity: no password, no
-- confirmed email, never issued a token. Deterministic UUID so every
-- environment (and every re-run) resolves the same row.
--
-- The profile row itself is created by the EXISTING `on_auth_user_created`
-- trigger (`public.handle_new_user`, migration 025), which reads
-- `raw_user_meta_data->>'nome'` and `NEW.email` -- both are supplied below
-- because `erp.profiles.nome`/`email`/`telefone` are NOT NULL. We deliberately
-- do NOT insert the profile directly: duplicating the trigger's job is how the
-- two drift apart.
INSERT INTO auth.users (id, email, raw_user_meta_data)
VALUES (
  '00000000-0000-0000-0000-0000000a6e0c',
  'agencia@sistema.interno',
  '{"nome": "Agência", "telefone": ""}'::jsonb
)
ON CONFLICT (id) DO NOTHING;

-- Backstop: if the trigger were ever absent/altered, the profile still exists.
-- `ON CONFLICT DO NOTHING` makes this a no-op in the normal (trigger-ran) path.
INSERT INTO erp.profiles (id, nome, email, telefone)
VALUES (
  '00000000-0000-0000-0000-0000000a6e0c',
  'Agência',
  'agencia@sistema.interno',
  ''
)
ON CONFLICT (id) DO NOTHING;

-- Resolver so application code and RLS never hardcode the UUID twice.
CREATE OR REPLACE FUNCTION erp.agency_profile_id()
  RETURNS uuid
  LANGUAGE sql
  IMMUTABLE
  SET search_path TO 'erp', 'public'
AS $$ SELECT '00000000-0000-0000-0000-0000000a6e0c'::uuid $$;

-- ----------------------------------------------------------------------------
-- 3. erp.negociacoes_venda
-- ----------------------------------------------------------------------------
-- `etapa` REUSES `erp.etapa_funil` (roadmap Q5 -- RESOLVED: lean reuse until
-- the two boards' stage vocabularies genuinely diverge; a parallel enum would
-- duplicate five values on day one).
CREATE TABLE IF NOT EXISTS erp.negociacoes_venda (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES erp.clientes(id) ON DELETE CASCADE,
  corretor_id UUID NOT NULL REFERENCES erp.profiles(id) DEFAULT erp.agency_profile_id(),
  titulo TEXT,
  etapa erp.etapa_funil NOT NULL DEFAULT 'qualificacao',
  status erp.status_negociacao_venda NOT NULL DEFAULT 'aberta',
  valor_estimado NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_estimado >= 0),
  probabilidade INTEGER NOT NULL DEFAULT 10 CHECK (probabilidade >= 0 AND probabilidade <= 100),
  kanban_pos INTEGER NOT NULL DEFAULT 0,
  arquivado BOOLEAN NOT NULL DEFAULT false,
  -- Set when `status` leaves 'aberta'. The cycle-time substrate: without it
  -- "absent from the board" is the only record and duration is unknowable.
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- A closed deal must carry its close timestamp, and an open one must not.
  -- Enforced here so a partial UPDATE cannot silently produce a deal that is
  -- 'aceita' with no closed_at (which would read as duration zero in stats).
  CONSTRAINT negociacoes_venda_closed_at_matches_status CHECK (
    (status = 'aberta' AND closed_at IS NULL)
    OR (status <> 'aberta' AND closed_at IS NOT NULL)
  )
);

-- The board query: open, unarchived deals grouped by etapa, ordered by position.
CREATE INDEX IF NOT EXISTS idx_negociacoes_venda_board
  ON erp.negociacoes_venda (etapa, kanban_pos)
  WHERE status = 'aberta' AND arquivado = false;
CREATE INDEX IF NOT EXISTS idx_negociacoes_venda_cliente
  ON erp.negociacoes_venda (cliente_id);
CREATE INDEX IF NOT EXISTS idx_negociacoes_venda_corretor
  ON erp.negociacoes_venda (corretor_id);

DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON erp.negociacoes_venda;
CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON erp.negociacoes_venda
  FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

ALTER TABLE erp.negociacoes_venda ENABLE ROW LEVEL SECURITY;

-- RLS mirrors `erp.clientes` exactly (admin OR owning corretor) -- deliberately
-- the SAME shape as the parent, so a negociação is never visible to someone who
-- cannot see its cliente, and never hidden from someone who can.
DROP POLICY IF EXISTS "negociacoes_venda_select" ON erp.negociacoes_venda;
CREATE POLICY "negociacoes_venda_select" ON erp.negociacoes_venda
  FOR SELECT TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
  );

-- INSERT admits the agency sentinel in addition to self-ownership: an
-- unassigned deal is a legitimate creation, not a privilege escalation (the
-- agency identity can never log in, so nothing is granted to a caller).
DROP POLICY IF EXISTS "negociacoes_venda_insert" ON erp.negociacoes_venda;
CREATE POLICY "negociacoes_venda_insert" ON erp.negociacoes_venda
  FOR INSERT TO authenticated
  WITH CHECK (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
    OR corretor_id = erp.agency_profile_id()
  );

DROP POLICY IF EXISTS "negociacoes_venda_update" ON erp.negociacoes_venda;
CREATE POLICY "negociacoes_venda_update" ON erp.negociacoes_venda
  FOR UPDATE TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
  );

DROP POLICY IF EXISTS "negociacoes_venda_delete" ON erp.negociacoes_venda;
CREATE POLICY "negociacoes_venda_delete" ON erp.negociacoes_venda
  FOR DELETE TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
  );

DROP POLICY IF EXISTS "service_role_bypass" ON erp.negociacoes_venda;
CREATE POLICY "service_role_bypass" ON erp.negociacoes_venda
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. Widen erp.clientes INSERT RLS for the agency default
-- ----------------------------------------------------------------------------
-- See AGENCY DEFAULT ⇄ RLS COLLISION in the header. Same policy name, same
-- action, same role grant -- the predicate gains exactly one alternative.
DROP POLICY IF EXISTS "Usuários podem criar seus próprios clientes" ON erp.clientes;
CREATE POLICY "Usuários podem criar seus próprios clientes" ON erp.clientes
  FOR INSERT TO authenticated
  WITH CHECK (
    (SELECT auth.uid()) = usuario_id
    OR usuario_id = erp.agency_profile_id()
  );

-- ----------------------------------------------------------------------------
-- 5. Stage-transition log becomes negociação-grained (roadmap P1.5.3)
-- ----------------------------------------------------------------------------
-- REUSES `erp.funil_movimentos` rather than spawning a sibling table: it
-- already carries (de_etapa, para_etapa, responsavel_id, created_at) + RLS +
-- indexes, and the roadmap left "new table or reuse" open. Reuse wins -- a
-- second history table would fork the funnel's audit trail in two.
--
-- NOTE on the pre-existing gap (roadmap trigger T3): `mover_etapa` never wrote
-- to this table at all. The application side of that is fixed in this slice's
-- router change; this column is what makes the row attributable to a DEAL
-- rather than only to a cliente.
--
-- Nullable: rows predating this migration have no negociação, and cliente-level
-- movements remain representable. Not backfilled -- there are no existing rows
-- to attribute (verified against the live DB), and inventing an attribution
-- would be fabricated history.
ALTER TABLE erp.funil_movimentos
  ADD COLUMN IF NOT EXISTS negociacao_venda_id UUID
  REFERENCES erp.negociacoes_venda(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_funil_movimentos_negociacao
  ON erp.funil_movimentos (negociacao_venda_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 6. Zero-loss backfill -- every cliente gets EXACTLY ONE negociação
-- ----------------------------------------------------------------------------
-- The whole gate for this phase: post-migration, a cliente with one deal must
-- render and behave identically to today's board. Carries etapa_atual,
-- valores, kanban_pos and arquivado across verbatim.
--
-- `WHERE NOT EXISTS` (not ON CONFLICT) because there is no unique constraint on
-- cliente_id -- multiple deals per cliente is the entire point. Re-running must
-- not mint a second negociação for an already-backfilled cliente, and must not
-- suppress genuine additional deals created later.
--
-- `fechado` maps to status 'aberta', NOT 'aceita': `fechado` is a Funil-INTERNAL
-- terminal column (roadmap decision log 2026-07-16 -- the user's correction).
-- Acceptance is a separate, explicit act via the Processos seam; inferring it
-- here would fabricate accepted deals and spawn processos nobody created.
INSERT INTO erp.negociacoes_venda (
  cliente_id, corretor_id, etapa, valor_estimado, probabilidade,
  kanban_pos, arquivado, created_at
)
SELECT
  c.id, c.usuario_id, c.etapa_atual, c.valor_estimado, c.probabilidade,
  c.kanban_pos, c.arquivado, c.created_at
FROM erp.clientes c
WHERE NOT EXISTS (
  SELECT 1 FROM erp.negociacoes_venda nv WHERE nv.cliente_id = c.id
);

-- Backfill assertion -- the migration REFUSES to land a lossy backfill rather
-- than reporting success over missing deals (no silent errors).
DO $$
DECLARE
  orphaned integer;
BEGIN
  SELECT count(*) INTO orphaned
  FROM erp.clientes c
  WHERE NOT EXISTS (
    SELECT 1 FROM erp.negociacoes_venda nv WHERE nv.cliente_id = c.id
  );
  IF orphaned > 0 THEN
    RAISE EXCEPTION
      'Backfill incomplete: % cliente(s) have no negociacoes_venda row', orphaned;
  END IF;
END
$$;
