-- ============================================================================
-- Migration 240 — spawn_funil_card never drops a card silently
--
-- INCIDENT (prod, 2026-10-10): 6 real funil cards were lost with no signal.
--
-- `spawn_funil_card()` (fires on INSERT into `leads` and `meta_ads_leads`)
-- ended both INSERTs with `ON CONFLICT DO NOTHING`. The unique index
-- `uq_sw_atendimentos_meta_lead` was GLOBAL (meta_ads_lead_id alone) while the
-- trigger's merge lookup is org-scoped. A test left a ghost org's atendimento
-- holding a real `meta_ads_lead_id`; when the real org's lead was backfilled
-- the org-scoped lookup found nothing, the INSERT hit the global unique, and
-- DO NOTHING swallowed the conflict: no card, no error, nobody told.
-- Second shape (same org): the meta lead's card is already linked to a
-- DIFFERENT lead_id, so the `lead_id IS NULL` lookup misses and the INSERT is
-- dropped the same way.
--
-- FIX
--   1. The unique becomes per ORG: (org_id, meta_ads_lead_id). A card held by
--      another org can no longer block this org's card (shape 1 disappears).
--   2. `spawn_funil_card` has no DO NOTHING. The same-org collision is handled
--      explicitly and RECORDED:
--        * `leads` side: the card is still created (the person must not
--          vanish from the board) but WITHOUT the campaign link the other card
--          already owns — no duplicate under the unique;
--        * `meta_ads_leads` side: the arrival already has a card; nothing new
--          is created.
--      Either way a row lands in `social_wiring.funil_card_anomalias`
--      (queryable by ops, org-readable) and a WARNING is raised. Any OTHER
--      uniqueness violation now RAISES instead of vanishing.
--
-- WHY NOT RAISE EXCEPTION for the handled collision: the trigger runs inside
-- lead ingestion's transaction; raising would roll the lead back and the
-- webhook would retry into the same collision forever — legitimate lead data
-- lost to protect a bookkeeping edge. The anomaly row is the durable signal.
--
-- IDEMPOTENT: IF NOT EXISTS / IF EXISTS / CREATE OR REPLACE.
-- ============================================================================

SET search_path = social_wiring, public;

-- ─── 1. org-scoped unique (create new, then drop old) ──────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimentos_org_meta_lead
  ON social_wiring.atendimentos (org_id, meta_ads_lead_id)
  WHERE meta_ads_lead_id IS NOT NULL;

DROP INDEX IF EXISTS social_wiring.uq_sw_atendimentos_meta_lead;

-- ─── 2. visible signal ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.funil_card_anomalias (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                  UUID NOT NULL,
  tipo                    TEXT NOT NULL,
  origem                  TEXT NOT NULL,   -- trigger table: leads | meta_ads_leads
  lead_id                 UUID,
  meta_ads_lead_id        TEXT,
  atendimento_existente_id UUID,
  detalhe                 TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolvido_em            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sw_funil_card_anomalias_org_abertas
  ON social_wiring.funil_card_anomalias (org_id, created_at DESC)
  WHERE resolvido_em IS NULL;

ALTER TABLE social_wiring.funil_card_anomalias ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "funil_card_anomalias_select_own_org" ON social_wiring.funil_card_anomalias;
CREATE POLICY "funil_card_anomalias_select_own_org" ON social_wiring.funil_card_anomalias
  FOR SELECT TO authenticated
  USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "funil_card_anomalias_service_role" ON social_wiring.funil_card_anomalias;
CREATE POLICY "funil_card_anomalias_service_role" ON social_wiring.funil_card_anomalias
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── 3. the trigger function, without the silent DO NOTHING ────────────────
CREATE OR REPLACE FUNCTION social_wiring.spawn_funil_card()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'social_wiring', 'public'
AS $function$
DECLARE
  v_stage_id     UUID;
  v_titulo       TEXT;
  v_pos          NUMERIC;
  v_existente    UUID;
  v_meta_lead_id TEXT;
BEGIN
  PERFORM social_wiring.ensure_default_pipeline_stages(NEW.org_id);
  SELECT id INTO v_stage_id FROM social_wiring.pipeline_stages
   WHERE org_id = NEW.org_id AND pipeline = 'funil' AND ativo
   ORDER BY posicao, slug LIMIT 1;
  IF v_stage_id IS NULL THEN
    RAISE EXCEPTION 'spawn_funil_card: org % has no active funil stages', NEW.org_id;
  END IF;

  -- ── Does this arrival already have a card? ─────────────────────────────
  IF TG_TABLE_NAME = 'leads' THEN
    v_meta_lead_id := NEW.meta_lead_id;
    IF v_meta_lead_id IS NOT NULL THEN
      SELECT id INTO v_existente
        FROM social_wiring.atendimentos
       WHERE org_id = NEW.org_id
         AND meta_ads_lead_id = v_meta_lead_id
         AND lead_id IS NULL
       LIMIT 1;
      IF v_existente IS NOT NULL THEN
        -- The campaign half got here first. Attach, do NOT duplicate.
        UPDATE social_wiring.atendimentos
           SET lead_id = NEW.id,
               titulo  = COALESCE(NULLIF(btrim(NEW.cliente_nome), ''), titulo)
         WHERE id = v_existente;
        RETURN NEW;
      END IF;

      -- Same org, but the meta lead's card is already linked to ANOTHER lead.
      -- The unique (org_id, meta_ads_lead_id) forbids a second holder: keep
      -- this person on the board WITHOUT the campaign link, and say so.
      SELECT id INTO v_existente
        FROM social_wiring.atendimentos
       WHERE org_id = NEW.org_id
         AND meta_ads_lead_id = v_meta_lead_id
       LIMIT 1;
      IF v_existente IS NOT NULL THEN
        INSERT INTO social_wiring.funil_card_anomalias
               (org_id, tipo, origem, lead_id, meta_ads_lead_id, atendimento_existente_id, detalhe)
        VALUES (NEW.org_id, 'meta_lead_ja_ligado_a_outro_lead', TG_TABLE_NAME,
                NEW.id, v_meta_lead_id, v_existente,
                'card criado sem o vinculo de campanha: o meta lead ja pertence a outro card da org');
        RAISE WARNING 'spawn_funil_card: meta lead % already linked to card % (org %); card for lead % created without campaign link',
          v_meta_lead_id, v_existente, NEW.org_id, NEW.id;
        v_meta_lead_id := NULL;
      END IF;
    END IF;
  ELSE
    -- Firing on `meta_ads_leads`: the canonical lead may already exist
    -- (the backfill route replays meta rows whose `leads` row is present).
    SELECT a.id INTO v_existente
      FROM social_wiring.atendimentos a
      JOIN social_wiring.leads l ON l.id = a.lead_id
     WHERE a.org_id = NEW.org_id
       AND l.meta_lead_id = NEW.id::text
       AND a.meta_ads_lead_id IS NULL
     LIMIT 1;
    IF v_existente IS NOT NULL THEN
      UPDATE social_wiring.atendimentos
         SET meta_ads_lead_id = NEW.id
       WHERE id = v_existente;
      RETURN NEW;
    END IF;

    -- A card in this org already holds this meta lead: the arrival HAS a card,
    -- creating another is forbidden by the unique. Record it, do not drop it
    -- silently.
    SELECT id INTO v_existente
      FROM social_wiring.atendimentos
     WHERE org_id = NEW.org_id AND meta_ads_lead_id = NEW.id
     LIMIT 1;
    IF v_existente IS NOT NULL THEN
      INSERT INTO social_wiring.funil_card_anomalias
             (org_id, tipo, origem, meta_ads_lead_id, atendimento_existente_id, detalhe)
      VALUES (NEW.org_id, 'card_ja_existe_para_meta_lead', TG_TABLE_NAME,
              NEW.id, v_existente,
              'nenhum card novo: a org ja tem um card com este meta lead');
      RAISE WARNING 'spawn_funil_card: meta lead % already has card % in org %; none created',
        NEW.id, v_existente, NEW.org_id;
      RETURN NEW;
    END IF;
  END IF;

  -- ── No card yet — create exactly one, on top of the stage. ─────────────
  -- No ON CONFLICT: a violation that reaches here is unexpected and must be
  -- loud, never a silently missing card.
  SELECT COALESCE(MIN(kanban_pos), 1) - 1 INTO v_pos
    FROM social_wiring.atendimentos
   WHERE org_id = NEW.org_id AND etapa_id = v_stage_id;

  IF TG_TABLE_NAME = 'leads' THEN
    v_titulo := COALESCE(NULLIF(trim(NEW.cliente_nome), ''), NEW.contato, 'Lead sem nome');
    INSERT INTO social_wiring.atendimentos
           (org_id, lead_id, meta_ads_lead_id, etapa_id, titulo, kanban_pos)
    VALUES (NEW.org_id, NEW.id, v_meta_lead_id, v_stage_id, v_titulo, v_pos);
  ELSE
    v_titulo := COALESCE(NULLIF(trim(NEW.full_name), ''), NEW.email, NEW.phone, 'Lead de campanha');
    INSERT INTO social_wiring.atendimentos
           (org_id, meta_ads_lead_id, etapa_id, titulo, kanban_pos)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo, v_pos);
  END IF;
  RETURN NEW;
END
$function$;

COMMENT ON FUNCTION social_wiring.spawn_funil_card() IS
  'Spawns the funil card for an arriving lead (fires on `leads` and `meta_ads_leads`). '
  'First arrival creates, second attaches (090). No silent ON CONFLICT DO NOTHING (240): '
  'a same-org collision on the meta lead is recorded in funil_card_anomalias + WARNING; '
  'any other violation raises.';

-- Trigger function only: never callable through PostgREST /rpc/ with the
-- owner's rights. Triggers do not need EXECUTE at fire time.
REVOKE EXECUTE ON FUNCTION social_wiring.spawn_funil_card() FROM PUBLIC, anon, authenticated;
