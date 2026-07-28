-- ============================================================================
-- Migration 034 -- social_wiring: Funil de Vendas + Processos de Venda
--
-- WHAT THIS IS
-- ------------
-- The second consumer of the pipeline primitive extracted from the ERP
-- (`noctusai_lib.domain.pipeline` + `@noctusai/lib`'s `PipelineBoard`). Same
-- mechanic, same stage-row model, same accept-proposal seam -- a different
-- schema and a different card source.
--
-- Shapes mirror `products/erp-imobiliario/backend/migrations/042_pipeline_stages.sql`
-- deliberately: the seed primitive is configured by table NAME, so keeping the
-- column names identical means the `PipelineConfig` for this product differs
-- only in `pipeline`/`card_table`/`value_field`. Read 042's header for the full
-- rationale on why stages are ROWS (rename propagation) and why `papel` exists
-- (features key on the role, so a rename cannot break the accept seam).
--
-- WHAT'S DIFFERENT HERE, AND WHY
-- ------------------------------
-- 1. EVERY table carries `org_id NOT NULL`. `social_wiring.leads` already does,
--    so unlike the ERP (where `clientes` has no `org_id` and migration 040
--    deliberately refused to scope children tighter than their parent) there is
--    no reason to leave the cards unscoped. RLS is `org_id = current_org_id()`,
--    matching every other table in this schema.
--
-- 2. THE CARD IS SPAWNED BY A TRIGGER, not by a UI action. A lead arriving IS
--    the event that should put a card on the board, and leads arrive through
--    three different paths (the `/api/leads` router, the workbook importer's
--    bulk upsert, and the Meta Lead-Ads sync). A service-layer hook would have
--    to be added to each, and the next path added would silently skip it. A DB
--    trigger cannot be forgotten.
--
-- 3. A card points at EITHER a `leads` row OR a `meta_ads_leads` row, never
--    both and never neither (CHECK on `num_nonnulls`). Both are real tables
--    with real FKs, so this keeps referential integrity on both paths rather
--    than degrading to an untyped `origem_id`.
--
-- FORWARD-ONLY, BY DESIGN
-- -----------------------
-- There are ~12,177 `leads` and ~941 `meta_ads_leads` rows already. This
-- migration does NOT backfill cards for them: 13k cards in the first column is
-- an unusable board, and "put new leads on the first stage" is a statement
-- about arrivals, not about history. The trigger is AFTER INSERT, so only
-- leads created from now on get a card.
--
-- ⚠️ OPERATIONAL NOTE worth knowing before the next workbook import: a bulk
-- import of N NEW leads will create N cards. Re-importing existing rows is an
-- UPDATE (the importer upserts on `uq_sw_leads_org_sheet_row`), which does not
-- fire this trigger, so re-runs are safe. If a large first-time import should
-- NOT flood the board, disable the trigger for that transaction.
--
-- APPLY CONTRACT: apply inside an explicit transaction. Idempotent throughout
-- (IF NOT EXISTS / ON CONFLICT DO NOTHING / DROP ... IF EXISTS), so a failed
-- run is fixed by repairing the cause and re-running this file unchanged.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. pipeline_stages
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.pipeline_stages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  pipeline TEXT NOT NULL CHECK (pipeline IN ('funil', 'processos_venda')),
  slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9_]+$'),
  label TEXT NOT NULL CHECK (length(trim(label)) > 0),
  cor TEXT NOT NULL DEFAULT 'secondary'
    CHECK (cor IN ('primary','secondary','success','warning','destructive','muted')),
  posicao INTEGER NOT NULL DEFAULT 0,
  papel TEXT CHECK (papel IN ('proposta_aceite', 'final')),
  ativo BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, pipeline, slug)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_pipeline_stages_papel
  ON social_wiring.pipeline_stages (org_id, pipeline, papel)
  WHERE papel IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_pipeline_stages_board
  ON social_wiring.pipeline_stages (org_id, pipeline, posicao);

-- ----------------------------------------------------------------------------
-- 2. negociacoes_venda -- the Funil card
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.negociacoes_venda (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,

  -- EXACTLY ONE origin. Both are real FKs, so a deleted lead takes its card
  -- with it rather than leaving a dangling board entry.
  lead_id UUID REFERENCES social_wiring.leads(id) ON DELETE CASCADE,
  meta_ads_lead_id TEXT REFERENCES social_wiring.meta_ads_leads(id) ON DELETE CASCADE,
  CONSTRAINT negociacoes_venda_exactly_one_origin
    CHECK (num_nonnulls(lead_id, meta_ads_lead_id) = 1),

  etapa_id UUID NOT NULL REFERENCES social_wiring.pipeline_stages(id),
  status TEXT NOT NULL DEFAULT 'aberta'
    CHECK (status IN ('aberta', 'aceita', 'perdida')),
  titulo TEXT,
  valor_estimado NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_estimado >= 0),
  kanban_pos INTEGER NOT NULL DEFAULT 0,
  arquivado BOOLEAN NOT NULL DEFAULT false,

  -- Cycle-time substrate. The CHECK ties it to `status` so a closed deal
  -- cannot exist without its timestamp, which would read as zero days.
  closed_at TIMESTAMPTZ,
  CONSTRAINT negociacoes_venda_closed_at_matches_status
    CHECK ((status = 'aberta' AND closed_at IS NULL)
        OR (status <> 'aberta' AND closed_at IS NOT NULL)),

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ONE card per lead. This is what makes the spawn trigger idempotent: a second
-- INSERT for the same lead is impossible at the DB rather than merely unlikely
-- in the trigger body.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_negociacoes_venda_lead
  ON social_wiring.negociacoes_venda (lead_id) WHERE lead_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_negociacoes_venda_meta_lead
  ON social_wiring.negociacoes_venda (meta_ads_lead_id) WHERE meta_ads_lead_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_negociacoes_venda_board
  ON social_wiring.negociacoes_venda (org_id, etapa_id, kanban_pos)
  WHERE status = 'aberta' AND arquivado = false;

-- ----------------------------------------------------------------------------
-- 3. processos_venda -- the post-acceptance execution card
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.processos_venda (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,

  -- UNIQUE, and that is load-bearing: it is the idempotency guarantee for the
  -- accept-proposal seam. A double-clicked button cannot mint a second
  -- processo even under concurrent requests.
  negociacao_venda_id UUID NOT NULL UNIQUE
    REFERENCES social_wiring.negociacoes_venda(id) ON DELETE CASCADE,

  etapa_id UUID NOT NULL REFERENCES social_wiring.pipeline_stages(id),
  valor NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor >= 0),
  observacoes TEXT,
  kanban_pos INTEGER NOT NULL DEFAULT 0,
  arquivado BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_processos_venda_board
  ON social_wiring.processos_venda (org_id, etapa_id, kanban_pos)
  WHERE arquivado = false;

-- ----------------------------------------------------------------------------
-- 4. pipeline_movimentos -- ONE stage-transition history for BOTH boards
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.pipeline_movimentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL,
  pipeline TEXT NOT NULL CHECK (pipeline IN ('funil', 'processos_venda')),

  -- The card that moved. Deliberately NOT an FK: one column cannot reference
  -- two tables, and history outliving a hard-deleted card is the point of an
  -- audit trail.
  entidade_id UUID NOT NULL,

  de_etapa_id UUID REFERENCES social_wiring.pipeline_stages(id),
  para_etapa_id UUID NOT NULL REFERENCES social_wiring.pipeline_stages(id),
  responsavel_id UUID NOT NULL,
  motivo TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_pipeline_movimentos_entidade
  ON social_wiring.pipeline_movimentos (pipeline, entidade_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sw_pipeline_movimentos_org
  ON social_wiring.pipeline_movimentos (org_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 5. Default stage sets, seeded per org
-- ----------------------------------------------------------------------------
-- The funil defaults are the agency-CRM canonical pipeline
-- (Novo → Contato → Qualificado → Proposta → Negociação → Fechado), the same
-- vocabulary documented in `KB § CONTEXT/ABSORPTIONS/orbity/06-DOMAIN-GLOSSARY.md`
-- for this exact business. The processos defaults are a first pass at
-- post-signature delivery and are expected to be refined IN THE UI — which is
-- the whole point of stages being rows.
CREATE OR REPLACE FUNCTION social_wiring.ensure_default_pipeline_stages(p_org_id uuid)
  RETURNS void
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
  IF p_org_id IS NULL THEN
    RAISE EXCEPTION 'ensure_default_pipeline_stages: org_id is required';
  END IF;

  INSERT INTO social_wiring.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
  VALUES
    (p_org_id, 'funil', 'novo',        'Novo',        'secondary', 0, NULL),
    (p_org_id, 'funil', 'contato',     'Contato',     'secondary', 1, NULL),
    (p_org_id, 'funil', 'qualificado', 'Qualificado', 'warning',   2, NULL),
    (p_org_id, 'funil', 'proposta',    'Proposta',    'primary',   3, 'proposta_aceite'),
    (p_org_id, 'funil', 'negociacao',  'Negociação',  'muted',     4, NULL),
    (p_org_id, 'funil', 'fechado',     'Fechado',     'success',   5, 'final')
  ON CONFLICT (org_id, pipeline, slug) DO NOTHING;

  INSERT INTO social_wiring.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
  VALUES
    (p_org_id, 'processos_venda', 'contrato',    'Contrato',    'secondary', 0, NULL),
    (p_org_id, 'processos_venda', 'onboarding',  'Onboarding',  'secondary', 1, NULL),
    (p_org_id, 'processos_venda', 'briefing',    'Briefing',    'warning',   2, NULL),
    (p_org_id, 'processos_venda', 'planejamento','Planejamento','warning',   3, NULL),
    (p_org_id, 'processos_venda', 'execucao',    'Execução',    'primary',   4, NULL),
    (p_org_id, 'processos_venda', 'entrega',     'Entrega',     'success',   5, NULL),
    (p_org_id, 'processos_venda', 'faturamento', 'Faturamento', 'success',   6, 'final')
  ON CONFLICT (org_id, pipeline, slug) DO NOTHING;
END
$$;

-- Bootstrap every org that already has leads, so the boards are usable the
-- moment this lands rather than only after the first new lead arrives.
DO $$
DECLARE
  v_org UUID;
BEGIN
  FOR v_org IN
    SELECT DISTINCT org_id FROM social_wiring.leads
    UNION
    SELECT DISTINCT org_id FROM social_wiring.meta_ads_leads
  LOOP
    PERFORM social_wiring.ensure_default_pipeline_stages(v_org);
  END LOOP;
END
$$;

-- ----------------------------------------------------------------------------
-- 6. The spawn trigger -- a new lead becomes a card
-- ----------------------------------------------------------------------------
-- SECURITY DEFINER because it writes `negociacoes_venda` on behalf of whatever
-- path inserted the lead, including the service-role Meta sync.
--
-- Stages are ensured lazily here as well as in step 5: a brand-new org's very
-- first lead must not fail because nobody had configured its funnel yet, and
-- "the board configures itself on first use" is friendlier than an error.
CREATE OR REPLACE FUNCTION social_wiring.spawn_funil_card()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
  v_stage_id UUID;
  v_titulo   TEXT;
BEGIN
  PERFORM social_wiring.ensure_default_pipeline_stages(NEW.org_id);

  -- The FIRST stage in the org's configured order -- derived, never a
  -- hardcoded slug, because the user can reorder the board.
  SELECT id INTO v_stage_id
    FROM social_wiring.pipeline_stages
   WHERE org_id = NEW.org_id AND pipeline = 'funil' AND ativo
   ORDER BY posicao, slug
   LIMIT 1;

  IF v_stage_id IS NULL THEN
    RAISE EXCEPTION 'spawn_funil_card: org % has no active funil stages', NEW.org_id;
  END IF;

  IF TG_TABLE_NAME = 'leads' THEN
    v_titulo := COALESCE(NULLIF(trim(NEW.cliente_nome), ''), NEW.contato, 'Lead sem nome');
    INSERT INTO social_wiring.negociacoes_venda (org_id, lead_id, etapa_id, titulo)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo)
    ON CONFLICT DO NOTHING;
  ELSE
    v_titulo := COALESCE(NULLIF(trim(NEW.full_name), ''), NEW.email, NEW.phone, 'Lead de campanha');
    INSERT INTO social_wiring.negociacoes_venda (org_id, meta_ads_lead_id, etapa_id, titulo)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo)
    ON CONFLICT DO NOTHING;
  END IF;

  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS spawn_funil_card_on_lead ON social_wiring.leads;
CREATE TRIGGER spawn_funil_card_on_lead
  AFTER INSERT ON social_wiring.leads
  FOR EACH ROW EXECUTE FUNCTION social_wiring.spawn_funil_card();

-- Campaign leads take the SAME path. "Same mechanism" is not a convention here
-- -- it is literally the same function.
DROP TRIGGER IF EXISTS spawn_funil_card_on_meta_lead ON social_wiring.meta_ads_leads;
CREATE TRIGGER spawn_funil_card_on_meta_lead
  AFTER INSERT ON social_wiring.meta_ads_leads
  FOR EACH ROW EXECUTE FUNCTION social_wiring.spawn_funil_card();

-- ----------------------------------------------------------------------------
-- 7. RLS -- org-scoped throughout, matching every other table in this schema
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.pipeline_stages     ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.negociacoes_venda   ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.processos_venda     ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.pipeline_movimentos ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['pipeline_stages','negociacoes_venda','processos_venda','pipeline_movimentos']
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_own_org', t);
    EXECUTE format(
      'CREATE POLICY %I ON social_wiring.%I FOR ALL TO authenticated '
      'USING (org_id = current_org_id()) WITH CHECK (org_id = current_org_id())',
      t || '_own_org', t);

    EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_service_role', t);
    EXECUTE format(
      'CREATE POLICY %I ON social_wiring.%I FOR ALL TO service_role '
      'USING (true) WITH CHECK (true)', t || '_service_role', t);
  END LOOP;
END
$$;

-- ----------------------------------------------------------------------------
-- 8. Nav gating -- an unlisted route is HIDDEN, so the pages would not appear
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao) VALUES
  ('funil',           'producao', 'Funil de Vendas — kanban de leads'),
  ('processos_venda', 'producao', 'Processos de Venda — execução pós-aceite')
ON CONFLICT (nome_pagina) DO NOTHING;

NOTIFY pgrst, 'reload schema';
