-- ============================================================================
-- Migration 037 -- social_wiring: ERP stage parity + canonical phone format
--
-- TWO CHANGES, ONE MIGRATION
-- --------------------------
-- They ship together because both are "make social-wiring agree with the rest
-- of the platform", both touch rows the Funil board reads, and splitting them
-- would mean two apply windows against the same live boards.
--
--   PART A -- both pipelines adopt the ERP's stage vocabulary verbatim.
--   PART B -- `leads.contato` / `meta_ads_leads.phone` become E.164, and a
--             trigger keeps them that way.
--
-- ============================================================================
-- PART A -- ERP stage parity
-- ============================================================================
-- Migration 034 seeded social-wiring with an agency-CRM funnel (Novo →
-- Contato → Qualificado → …) and a first-pass delivery pipeline (Contrato →
-- Onboarding → Briefing → …). The user reversed that on 2026-07-30: this
-- product and erp-imobiliario serve the SAME real-estate business, and two
-- boards with different column names for the same deal is a reporting problem
-- and a training problem. Both boards now carry the ERP's stages, from
-- `products/erp-imobiliario/backend/migrations/042_pipeline_stages.sql`.
--
-- RENAME IN PLACE, NEVER DELETE-AND-RECREATE
-- ------------------------------------------
-- Every stage is referenced by `negociacoes_venda.etapa_id`,
-- `processos_venda.etapa_id` AND by `pipeline_movimentos.de_etapa_id` /
-- `para_etapa_id`. Dropping a stage row and inserting its replacement would
-- either violate those FKs or, worse, orphan the audit trail -- history rows
-- pointing at a stage that no longer explains what happened.
--
-- So this migration RENAMES: it UPDATEs `slug`/`label`/`cor`/`posicao`/`papel`
-- on the surviving rows. That is the same guarantee 042 was designed around --
-- a rename is one UPDATE and every card, column header and history row
-- re-reads it on the next query, because nothing was ever copied.
--
-- The map is positional, since both boards describe the same journey at
-- different granularities:
--
--   funil            novo         -> qualificacao   (17 cards ride along)
--                    contato      -> visitas
--                    qualificado  -> FOLDED into qualificacao (1 card moved)
--                    proposta     -> proposta        (unchanged, repositioned)
--                    negociacao   -> negociacao      (unchanged, repositioned)
--                    fechado      -> fechado         (unchanged, repositioned)
--
--   processos_venda  contrato     -> elaboracao_contrato   (1 card rides along)
--                    onboarding   -> analise_partes
--                    briefing     -> revisao_contrato
--                    planejamento -> assinatura
--                    execucao     -> financiamento_escritura
--                    entrega      -> finalizacao
--                    faturamento  -> entrega_chaves
--                    (nota_fiscal is INSERTed -- 7 stages become 8)
--
-- `papel` moves with the semantics, not with the row: `faturamento` was the
-- funnel's terminal stage and becomes `entrega_chaves`, which is NOT terminal
-- in the ERP model -- so its `final` role is cleared and lands on the newly
-- inserted `nota_fiscal`. Doing that in the wrong order would trip
-- `uq_sw_pipeline_stages_papel`, so the clear happens before the insert.
--
-- NO CARD IS EVER STRANDED
-- ------------------------
-- A stage that survives the rename map but is not in the ERP target set is
-- deleted -- and step A4 REFUSES to delete one that still holds cards, with a
-- count, rather than cascading them into nothing. A card whose `etapa_id`
-- points at a deleted row would vanish from its board (the query groups by
-- stage; a dangling stage joins to nothing), which is exactly the silent
-- failure 042's step 5 was written to prevent.
--
-- ============================================================================
-- PART B -- canonical phone format
-- ============================================================================
-- The same person's phone was held four ways across this platform:
--
--   Meta Lead-Ads  "+5511994573387"   E.164          (864 of 958 rows)
--   workbook import "11 99457.3387"   DDD + dotted   (~12,177 leads)
--   ERP form        "(11) 99457-3387" pt-BR pretty
--   WhatsApp/WAHA   "5511994573387"   digits, no +
--
-- None of those compare equal, so dedup, search and "do we already have this
-- contact?" were all quietly wrong. The canonical form is now E.164 --
-- `+5511994573387` -- chosen because it is the shape campaign leads ALREADY
-- arrive in (so that intake path becomes a no-op) and because it is one
-- `lstrip('+')` from the WhatsApp chat id these numbers are ultimately for.
--
-- THREE RUNTIMES, ONE CONTRACT
-- ----------------------------
-- The rule lives in three places because three runtimes need it and cannot
-- share code:
--
--   noctusai_lib.primitives.phone      (backend, canonical)
--   @noctusai/lib/phone                (frontend display seam)
--   social_wiring.normalize_phone()    (this file -- the DB guarantee)
--
-- They are ONE contract. Step B4 below re-runs the SAME table of cases the
-- other two are tested against and RAISES if the SQL implementation disagrees,
-- so a drift fails at apply time instead of showing up as a number that saves
-- differently than it displays.
--
-- WHY A TRIGGER AND NOT JUST NORMALIZING IN THE ROUTER
-- ---------------------------------------------------
-- Leads arrive through three paths today (the `/api/leads` router, the
-- workbook importer's bulk upsert, and the Meta Lead-Ads sync) and the next
-- path added would silently skip a service-layer hook. Migration 034 made
-- exactly this argument for the card-spawn trigger; the same reasoning
-- applies to the format of the number those paths write. The application
-- layer ALSO normalizes (so the API echoes back what it stored); the trigger
-- is the backstop that cannot be forgotten.
--
-- IT NEVER INVENTS DIGITS
-- -----------------------
-- Brazil's 2012 nine-digit mobile migration left legacy 8-digit mobiles in the
-- data, and ~77 campaign rows are outright malformed (6 to 22 digits). Guessing
-- which 8-digit numbers need a leading 9 would silently write a stranger's
-- number into a customer record. Unparseable values are LEFT ALONE, counted,
-- and reported by step B5. They stay visible in the UI (the display seam falls
-- back to the raw string) so a human can fix what a machine must not guess.
--
-- NO NEW COLUMNS -- THE SPLIT ALREADY EXISTS
-- ------------------------------------------
-- `leads` already separates the two: `contato` is the string as it arrived
-- (sheet cell, form field, API body) and `contato_norm` is the machine form.
-- So this migration does NOT add a `contato_raw`; it REDEFINES `contato_norm`
-- from "digits, no country code" (`11994573387` -- which never compared equal
-- to a campaign's `+5511994573387`) to canonical E.164. The backfill is
-- reversible for free, because `contato` was never overwritten.
--
-- `meta_ads_leads` needs no raw column either: `raw` (jsonb) already holds
-- Meta's original `field_data` payload, phone included, verbatim.
--
-- A REAL BUG THIS CLOSES
-- ----------------------
-- Only the workbook importer ever populated `contato_norm`/`contato_tipo`. A
-- lead created through `POST /api/leads` left BOTH null (15 and 2 live rows
-- respectively on 2026-07-30), so hand-entered leads were invisible to every
-- lookup that keys on the normalized column. The trigger below populates them
-- for all three write paths, which is why it is a trigger and not another
-- service-layer call the next path would forget.
--
-- APPLY CONTRACT: apply inside an explicit transaction. Idempotent throughout
-- (IF NOT EXISTS / guarded UPDATEs / ON CONFLICT DO NOTHING), so a failed run
-- is fixed by repairing the cause and re-running this file unchanged.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- A1. The target vocabulary -- ERP's, verbatim
-- ----------------------------------------------------------------------------
-- Seeds NEW orgs. Existing orgs are reconciled by A2-A5 below.
--
-- This function stays a pure "seed if absent": it is called by the card-spawn
-- trigger on every lead insert, and a user who has deliberately renamed a
-- stage must not have it reverted by the next lead that arrives. Reconciling
-- existing orgs is a ONE-SHOT operation and lives in the DO blocks, not here.
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
    (p_org_id, 'funil', 'qualificacao', 'Qualificação', 'secondary', 0, NULL),
    (p_org_id, 'funil', 'visitas',      'Visitas',      'warning',   1, NULL),
    (p_org_id, 'funil', 'proposta',     'Proposta',     'primary',   2, 'proposta_aceite'),
    (p_org_id, 'funil', 'negociacao',   'Negociação',   'muted',     3, NULL),
    (p_org_id, 'funil', 'fechado',      'Fechado',      'success',   4, 'final')
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
$$;

-- ----------------------------------------------------------------------------
-- A2. Fold `qualificado` into what `novo` is about to become
-- ----------------------------------------------------------------------------
-- Runs BEFORE the rename, while both slugs still exist. Afterwards
-- `qualificado` holds no cards, so A4 can delete it without stranding one.
DO $$
DECLARE
  v_moved INTEGER;
BEGIN
  WITH src AS (
    SELECT id, org_id FROM social_wiring.pipeline_stages
     WHERE pipeline = 'funil' AND slug = 'qualificado'
  ), dst AS (
    SELECT id, org_id FROM social_wiring.pipeline_stages
     WHERE pipeline = 'funil' AND slug = 'novo'
  )
  UPDATE social_wiring.negociacoes_venda n
     SET etapa_id = dst.id, updated_at = now()
    FROM src JOIN dst ON dst.org_id = src.org_id
   WHERE n.etapa_id = src.id;
  GET DIAGNOSTICS v_moved = ROW_COUNT;

  IF v_moved > 0 THEN
    RAISE NOTICE '037/A2: folded % negociacoes from "qualificado" into "novo" (-> qualificacao)', v_moved;
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- A3. Rename every surviving stage to its ERP identity
-- ----------------------------------------------------------------------------
-- Guarded by `NOT EXISTS (target slug)` so a re-run is a no-op rather than a
-- unique-violation, and so an org that already holds the ERP vocabulary (a
-- fresh org seeded by A1) is left completely alone.
DO $$
DECLARE
  v_map RECORD;
  v_renamed INTEGER := 0;
  v_n INTEGER;
BEGIN
  FOR v_map IN
    SELECT * FROM (VALUES
      -- pipeline,          from,           to,                        label,                       cor,         posicao, papel
      ('funil',           'novo',         'qualificacao',            'Qualificação',              'secondary', 0, NULL),
      ('funil',           'contato',      'visitas',                 'Visitas',                   'warning',   1, NULL),
      ('funil',           'proposta',     'proposta',                'Proposta',                  'primary',   2, 'proposta_aceite'),
      ('funil',           'negociacao',   'negociacao',              'Negociação',                'muted',     3, NULL),
      ('funil',           'fechado',      'fechado',                 'Fechado',                   'success',   4, 'final'),
      ('processos_venda', 'contrato',     'elaboracao_contrato',     'Elaboração do Contrato',    'secondary', 0, NULL),
      ('processos_venda', 'onboarding',   'analise_partes',          'Análise das Partes',        'secondary', 1, NULL),
      ('processos_venda', 'briefing',     'revisao_contrato',        'Revisão do Contrato',       'warning',   2, NULL),
      ('processos_venda', 'planejamento', 'assinatura',              'Assinatura',                'warning',   3, NULL),
      ('processos_venda', 'execucao',     'financiamento_escritura', 'Financiamento & Escritura', 'primary',   4, NULL),
      ('processos_venda', 'entrega',      'finalizacao',             'Finalização',               'primary',   5, NULL),
      -- `faturamento` loses `final`; A5 gives it to `nota_fiscal`. Clearing
      -- here (before the insert) is what keeps uq_sw_pipeline_stages_papel
      -- satisfied at every point in this migration.
      ('processos_venda', 'faturamento',  'entrega_chaves',          'Entrega das Chaves',        'success',   6, NULL)
    ) AS t(pipeline, from_slug, to_slug, label, cor, posicao, papel)
  LOOP
    UPDATE social_wiring.pipeline_stages ps
       SET slug    = v_map.to_slug,
           label   = v_map.label,
           cor     = v_map.cor,
           posicao = v_map.posicao,
           papel   = v_map.papel,
           updated_at = now()
     WHERE ps.pipeline = v_map.pipeline
       AND ps.slug = v_map.from_slug
       AND (v_map.from_slug = v_map.to_slug
            OR NOT EXISTS (
              SELECT 1 FROM social_wiring.pipeline_stages other
               WHERE other.org_id = ps.org_id
                 AND other.pipeline = ps.pipeline
                 AND other.slug = v_map.to_slug
            ));
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_renamed := v_renamed + v_n;
  END LOOP;

  RAISE NOTICE '037/A3: renamed % stage rows to the ERP vocabulary', v_renamed;
END
$$;

-- ----------------------------------------------------------------------------
-- A4. Delete leftovers -- but REFUSE to strand a card
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_stranded INTEGER;
  v_deleted INTEGER;
BEGIN
  WITH canonical(pipeline, slug) AS (
    VALUES
      ('funil','qualificacao'), ('funil','visitas'), ('funil','proposta'),
      ('funil','negociacao'), ('funil','fechado'),
      ('processos_venda','elaboracao_contrato'), ('processos_venda','analise_partes'),
      ('processos_venda','revisao_contrato'), ('processos_venda','assinatura'),
      ('processos_venda','financiamento_escritura'), ('processos_venda','finalizacao'),
      ('processos_venda','entrega_chaves'), ('processos_venda','nota_fiscal')
  )
  SELECT count(*) INTO v_stranded
    FROM social_wiring.pipeline_stages ps
   WHERE NOT EXISTS (
           SELECT 1 FROM canonical c
            WHERE c.pipeline = ps.pipeline AND c.slug = ps.slug)
     AND (EXISTS (SELECT 1 FROM social_wiring.negociacoes_venda n WHERE n.etapa_id = ps.id)
       OR EXISTS (SELECT 1 FROM social_wiring.processos_venda p WHERE p.etapa_id = ps.id));

  IF v_stranded > 0 THEN
    RAISE EXCEPTION
      '037/A4: % non-canonical stage(s) still hold cards. Deleting them would '
      'remove those cards from their board silently. Move the cards to a '
      'canonical stage, then re-run this file unchanged.', v_stranded;
  END IF;

  -- History rows outlive their stage by design, but the FK does not allow it:
  -- point them at the stage the deleted one became, or NULL for `de_etapa_id`
  -- (which already means "entered the board here"). Only reachable for stages
  -- this migration did NOT rename, i.e. ones a user created themselves.
  WITH canonical(pipeline, slug) AS (
    VALUES
      ('funil','qualificacao'), ('funil','visitas'), ('funil','proposta'),
      ('funil','negociacao'), ('funil','fechado'),
      ('processos_venda','elaboracao_contrato'), ('processos_venda','analise_partes'),
      ('processos_venda','revisao_contrato'), ('processos_venda','assinatura'),
      ('processos_venda','financiamento_escritura'), ('processos_venda','finalizacao'),
      ('processos_venda','entrega_chaves'), ('processos_venda','nota_fiscal')
  ), doomed AS (
    SELECT ps.id FROM social_wiring.pipeline_stages ps
     WHERE NOT EXISTS (
       SELECT 1 FROM canonical c WHERE c.pipeline = ps.pipeline AND c.slug = ps.slug)
  )
  UPDATE social_wiring.pipeline_movimentos m
     SET de_etapa_id = NULL
   WHERE m.de_etapa_id IN (SELECT id FROM doomed);

  WITH canonical(pipeline, slug) AS (
    VALUES
      ('funil','qualificacao'), ('funil','visitas'), ('funil','proposta'),
      ('funil','negociacao'), ('funil','fechado'),
      ('processos_venda','elaboracao_contrato'), ('processos_venda','analise_partes'),
      ('processos_venda','revisao_contrato'), ('processos_venda','assinatura'),
      ('processos_venda','financiamento_escritura'), ('processos_venda','finalizacao'),
      ('processos_venda','entrega_chaves'), ('processos_venda','nota_fiscal')
  )
  DELETE FROM social_wiring.pipeline_stages ps
   WHERE NOT EXISTS (
     SELECT 1 FROM canonical c WHERE c.pipeline = ps.pipeline AND c.slug = ps.slug)
     -- A movimento's `para_etapa_id` is NOT NULL, so a stage still named by
     -- one cannot be deleted without destroying that history row. Keep it:
     -- an orphaned-but-referenced stage row costs nothing and the audit trail
     -- stays readable. `ativo = false` takes it off the board.
     AND NOT EXISTS (
       SELECT 1 FROM social_wiring.pipeline_movimentos m WHERE m.para_etapa_id = ps.id);
  GET DIAGNOSTICS v_deleted = ROW_COUNT;

  -- Anything that survived the DELETE did so only because a history row still
  -- names it. Soft-disable takes it off the board while keeping that history
  -- readable -- which is exactly what `ativo` is for.
  --
  -- Scoped on the (pipeline, slug) PAIR, not on slug alone: `assinatura` is
  -- canonical for `processos_venda` and would wrongly survive a slug-only
  -- test if a user had ever created a funil stage by that name.
  WITH canonical(pipeline, slug) AS (
    VALUES
      ('funil','qualificacao'), ('funil','visitas'), ('funil','proposta'),
      ('funil','negociacao'), ('funil','fechado'),
      ('processos_venda','elaboracao_contrato'), ('processos_venda','analise_partes'),
      ('processos_venda','revisao_contrato'), ('processos_venda','assinatura'),
      ('processos_venda','financiamento_escritura'), ('processos_venda','finalizacao'),
      ('processos_venda','entrega_chaves'), ('processos_venda','nota_fiscal')
  )
  UPDATE social_wiring.pipeline_stages ps
     SET ativo = false, updated_at = now()
   WHERE ps.ativo
     AND NOT EXISTS (
       SELECT 1 FROM canonical c
        WHERE c.pipeline = ps.pipeline AND c.slug = ps.slug);

  RAISE NOTICE '037/A4: deleted % leftover stage row(s)', v_deleted;
END
$$;

-- ----------------------------------------------------------------------------
-- A5. Ensure the full ERP set exists, with the right shape
-- ----------------------------------------------------------------------------
-- Inserts what the rename map could not produce (`nota_fiscal` -- 7 stages
-- become 8) and corrects label/cor/posicao/papel for any org already holding
-- a canonical slug with stale attributes (a re-run, or an org seeded before
-- this migration by the old A1).
DO $$
DECLARE
  v_org UUID;
BEGIN
  FOR v_org IN SELECT DISTINCT org_id FROM social_wiring.pipeline_stages LOOP
    PERFORM social_wiring.ensure_default_pipeline_stages(v_org);
  END LOOP;
END
$$;

UPDATE social_wiring.pipeline_stages ps
   SET label = t.label, cor = t.cor, posicao = t.posicao, papel = t.papel,
       ativo = true, updated_at = now()
  FROM (VALUES
    ('funil','qualificacao','Qualificação','secondary',0,NULL),
    ('funil','visitas','Visitas','warning',1,NULL),
    ('funil','proposta','Proposta','primary',2,'proposta_aceite'),
    ('funil','negociacao','Negociação','muted',3,NULL),
    ('funil','fechado','Fechado','success',4,'final'),
    ('processos_venda','elaboracao_contrato','Elaboração do Contrato','secondary',0,NULL),
    ('processos_venda','analise_partes','Análise das Partes','secondary',1,NULL),
    ('processos_venda','revisao_contrato','Revisão do Contrato','warning',2,NULL),
    ('processos_venda','assinatura','Assinatura','warning',3,NULL),
    ('processos_venda','financiamento_escritura','Financiamento & Escritura','primary',4,NULL),
    ('processos_venda','finalizacao','Finalização','primary',5,NULL),
    ('processos_venda','entrega_chaves','Entrega das Chaves','success',6,NULL),
    ('processos_venda','nota_fiscal','Nota Fiscal','success',7,'final')
  ) AS t(pipeline, slug, label, cor, posicao, papel)
 WHERE ps.pipeline = t.pipeline AND ps.slug = t.slug
   AND (ps.label, ps.cor, ps.posicao, ps.papel, ps.ativo)
       IS DISTINCT FROM (t.label, t.cor, t.posicao, t.papel, true);

-- ----------------------------------------------------------------------------
-- A6. Verify the boards are intact
-- ----------------------------------------------------------------------------
-- Asserts PRESENCE of the canonical set rather than an exact count. Stages are
-- user-editable by design, so an org that has since added a stage of its own
-- must not make a re-run of this file explode -- but a MISSING canonical stage
-- means the reconcile did not land, and a card pointing at a dead stage means
-- a card has silently left its board. Those two are hard failures.
DO $$
DECLARE
  v_missing INTEGER;
  v_orphan_neg INTEGER;
  v_orphan_proc INTEGER;
  v_extra INTEGER;
BEGIN
  WITH canonical(pipeline, slug) AS (
    VALUES
      ('funil','qualificacao'), ('funil','visitas'), ('funil','proposta'),
      ('funil','negociacao'), ('funil','fechado'),
      ('processos_venda','elaboracao_contrato'), ('processos_venda','analise_partes'),
      ('processos_venda','revisao_contrato'), ('processos_venda','assinatura'),
      ('processos_venda','financiamento_escritura'), ('processos_venda','finalizacao'),
      ('processos_venda','entrega_chaves'), ('processos_venda','nota_fiscal')
  ), orgs AS (
    SELECT DISTINCT org_id FROM social_wiring.pipeline_stages
  )
  SELECT count(*) INTO v_missing
    FROM orgs CROSS JOIN canonical c
   WHERE NOT EXISTS (
     SELECT 1 FROM social_wiring.pipeline_stages ps
      WHERE ps.org_id = orgs.org_id AND ps.pipeline = c.pipeline
        AND ps.slug = c.slug AND ps.ativo);

  SELECT count(*) INTO v_orphan_neg
    FROM social_wiring.negociacoes_venda n
    LEFT JOIN social_wiring.pipeline_stages ps ON ps.id = n.etapa_id
   WHERE ps.id IS NULL OR NOT ps.ativo;

  SELECT count(*) INTO v_orphan_proc
    FROM social_wiring.processos_venda p
    LEFT JOIN social_wiring.pipeline_stages ps ON ps.id = p.etapa_id
   WHERE ps.id IS NULL OR NOT ps.ativo;

  IF v_missing > 0 THEN
    RAISE EXCEPTION
      '037/A6: % canonical (org, pipeline, stage) combination(s) are missing or '
      'inactive after the reconcile -- the ERP vocabulary did not land.', v_missing;
  END IF;

  IF v_orphan_neg > 0 OR v_orphan_proc > 0 THEN
    RAISE EXCEPTION
      '037/A6: % negociacao(oes) and % processo(s) point at a missing or inactive '
      'stage and would disappear from their board.', v_orphan_neg, v_orphan_proc;
  END IF;

  SELECT count(*) INTO v_extra
    FROM social_wiring.pipeline_stages
   WHERE ativo AND pipeline IN ('funil','processos_venda')
     AND (pipeline, slug) NOT IN (
       ('funil','qualificacao'), ('funil','visitas'), ('funil','proposta'),
       ('funil','negociacao'), ('funil','fechado'),
       ('processos_venda','elaboracao_contrato'), ('processos_venda','analise_partes'),
       ('processos_venda','revisao_contrato'), ('processos_venda','assinatura'),
       ('processos_venda','financiamento_escritura'), ('processos_venda','finalizacao'),
       ('processos_venda','entrega_chaves'), ('processos_venda','nota_fiscal'));

  IF v_extra > 0 THEN
    RAISE NOTICE
      '037/A6: % active stage(s) outside the ERP set remain (user-created since '
      'this migration was written). Parity with erp-imobiliario is partial.', v_extra;
  END IF;
END
$$;

-- ============================================================================
-- PART B -- canonical phone format
-- ============================================================================

-- ----------------------------------------------------------------------------
-- B1. Re-document the columns this migration redefines
-- ----------------------------------------------------------------------------
-- No DDL: the raw/normalized split already exists. What changes is the MEANING
-- of `contato_norm`, and a stale comment on a column whose semantics moved is
-- how the next person writes code against the old contract.
COMMENT ON COLUMN social_wiring.leads.contato IS
  'The contact string exactly as it arrived (sheet cell, form field, API body). '
  'Never rewritten -- this is what makes the canonical form recoverable.';

COMMENT ON COLUMN social_wiring.leads.contato_norm IS
  'CANONICAL form of `contato`: E.164 (+5511994573387) for phones, lowercased '
  'for e-mail. Was bare digits with no country code before migration 037, which '
  'never compared equal to a Meta campaign phone. Maintained by '
  'canonicalize_lead_contato_trigger for EVERY write path. NULL means the value '
  'could not be canonicalized without guessing -- see `contato` for what arrived.';

COMMENT ON COLUMN social_wiring.meta_ads_leads.phone IS
  'Canonical E.164. Meta already delivers this shape; the trigger normalizes '
  'the ~8%% of rows that arrive malformed or without a country code. The '
  'original payload is preserved verbatim in `raw`.';

-- ----------------------------------------------------------------------------
-- B2. `normalize_phone` -- the DB runtime of the shared contract
-- ----------------------------------------------------------------------------
-- Mirrors `noctusai_lib.primitives.phone.normalize_phone` and
-- `@noctusai/lib/phone`'s `normalizePhone` case for case. IMMUTABLE so it can
-- be used in an index or a generated column later without a rewrite.
--
-- Returns NULL for anything it cannot resolve WITHOUT GUESSING. Never invents
-- a digit -- see the header.
CREATE OR REPLACE FUNCTION social_wiring.normalize_phone(
  p_raw TEXT,
  p_country_code TEXT DEFAULT '55'
) RETURNS TEXT
  LANGUAGE plpgsql
  IMMUTABLE
  SET search_path TO 'pg_catalog'
AS $$
DECLARE
  v_text   TEXT;
  v_digits TEXT;
  v_rest   TEXT;
  v_intl   BOOLEAN;
  -- 2-digit DDD 11-99, then a 9-digit mobile starting with 9 or an 8-digit
  -- landline starting 2-5. ANATEL reserves the leading 9 for mobile.
  c_national CONSTANT TEXT := '^[1-9][0-9](9[0-9]{8}|[2-5][0-9]{7})$';
BEGIN
  IF p_raw IS NULL THEN RETURN NULL; END IF;
  v_text := btrim(p_raw);
  IF v_text = '' THEN RETURN NULL; END IF;

  v_intl := left(v_text, 1) = '+';
  v_digits := regexp_replace(v_text, '\D', '', 'g');
  IF v_digits = '' THEN RETURN NULL; END IF;

  IF v_intl THEN
    -- An explicit "+" asserts a full international number. A +55 claim is one
    -- we CAN check, so a malformed Brazilian number is still refused.
    IF left(v_digits, length(p_country_code)) = p_country_code THEN
      v_rest := substr(v_digits, length(p_country_code) + 1);
      RETURN CASE WHEN v_rest ~ c_national THEN '+' || v_digits ELSE NULL END;
    END IF;
    -- Foreign: no per-country plan, so the only honest check is the E.164
    -- envelope (8..15 digits).
    RETURN CASE
      WHEN length(v_digits) BETWEEN 8 AND 15 THEN '+' || v_digits
      ELSE NULL
    END;
  END IF;

  -- National form. A leading 0 is the long-distance trunk prefix, never part
  -- of the number.
  v_digits := regexp_replace(v_digits, '^0+', '');
  IF v_digits = '' THEN RETURN NULL; END IF;

  -- Already country-coded (a bare WAHA chat id, or a row an earlier pass
  -- normalized). Detected by SHAPE, not length: a bare "11994573387" is
  -- DDD+mobile and must not lose its "11" to a prefix test, so only the
  -- reading that leaves a VALID national number behind is accepted.
  IF left(v_digits, length(p_country_code)) = p_country_code THEN
    v_rest := substr(v_digits, length(p_country_code) + 1);
    IF v_rest ~ c_national THEN
      RETURN '+' || v_digits;
    END IF;
  END IF;

  IF v_digits ~ c_national THEN
    RETURN '+' || p_country_code || v_digits;
  END IF;

  RETURN NULL;
END
$$;

COMMENT ON FUNCTION social_wiring.normalize_phone(TEXT, TEXT) IS
  'Canonical E.164 form, or NULL when the input cannot be resolved without '
  'guessing. One of THREE runtimes of one contract -- the others are '
  'noctusai_lib.primitives.phone and @noctusai/lib/phone. Migration 037 step B4 '
  'asserts they agree.';

-- ----------------------------------------------------------------------------
-- B3. The trigger -- the guarantee no write path can forget
-- ----------------------------------------------------------------------------
-- `contato` is NEVER touched here. The trigger derives `contato_norm` and
-- `contato_tipo` FROM it, which is the split the table was already built
-- around -- and it is what makes this backfill reversible with no extra
-- column: the original spelling is still sitting in `contato`.
CREATE OR REPLACE FUNCTION social_wiring.canonicalize_lead_contato()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
  v_value TEXT;
BEGIN
  v_value := btrim(COALESCE(NEW.contato, ''));

  IF v_value = '' THEN
    NEW.contato_norm := NULL;
    NEW.contato_tipo := 'desconhecido';
    RETURN NEW;
  END IF;

  IF v_value LIKE '%@%' THEN
    NEW.contato_norm := lower(v_value);
    NEW.contato_tipo := 'email';
    RETURN NEW;
  END IF;

  NEW.contato_norm := social_wiring.normalize_phone(v_value);

  IF NEW.contato_norm IS NOT NULL THEN
    NEW.contato_tipo := 'telefone';
  ELSIF length(regexp_replace(v_value, '\D', '', 'g')) >= 8 THEN
    -- Looks like a phone, is not canonicalizable. `contato_norm` stays NULL
    -- (nothing may key on a value we had to guess) but the TYPE is still
    -- `telefone`, because that is what it is -- and a phone filter that
    -- silently omits the malformed rows hides exactly the ones needing a fix.
    NEW.contato_tipo := 'telefone';
  ELSE
    NEW.contato_tipo := 'desconhecido';
  END IF;

  RETURN NEW;
END
$$;

-- `UPDATE OF contato` and not a bare `UPDATE`: re-deriving on every unrelated
-- PATCH is wasted work, and the derived columns cannot go stale while their
-- only input is unchanged.
DROP TRIGGER IF EXISTS canonicalize_lead_contato_trigger ON social_wiring.leads;
CREATE TRIGGER canonicalize_lead_contato_trigger
  BEFORE INSERT OR UPDATE OF contato ON social_wiring.leads
  FOR EACH ROW EXECUTE FUNCTION social_wiring.canonicalize_lead_contato();

-- meta_ads_leads has no norm/raw split and does not need one: `raw` (jsonb)
-- already holds Meta's original `field_data` payload verbatim, phone included.
-- So `phone` is normalized IN PLACE, and the original stays recoverable.
CREATE OR REPLACE FUNCTION social_wiring.canonicalize_meta_lead_phone()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
  v_canonical TEXT;
BEGIN
  IF NEW.phone IS NULL OR btrim(NEW.phone) = '' THEN
    RETURN NEW;
  END IF;

  v_canonical := social_wiring.normalize_phone(NEW.phone);
  IF v_canonical IS NOT NULL THEN
    NEW.phone := v_canonical;
  END IF;
  -- Unparseable: left EXACTLY as Meta sent it. A number we cannot canonicalize
  -- is one a human must look at; blanking it removes the only signal that it
  -- needs fixing.

  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS canonicalize_meta_lead_phone_trigger ON social_wiring.meta_ads_leads;
CREATE TRIGGER canonicalize_meta_lead_phone_trigger
  BEFORE INSERT OR UPDATE OF phone ON social_wiring.meta_ads_leads
  FOR EACH ROW EXECUTE FUNCTION social_wiring.canonicalize_meta_lead_phone();

-- ----------------------------------------------------------------------------
-- B4. Prove the SQL runtime agrees with the other two
-- ----------------------------------------------------------------------------
-- The SAME table of cases asserted by `seed/lib/backend/tests/test_phone.py`
-- and `seed/lib/frontend/src/phone.test.ts`. A drift between the three
-- implementations fails HERE, at apply time, rather than surfacing months
-- later as a number that saves differently than it displays.
DO $$
DECLARE
  v_case RECORD;
  v_got TEXT;
  v_failures TEXT := '';
BEGIN
  FOR v_case IN
    SELECT * FROM (VALUES
      -- every observed spelling collapses to one string
      ('+5511994573387',   '+5511994573387'),
      ('5511994573387',    '+5511994573387'),
      ('11994573387',      '+5511994573387'),
      ('11 99457.3387',    '+5511994573387'),
      ('(11) 99457-3387',  '+5511994573387'),
      ('+55 11 99457-3387','+5511994573387'),
      ('011994573387',     '+5511994573387'),
      ('  11994573387  ',  '+5511994573387'),
      -- 8-digit landline
      ('(11) 3216-5498',   '+551132165498'),
      -- DDD 55 is Santa Maria/RS, not the country code
      ('5532165498',       '+555532165498'),
      -- refusals: never guess
      ('+55115072510',     NULL),
      ('1199457',          NULL),
      ('119999999',        NULL),
      ('11 9999-9999',     NULL),
      ('não informado',    NULL),
      ('',                 NULL),
      ('   ',              NULL),
      (NULL,               NULL),
      ('0',                NULL),
      -- international
      ('+14155552671',     '+14155552671'),
      ('+5511507251',      NULL),
      ('+1234567890123456',NULL)
    ) AS t(input, expected)
  LOOP
    v_got := social_wiring.normalize_phone(v_case.input);
    IF v_got IS DISTINCT FROM v_case.expected THEN
      v_failures := v_failures || format(
        E'\n  normalize_phone(%L) = %L, expected %L',
        v_case.input, v_got, v_case.expected);
    END IF;
  END LOOP;

  IF v_failures <> '' THEN
    RAISE EXCEPTION
      'social_wiring.normalize_phone disagrees with noctusai_lib.primitives.phone: %',
      v_failures;
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- B5. Backfill -- re-derive every row through the trigger's own logic
-- ----------------------------------------------------------------------------
-- ~12,179 leads, of which 15 never had `contato_norm` at all (created through
-- `POST /api/leads`, which only the importer's path ever populated) and the
-- rest hold the old bare-digits form.
--
-- `contato` is NOT in the SET list: the arriving spelling is the thing we are
-- keeping. `updated_at` is not bumped either -- this is a format migration,
-- not a business edit, and moving 12k leads to the top of a "recently
-- changed" sort would be a lie about what happened to those records.
UPDATE social_wiring.leads l
   SET contato_norm = CASE
         WHEN btrim(l.contato) LIKE '%@%' THEN lower(btrim(l.contato))
         ELSE social_wiring.normalize_phone(l.contato)
       END,
       contato_tipo = CASE
         WHEN btrim(l.contato) LIKE '%@%' THEN 'email'
         WHEN social_wiring.normalize_phone(l.contato) IS NOT NULL THEN 'telefone'
         WHEN length(regexp_replace(l.contato, '\D', '', 'g')) >= 8 THEN 'telefone'
         ELSE 'desconhecido'
       END
 WHERE l.contato IS NOT NULL
   AND btrim(l.contato) <> '';

UPDATE social_wiring.leads
   SET contato_norm = NULL, contato_tipo = 'desconhecido'
 WHERE (contato IS NULL OR btrim(contato) = '')
   AND (contato_norm IS NOT NULL OR contato_tipo IS DISTINCT FROM 'desconhecido');

UPDATE social_wiring.meta_ads_leads m
   SET phone = social_wiring.normalize_phone(m.phone)
 WHERE m.phone IS NOT NULL
   AND social_wiring.normalize_phone(m.phone) IS NOT NULL
   AND social_wiring.normalize_phone(m.phone) IS DISTINCT FROM m.phone;

DO $$
DECLARE
  v_leads_phone INTEGER;
  v_leads_ok    INTEGER;
  v_meta_total  INTEGER;
  v_meta_ok     INTEGER;
BEGIN
  SELECT count(*) FILTER (WHERE contato_tipo = 'telefone'),
         count(*) FILTER (WHERE contato_tipo = 'telefone' AND contato_norm LIKE '+%')
    INTO v_leads_phone, v_leads_ok
    FROM social_wiring.leads;

  SELECT count(*), count(*) FILTER (WHERE phone LIKE '+%')
    INTO v_meta_total, v_meta_ok
    FROM social_wiring.meta_ads_leads WHERE phone IS NOT NULL;

  RAISE NOTICE
    '037/B5: leads -- %/% phone rows canonical; % left for a human (contato_norm NULL, original visible in contato)',
    v_leads_ok, v_leads_phone, v_leads_phone - v_leads_ok;
  RAISE NOTICE
    '037/B5: meta_ads_leads -- %/% canonical; % left as Meta sent them (original also in raw)',
    v_meta_ok, v_meta_total, v_meta_total - v_meta_ok;

  -- Deliberately a NOTICE, not an EXCEPTION. Unparseable numbers are a DATA
  -- problem, not a migration failure -- aborting would block the format change
  -- for every good row on account of the bad ones, and those rows end up no
  -- worse off than before this ran.
END
$$;

-- ----------------------------------------------------------------------------
-- B6. PostgREST must re-read the schema (new functions + triggers)
-- ----------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';
