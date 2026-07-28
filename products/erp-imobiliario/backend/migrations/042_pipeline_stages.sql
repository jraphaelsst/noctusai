-- ============================================================================
-- Migration 042 -- erp.pipeline_stages: user-editable, DB-driven funnel stages
--
-- WHY THIS EXISTS
-- ---------------
-- Migrations 040/041 fixed both boards' stages as PostgreSQL enums
-- (`erp.etapa_funil`, `erp.etapa_processo`) and 041 said so explicitly:
-- "Deliberately a FIXED enum, not a configurable workflow". The user reversed
-- that decision on 2026-07-28: stages must be add/rename/recolour/reorder-able
-- from the UI, per organization, for BOTH boards.
--
-- An enum cannot carry that. `ALTER TYPE ... ADD VALUE` cannot run in a
-- transaction with the rows that use it, cannot RENAME a value without
-- rewriting every dependent row's text, and cannot be reordered at all. So the
-- stage becomes a ROW, and every card points at it by ID.
--
-- THE RENAME GUARANTEE
-- --------------------
-- The user's requirement was: "if I rename a stage, all past records get
-- edited". Pointing cards at `pipeline_stages.id` makes that true BY
-- CONSTRUCTION rather than by a backfill job: a rename is one UPDATE of one
-- `label`, and every card, column header, and history row re-reads it on the
-- next query. Nothing is copied, so nothing can drift. Storing the label on
-- the card instead would have required rewriting every historical row on every
-- rename -- and would silently miss rows an in-flight transaction had not
-- committed yet.
--
-- `slug` is a SEPARATE, stable machine key. It is what the seed defaults and
-- any code-level reference use; `label` is what humans edit. Renaming the
-- label never touches the slug, so a rename cannot break code.
--
-- THE ROLE (`papel`) COLUMN -- why user-editable stages need it
-- -------------------------------------------------------------
-- `POST /aceitar-proposta` was gated on `etapa == 'proposta'` (a hardcoded
-- slug). The moment stages are user-editable, renaming or deleting "Proposta"
-- silently breaks the seam between the two boards -- the exact class of
-- failure that makes configurable workflows dangerous.
--
-- `papel` is a small closed set of SEMANTIC roles the CODE keys on:
--   'proposta_aceite' -- the funil stage from which a proposal may be accepted
--   'final'           -- the terminal stage of a pipeline
-- The user may rename "Proposta" to anything, move it anywhere in the order,
-- or recolour it; the seam follows the role. Deleting a stage that carries a
-- role is REFUSED (enforced in the service layer, which can return a usable
-- error message; a CHECK constraint could only abort).
--
-- COLOUR IS A TOKEN, NOT A CLASS
-- ------------------------------
-- `cor` holds a design-system token name ('primary', 'warning', ...), never a
-- raw Tailwind class string. A user-editable field that flows into `className`
-- is an injection surface and a way to break the design system one stage at a
-- time; the frontend maps token -> classes from a fixed table, so an unknown
-- token degrades to the neutral default instead of rendering arbitrary CSS.
--
-- PREREQUISITES: migrations 040 (negociacoes_venda + erp.profiles.org_id +
-- the per-org agency bootstrap trigger) and 041 (processos_venda).
--
-- APPLY CONTRACT
-- --------------
-- Apply INSIDE an explicit transaction (`BEGIN; \i 042...; COMMIT;`), the same
-- way 040 and 041 were applied. This file deliberately does NOT wrap itself:
-- every sibling migration leaves transaction control to the operator, and a
-- self-wrapping file is actively unsafe under that convention -- a nested
-- COMMIT would commit the OPERATOR's outer transaction early, silently taking
-- the rest of their batch out of the transaction.
--
-- Without an outer transaction, psql commits each statement on its own, so the
-- step-5 verification RAISE aborts with the tables already created. That state
-- is RECOVERABLE rather than corrupt, and by design: every DDL statement is
-- IF NOT EXISTS / DROP-then-CREATE, every seed INSERT is ON CONFLICT DO
-- NOTHING, and both backfills are guarded by `WHERE etapa_id IS NULL`. So the
-- fix is always "repair the offending profiles, re-run this file unchanged" --
-- verified: a half-applied run followed by a re-run yields 26 stages, 0
-- duplicates, 0 unplaced cards.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. erp.pipeline_stages
-- ----------------------------------------------------------------------------
-- ORG-SCOPED, unlike `erp.clientes`/`negociacoes_venda`, which carry no
-- `org_id` (migration 040 deliberately refused to scope a child tighter than
-- its parent). This table is not a child of `clientes` -- it is CONFIGURATION,
-- the same shape as the per-org agency profile 040 already bootstraps, so
-- per-org is the correct grain: one agency's funnel must not be renamed by
-- another's.
CREATE TABLE IF NOT EXISTS erp.pipeline_stages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

  -- Which board. Deliberately TEXT + CHECK rather than an enum: adding a third
  -- pipeline should not require the very ALTER TYPE dance this migration exists
  -- to escape.
  pipeline TEXT NOT NULL CHECK (pipeline IN ('funil', 'processos_venda')),

  -- Stable machine key. Code references this; users never see or edit it.
  slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9_]+$'),

  -- The user-editable display name. THIS is what a rename changes.
  label TEXT NOT NULL CHECK (length(trim(label)) > 0),

  -- Design-system token, mapped to classes by the frontend. NOT a class string.
  cor TEXT NOT NULL DEFAULT 'secondary'
    CHECK (cor IN ('primary','secondary','success','warning','destructive','muted')),

  -- Sort order. NOT unique: a reorder rewrites the whole ordered list in one
  -- statement, and a UNIQUE(org,pipeline,posicao) would abort mid-rewrite
  -- unless made DEFERRABLE. Ties break on `slug` so ordering is total.
  posicao INTEGER NOT NULL DEFAULT 0,

  -- Semantic role the CODE keys on. See the header.
  papel TEXT CHECK (papel IN ('proposta_aceite', 'final')),

  -- Soft-disable: keeps history readable when a stage falls out of use but its
  -- past cards must still resolve their label.
  ativo BOOLEAN NOT NULL DEFAULT true,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (org_id, pipeline, slug)
);

-- At most one stage per pipeline may carry a given role -- otherwise
-- "the stage proposals are accepted from" is ambiguous and the seam picks one
-- arbitrarily.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_stages_papel
  ON erp.pipeline_stages (org_id, pipeline, papel)
  WHERE papel IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pipeline_stages_board
  ON erp.pipeline_stages (org_id, pipeline, posicao);

DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON erp.pipeline_stages;
CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON erp.pipeline_stages
  FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- ----------------------------------------------------------------------------
-- 2. Default stage sets -- the CURRENT enums, preserved exactly
-- ----------------------------------------------------------------------------
-- Labels and colours are lifted verbatim from the frontend configs they
-- replace (`lib/etapasConfig.ts`, `lib/etapasProcessoConfig.ts`) so that
-- applying this migration is visually a no-op: the same boards, the same
-- names, the same colours -- now editable.
CREATE OR REPLACE FUNCTION erp.ensure_default_pipeline_stages(p_org_id uuid)
  RETURNS void
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'erp', 'public'
AS $$
BEGIN
  IF p_org_id IS NULL THEN
    RAISE EXCEPTION 'ensure_default_pipeline_stages: org_id is required';
  END IF;

  -- Funil (from erp.etapa_funil). `proposta` carries the accept seam;
  -- `fechado` is the funil's terminal stage.
  INSERT INTO erp.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
  VALUES
    (p_org_id, 'funil', 'qualificacao', 'Qualificação', 'secondary',   0, NULL),
    (p_org_id, 'funil', 'visitas',      'Visitas',      'warning',     1, NULL),
    (p_org_id, 'funil', 'proposta',     'Proposta',     'primary',     2, 'proposta_aceite'),
    (p_org_id, 'funil', 'negociacao',   'Negociação',   'muted',       3, NULL),
    (p_org_id, 'funil', 'fechado',      'Fechado',      'success',     4, 'final')
  ON CONFLICT (org_id, pipeline, slug) DO NOTHING;

  -- Processos de Venda (from erp.etapa_processo). `nota_fiscal` is terminal.
  INSERT INTO erp.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
  VALUES
    (p_org_id, 'processos_venda', 'elaboracao_contrato',     'Elaboração do Contrato',  'secondary', 0, NULL),
    (p_org_id, 'processos_venda', 'analise_partes',          'Análise das Partes',      'secondary', 1, NULL),
    (p_org_id, 'processos_venda', 'revisao_contrato',        'Revisão do Contrato',     'warning',   2, NULL),
    (p_org_id, 'processos_venda', 'assinatura',              'Assinatura',              'warning',   3, NULL),
    (p_org_id, 'processos_venda', 'financiamento_escritura', 'Financiamento & Escritura','primary',  4, NULL),
    (p_org_id, 'processos_venda', 'finalizacao',             'Finalização',             'primary',   5, NULL),
    (p_org_id, 'processos_venda', 'entrega_chaves',          'Entrega das Chaves',      'success',   6, NULL),
    (p_org_id, 'processos_venda', 'nota_fiscal',             'Nota Fiscal',             'success',   7, 'final')
  ON CONFLICT (org_id, pipeline, slug) DO NOTHING;
END
$$;

-- Bootstrap every EXISTING org.
DO $$
DECLARE
  v_org RECORD;
BEGIN
  FOR v_org IN SELECT id FROM public.organizations LOOP
    PERFORM erp.ensure_default_pipeline_stages(v_org.id);
  END LOOP;
END
$$;

-- And every FUTURE org. 040 already installs `create_agency_profile_trigger`
-- on `public.organizations` for the agency profile; this extends the same
-- bootstrap seam rather than adding a second trigger on the same table, so the
-- per-org setup stays one thing to reason about.
CREATE OR REPLACE FUNCTION erp.create_agency_for_new_org()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'erp', 'public'
AS $$
BEGIN
  PERFORM erp.ensure_agency_profile(NEW.id);
  PERFORM erp.ensure_default_pipeline_stages(NEW.id);
  RETURN NEW;
END
$$;

-- ----------------------------------------------------------------------------
-- 3. Point the cards at stage ROWS
-- ----------------------------------------------------------------------------
-- Nullable for now, on purpose. Making it NOT NULL here would abort the
-- migration for any row whose org cannot be resolved (a corretor with a NULL
-- `org_id` -- there are such profiles today). Step 5 verifies instead, and
-- RAISES with a count, which is a diagnosable failure rather than a constraint
-- violation with no context.
ALTER TABLE erp.negociacoes_venda
  ADD COLUMN IF NOT EXISTS etapa_id UUID REFERENCES erp.pipeline_stages(id);
ALTER TABLE erp.processos_venda
  ADD COLUMN IF NOT EXISTS etapa_id UUID REFERENCES erp.pipeline_stages(id);

CREATE INDEX IF NOT EXISTS idx_negociacoes_venda_etapa_id
  ON erp.negociacoes_venda (etapa_id, kanban_pos);
CREATE INDEX IF NOT EXISTS idx_processos_venda_etapa_id
  ON erp.processos_venda (etapa_id, kanban_pos);

-- The legacy enum columns lose NOT NULL: once a user adds a stage of their own,
-- there is no enum value to write. They are RETAINED (not dropped) as the
-- rollback landing zone and are kept in sync opportunistically by the service
-- layer while the slug still matches an enum label. Removal is the sibling of
-- roadmap Q8 (`clientes.etapa_atual`) and follows the same trigger: one stable
-- release on the new read path.
ALTER TABLE erp.negociacoes_venda ALTER COLUMN etapa DROP NOT NULL;
ALTER TABLE erp.negociacoes_venda ALTER COLUMN etapa DROP DEFAULT;
ALTER TABLE erp.processos_venda   ALTER COLUMN etapa DROP NOT NULL;
ALTER TABLE erp.processos_venda   ALTER COLUMN etapa DROP DEFAULT;

-- Backfill: resolve each card's org through its corretor's profile, then match
-- the stage by slug. `etapa::text` is exactly the seeded slug, which is why the
-- defaults above reuse the enum labels verbatim.
UPDATE erp.negociacoes_venda n
   SET etapa_id = ps.id
  FROM erp.profiles p
  JOIN erp.pipeline_stages ps
    ON ps.org_id = p.org_id AND ps.pipeline = 'funil'
 WHERE p.id = n.corretor_id
   AND ps.slug = n.etapa::text
   AND n.etapa_id IS NULL;

UPDATE erp.processos_venda pv
   SET etapa_id = ps.id
  FROM erp.profiles p
  JOIN erp.pipeline_stages ps
    ON ps.org_id = p.org_id AND ps.pipeline = 'processos_venda'
 WHERE p.id = pv.corretor_id
   AND ps.slug = pv.etapa::text
   AND pv.etapa_id IS NULL;

-- ----------------------------------------------------------------------------
-- 4. erp.pipeline_movimentos -- ONE stage-transition history for BOTH boards
-- ----------------------------------------------------------------------------
-- `erp.funil_movimentos` cannot serve both: its `de_etapa`/`para_etapa` are
-- typed `erp.etapa_funil`, so a Processos transition is literally unwritable
-- there -- which is why the Processos board shipped with NO audit trail at all
-- while the Funil had one (the gap this migration closes at the root rather
-- than per-board).
--
-- `funil_movimentos` is RETAINED, not dropped: dropping a PostgREST-exposed
-- table is forbidden, and it costs nothing to leave (0 rows, no readers). It is
-- superseded by this table and should be treated as deprecated.
CREATE TABLE IF NOT EXISTS erp.pipeline_movimentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline TEXT NOT NULL CHECK (pipeline IN ('funil', 'processos_venda')),

  -- The card that moved: a negociacao_venda.id or a processos_venda.id.
  -- Deliberately NOT an FK: one column cannot reference two tables, and the
  -- alternative (two nullable FKs + a CHECK) buys referential integrity at the
  -- cost of a schema change every time a pipeline is added. History outliving
  -- a hard-deleted card is acceptable -- that is what an audit trail is for.
  entidade_id UUID NOT NULL,

  -- Denormalised for the common "this client's history" query without a hop.
  cliente_id UUID REFERENCES erp.clientes(id) ON DELETE SET NULL,

  -- NULL `de_etapa_id` = the card entered the board at this stage.
  de_etapa_id UUID REFERENCES erp.pipeline_stages(id),
  para_etapa_id UUID NOT NULL REFERENCES erp.pipeline_stages(id),

  responsavel_id UUID NOT NULL REFERENCES erp.profiles(id),
  motivo TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_movimentos_entidade
  ON erp.pipeline_movimentos (pipeline, entidade_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_movimentos_cliente
  ON erp.pipeline_movimentos (cliente_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_movimentos_responsavel
  ON erp.pipeline_movimentos (responsavel_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 5. Verify the backfill LOUDLY
-- ----------------------------------------------------------------------------
-- A silently-NULL `etapa_id` is a card that vanishes from its board: the query
-- groups by stage, and a NULL stage joins to nothing. Failing here with a count
-- is far cheaper than discovering it as a missing card in production.
DO $$
DECLARE
  v_neg INTEGER;
  v_proc INTEGER;
BEGIN
  SELECT count(*) INTO v_neg  FROM erp.negociacoes_venda WHERE etapa_id IS NULL;
  SELECT count(*) INTO v_proc FROM erp.processos_venda   WHERE etapa_id IS NULL;

  IF v_neg > 0 OR v_proc > 0 THEN
    RAISE EXCEPTION
      'pipeline_stages backfill incomplete: % negociacoes and % processos have no etapa_id. '
      'Cause is almost always a corretor whose erp.profiles.org_id IS NULL '
      '(no org => no stage rows to match). Fix those profiles, then re-run.',
      v_neg, v_proc;
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- 6. RLS
-- ----------------------------------------------------------------------------
ALTER TABLE erp.pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.pipeline_movimentos ENABLE ROW LEVEL SECURITY;

-- READ: anyone in the org. A stage label is not sensitive, and every board
-- render needs it.
DROP POLICY IF EXISTS "pipeline_stages_select" ON erp.pipeline_stages;
CREATE POLICY "pipeline_stages_select" ON erp.pipeline_stages
  FOR SELECT TO authenticated
  USING (
    org_id = erp.current_org_id()
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  );

-- WRITE: any authenticated member of the SAME org.
--
-- DECISION, worth stating because it is a real trade-off: editing stages
-- changes the board for everyone in the org, so `admin`-only is the tighter
-- and more obvious choice. It is not the one taken, because erp currently has
-- ZERO users holding the `admin` role -- every profile is `corretor` -- so an
-- admin-gated policy would ship a stage-management UI that nobody can use, and
-- "the feature is there but permission-denied for all" is a worse default than
-- team-level trust in a single-agency tenant. Tighten by replacing
-- `org_id = erp.current_org_id()` with the `has_role(admin)` clause alone once
-- admins exist. Cross-org writes are impossible either way.
DROP POLICY IF EXISTS "pipeline_stages_write" ON erp.pipeline_stages;
CREATE POLICY "pipeline_stages_write" ON erp.pipeline_stages
  FOR ALL TO authenticated
  USING (
    org_id = erp.current_org_id()
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  )
  WITH CHECK (
    org_id = erp.current_org_id()
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  );

DROP POLICY IF EXISTS "service_role_bypass" ON erp.pipeline_stages;
CREATE POLICY "service_role_bypass" ON erp.pipeline_stages
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- History mirrors the visibility of the cards it describes: admin, or the
-- corretor who performed the move.
DROP POLICY IF EXISTS "pipeline_movimentos_select" ON erp.pipeline_movimentos;
CREATE POLICY "pipeline_movimentos_select" ON erp.pipeline_movimentos
  FOR SELECT TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = responsavel_id
  );

DROP POLICY IF EXISTS "pipeline_movimentos_insert" ON erp.pipeline_movimentos;
CREATE POLICY "pipeline_movimentos_insert" ON erp.pipeline_movimentos
  FOR INSERT TO authenticated
  WITH CHECK (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = responsavel_id
  );

DROP POLICY IF EXISTS "service_role_bypass" ON erp.pipeline_movimentos;
CREATE POLICY "service_role_bypass" ON erp.pipeline_movimentos
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 7. PostgREST must be told about the new tables
-- ----------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';
