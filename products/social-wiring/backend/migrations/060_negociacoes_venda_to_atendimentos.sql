-- ============================================================================
-- Migration 060 -- social_wiring: `negociacoes_venda` -> `atendimentos`,
-- and the funil stage order the card was always supposed to have.
--
-- USER CORRECTION (2026-08-18), verbatim:
--   "make the card be an atendimento all the way. negociação is a stage of
--    the funnel after proposta recebida and before proposta aceita/rejeitada.
--    the acceptance of the proposal takes the card to the other funnel."
--
-- The roadmap's D1 recorded this as "Funil card = a person. Processo card =
-- a negotiation." That is now refined: the card is an ATENDIMENTO for its
-- whole life. It never "becomes" a negociação — *negociação* is one column
-- it passes through. The model got this wrong in two independent ways and
-- this file fixes both.
--
-- WRONG #1 -- the entity name collided with a stage name
-- --------------------------------------------------------------------------
-- `negociacoes_venda` was the card table AND `pipeline_stages` carries a
-- stage whose slug is `negociacao`. One word, two meanings, one line apart —
-- exactly the collision that forced `clients` -> `marcas` (migration `046`).
-- Same resolution, chosen by the user: rename the entity.
--
-- 🔴 THE STAGE KEEPS ITS NAME. `pipeline_stages.slug = 'negociacao'` and its
-- label "Negociação" are CORRECT and deliberately untouched here. After this
-- migration they are the ONLY negociação in the system, which is the entire
-- point of the rename.
--
-- WRONG #2 -- the accept action fired BEFORE the negotiation
-- --------------------------------------------------------------------------
-- Live funil stages before this file:
--     0 qualificacao | 1 visitas | 2 proposta (papel='proposta_aceite')
--   | 3 negociacao   | 4 fechado (papel='final')
--
-- `papel='proposta_aceite'` is what puts the "Aceitar Proposta" action on a
-- column (`app/modules/pipeline/routers/boards.py` -> `stage_by_role`). It
-- sat on **Proposta**, i.e. one could accept a proposal two columns before
-- the negotiation had happened. After:
--     0 qualificacao | 1 visitas | 2 proposta_recebida
--   | 3 negociacao   | 4 proposta_decisao (papel='proposta_aceite')
--
-- ONE closing column, per the user: "it should be one column. But propostas
-- aceitas wont be in this column, as the card is moved to the other funnel.
-- Keep on this column only the rejected ones for us to have that history."
-- So an ACCEPTED atendimento leaves the funil (it spawns its `processos_venda`
-- row exactly as before); a REJECTED one stays in that column as history.
--
-- `papel` holds ONE value and only two exist (`proposta_aceite`, `final`).
-- The closing column takes `proposta_aceite` because that is the one with
-- BEHAVIOUR attached; `final` is exported by the seed but read by nothing in
-- this product (verified 2026-08-18), so dropping it from the funil changes
-- no code path. Recorded here rather than left for someone to rediscover.
--
-- THE TWO THINGS THAT WOULD HAVE BROKEN SILENTLY
-- --------------------------------------------------------------------------
-- Both were found by inspecting the LIVE database, not the repo:
--
--   1. `social_wiring.spawn_funil_card()` — the trigger function behind
--      `spawn_funil_card_on_lead` / `spawn_funil_card_on_meta_lead` — INSERTs
--      into the table by name. plpgsql resolves that name at execution time,
--      so a bare table rename leaves the function compiling fine and failing
--      on the next real lead: every new lead would silently stop producing a
--      card. It is recreated below against the new name.
--
--   2. `social_wiring.ensure_default_pipeline_stages()` HARDCODES the funil
--      stage set, and is called by `spawn_funil_card` on every insert. Fixing
--      only the existing per-org rows would give every NEW org the old, wrong
--      stages — the defect reintroducing itself on the next tenant. It is
--      recreated below too.
--
-- `ALTER TABLE ... RENAME TO` does NOT rename constraints, indexes or
-- policies, and PostgREST's embedded-resource hints are spelled with the FK
-- CONSTRAINT name (`...!negociacoes_venda_lead_id_fkey(...)`). Leaving them
-- would keep the dead word alive in exactly the place the next reader looks.
-- Every one is renamed below, matching what `046` did.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. The table + the FK column on processos_venda
-- ----------------------------------------------------------------------------
ALTER TABLE IF EXISTS social_wiring.negociacoes_venda RENAME TO atendimentos;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='social_wiring' AND table_name='processos_venda'
      AND column_name='negociacao_venda_id'
  ) THEN
    ALTER TABLE social_wiring.processos_venda
      RENAME COLUMN negociacao_venda_id TO atendimento_id;
  END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 2. Constraints -- PostgREST spells its embeds with these names
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  r RECORD;
  pair TEXT[];
BEGIN
  FOR pair IN SELECT * FROM (VALUES
      ARRAY['negociacoes_venda_pkey',                    'atendimentos_pkey'],
      ARRAY['negociacoes_venda_lead_id_fkey',            'atendimentos_lead_id_fkey'],
      ARRAY['negociacoes_venda_meta_ads_lead_id_fkey',   'atendimentos_meta_ads_lead_id_fkey'],
      ARRAY['negociacoes_venda_etapa_id_fkey',           'atendimentos_etapa_id_fkey'],
      ARRAY['negociacoes_venda_cliente_id_fkey',         'atendimentos_cliente_id_fkey'],
      ARRAY['negociacoes_venda_substituida_por_fkey',    'atendimentos_substituida_por_fkey'],
      ARRAY['negociacoes_venda_status_check',            'atendimentos_status_check'],
      ARRAY['negociacoes_venda_valor_estimado_check',    'atendimentos_valor_estimado_check'],
      ARRAY['negociacoes_venda_closed_at_matches_status','atendimentos_closed_at_matches_status']
  ) AS t(x) LOOP
    IF EXISTS (
      SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
      WHERE n.nspname='social_wiring' AND cl.relname='atendimentos' AND c.conname = pair[1]
    ) THEN
      EXECUTE format('ALTER TABLE social_wiring.atendimentos RENAME CONSTRAINT %I TO %I', pair[1], pair[2]);
    END IF;
  END LOOP;

  FOR pair IN SELECT * FROM (VALUES
      ARRAY['processos_venda_negociacao_venda_id_fkey', 'processos_venda_atendimento_id_fkey'],
      ARRAY['processos_venda_negociacao_venda_id_key',  'processos_venda_atendimento_id_key']
  ) AS t(x) LOOP
    IF EXISTS (
      SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
      WHERE n.nspname='social_wiring' AND cl.relname='processos_venda' AND c.conname = pair[1]
    ) THEN
      EXECUTE format('ALTER TABLE social_wiring.processos_venda RENAME CONSTRAINT %I TO %I', pair[1], pair[2]);
    END IF;
  END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- 3. Indexes
-- ----------------------------------------------------------------------------
ALTER INDEX IF EXISTS social_wiring.idx_sw_negociacoes_venda_board          RENAME TO idx_sw_atendimentos_board;
ALTER INDEX IF EXISTS social_wiring.idx_sw_negociacoes_venda_cliente        RENAME TO idx_sw_atendimentos_cliente;
ALTER INDEX IF EXISTS social_wiring.idx_sw_negociacoes_venda_cliente_ativa  RENAME TO idx_sw_atendimentos_cliente_ativa;
ALTER INDEX IF EXISTS social_wiring.idx_sw_negociacoes_venda_substituida    RENAME TO idx_sw_atendimentos_substituida;
ALTER INDEX IF EXISTS social_wiring.uq_sw_negociacoes_venda_lead            RENAME TO uq_sw_atendimentos_lead;
ALTER INDEX IF EXISTS social_wiring.uq_sw_negociacoes_venda_meta_lead       RENAME TO uq_sw_atendimentos_meta_lead;

-- ----------------------------------------------------------------------------
-- 4. RLS policies
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='social_wiring'
               AND tablename='atendimentos' AND policyname='negociacoes_venda_own_org') THEN
    ALTER POLICY "negociacoes_venda_own_org" ON social_wiring.atendimentos RENAME TO "atendimentos_own_org";
  END IF;
  IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='social_wiring'
               AND tablename='atendimentos' AND policyname='negociacoes_venda_service_role') THEN
    ALTER POLICY "negociacoes_venda_service_role" ON social_wiring.atendimentos RENAME TO "atendimentos_service_role";
  END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 5. spawn_funil_card -- would fail on the next real lead without this
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.spawn_funil_card()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'social_wiring', 'public'
AS $function$
DECLARE
  v_stage_id UUID;
  v_titulo   TEXT;
BEGIN
  PERFORM social_wiring.ensure_default_pipeline_stages(NEW.org_id);

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
    INSERT INTO social_wiring.atendimentos (org_id, lead_id, etapa_id, titulo)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo)
    ON CONFLICT DO NOTHING;
  ELSE
    v_titulo := COALESCE(NULLIF(trim(NEW.full_name), ''), NEW.email, NEW.phone, 'Lead de campanha');
    INSERT INTO social_wiring.atendimentos (org_id, meta_ads_lead_id, etapa_id, titulo)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo)
    ON CONFLICT DO NOTHING;
  END IF;

  RETURN NEW;
END
$function$;

-- ----------------------------------------------------------------------------
-- 6. ensure_default_pipeline_stages -- or every NEW org gets the old stages
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.ensure_default_pipeline_stages(p_org_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'social_wiring', 'public'
AS $function$
BEGIN
  IF p_org_id IS NULL THEN
    RAISE EXCEPTION 'ensure_default_pipeline_stages: org_id is required';
  END IF;

  -- Funil: Proposta Recebida -> Negociação -> ONE closing column carrying the
  -- accept action. `negociacao` keeps its slug deliberately (migration 060).
  INSERT INTO social_wiring.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
  VALUES
    (p_org_id, 'funil', 'qualificacao',      'Qualificação',              'secondary', 0, NULL),
    (p_org_id, 'funil', 'visitas',           'Visitas',                   'warning',   1, NULL),
    (p_org_id, 'funil', 'proposta_recebida', 'Proposta Recebida',         'primary',   2, NULL),
    (p_org_id, 'funil', 'negociacao',        'Negociação',                'muted',     3, NULL),
    (p_org_id, 'funil', 'proposta_decisao',  'Proposta Aceita/Rejeitada', 'success',   4, 'proposta_aceite')
  ON CONFLICT (org_id, pipeline, slug) DO NOTHING;

  INSERT INTO social_wiring.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
  VALUES
    (p_org_id, 'processos_venda', 'elaboracao_contrato',     'Elaboração do Contrato',   'secondary', 0, NULL),
    (p_org_id, 'processos_venda', 'analise_partes',          'Análise das Partes',       'secondary', 1, NULL),
    (p_org_id, 'processos_venda', 'revisao_contrato',        'Revisão do Contrato',      'warning',   2, NULL),
    (p_org_id, 'processos_venda', 'assinatura',              'Assinatura',               'warning',   3, NULL),
    (p_org_id, 'processos_venda', 'financiamento_escritura', 'Financiamento & Escritura','primary',   4, NULL),
    (p_org_id, 'processos_venda', 'finalizacao',             'Finalização',              'primary',   5, NULL),
    (p_org_id, 'processos_venda', 'entrega_chaves',          'Entrega das Chaves',       'success',   6, NULL),
    (p_org_id, 'processos_venda', 'nota_fiscal',             'Nota Fiscal',              'success',   7, 'final')
  ON CONFLICT (org_id, pipeline, slug) DO NOTHING;
END
$function$;

-- ----------------------------------------------------------------------------
-- 7. The EXISTING per-org funil stage rows
--
-- UPDATE in place, never delete+reinsert: every atendimento points at
-- `etapa_id`, so reinserting would orphan the whole board. `papel` is cleared
-- from `proposta` BEFORE it is set on the closing column so the two never
-- hold the same role at the same instant.
-- ----------------------------------------------------------------------------
UPDATE social_wiring.pipeline_stages
   SET slug = 'proposta_recebida', label = 'Proposta Recebida', papel = NULL
 WHERE pipeline = 'funil' AND slug = 'proposta';

UPDATE social_wiring.pipeline_stages
   SET slug = 'proposta_decisao', label = 'Proposta Aceita/Rejeitada', papel = 'proposta_aceite'
 WHERE pipeline = 'funil' AND slug = 'fechado';

DO $$
DECLARE
  v_orphans INTEGER;
BEGIN
  SELECT count(*) INTO v_orphans
    FROM social_wiring.atendimentos a
    LEFT JOIN social_wiring.pipeline_stages s ON s.id = a.etapa_id
   WHERE s.id IS NULL;
  IF v_orphans > 0 THEN
    RAISE EXCEPTION 'migration 060: % atendimento(s) point at a stage that no longer exists', v_orphans;
  END IF;
  RAISE NOTICE 'migration 060: rename + stage restructure complete, 0 orphaned cards';
END $$;

NOTIFY pgrst, 'reload schema';
