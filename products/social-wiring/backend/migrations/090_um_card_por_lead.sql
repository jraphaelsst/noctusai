-- ============================================================================
-- Migration 090 — ONE card per arrival, by construction
--
-- WHY THIS EXISTS
-- ---------------
-- A campaign lead produced TWO cards and a later sweep merged them. Migration
-- 034 put `spawn_funil_card` on BOTH `leads` and `meta_ads_leads`, and
-- `ingest_meta_lead` writes BOTH rows for every Meta lead — so every single
-- campaign arrival spawned a duplicate that `_collapse_atendimentos` then had
-- to mark `substituida_por` and hide.
--
-- The numbers say this was the normal path, not an edge case: all 1.399
-- `meta_ads_leads` rows have a matching `leads` row (ZERO orphans), and 695
-- cards have been collapsed. That is 695 rows created only to be undone, and
-- 695 windows in which the board showed a person twice — each with a null
-- `cliente_id`, so both opened the fallback lead modal instead of the person
-- card. Reported from production 2026-09-02.
--
-- Creating work and then repairing it is the wrong shape. The two rows are
-- not two people; they are two RECORDS OF ONE ARRIVAL, and `atendimentos`
-- already has a column for each (`lead_id`, `meta_ads_lead_id`). So the card
-- carries BOTH and is created once.
--
-- HOW: WHOEVER ARRIVES FIRST CREATES, THE SECOND ATTACHES
-- -------------------------------------------------------
-- `leads.meta_lead_id` (migration 041, unique per org) is the link between
-- the two tables, so either trigger can find the other's card:
--
--   * `meta_ads_leads` INSERT → is there already a card whose lead has this
--     `meta_lead_id`? Attach `meta_ads_lead_id` to it. Otherwise create.
--   * `leads` INSERT with `meta_lead_id` → is there already a card for that
--     meta lead? Attach `lead_id` to it. Otherwise create, carrying BOTH ids.
--
-- Order-independent on purpose. Today the webhook writes `meta_ads_leads`
-- first and `ingest_meta_lead` writes `leads` ~0.4s later, but the backfill
-- route replays existing meta rows the other way round, and neither ordering
-- is a guarantee worth encoding.
--
-- 🔴 THE COLLAPSE STAYS. `_collapse_atendimentos` still runs and is still
-- correct — it is now a BACKSTOP for the 695 historical pairs and for any
-- duplicate arriving by a path this trigger does not cover, rather than the
-- mechanism the normal path depends on. Removing it would strand that data.
-- This migration deliberately does NOT rewrite history: existing pairs keep
-- their `substituida_por` linkage and keep rendering as one card.
--
-- A single card carrying both FKs makes the union REAL instead of computed:
-- the board's select embeds `lead` and `campanha` off those columns, so the
-- card shows the person AND the campaign with no read-time folding.
--
-- IDEMPOTENT: CREATE OR REPLACE only. Triggers themselves are unchanged —
-- both still fire, they simply cooperate now.
-- ============================================================================

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
  END IF;

  -- ── No card yet — create exactly one, on top of the stage. ─────────────
  SELECT COALESCE(MIN(kanban_pos), 1) - 1 INTO v_pos
    FROM social_wiring.atendimentos
   WHERE org_id = NEW.org_id AND etapa_id = v_stage_id;

  IF TG_TABLE_NAME = 'leads' THEN
    v_titulo := COALESCE(NULLIF(trim(NEW.cliente_nome), ''), NEW.contato, 'Lead sem nome');
    -- Carries the campaign id too when the lead knows it, so the one card
    -- embeds both origins without any read-time folding.
    INSERT INTO social_wiring.atendimentos
           (org_id, lead_id, meta_ads_lead_id, etapa_id, titulo, kanban_pos)
    VALUES (NEW.org_id, NEW.id, NEW.meta_lead_id, v_stage_id, v_titulo, v_pos)
    ON CONFLICT DO NOTHING;
  ELSE
    v_titulo := COALESCE(NULLIF(trim(NEW.full_name), ''), NEW.email, NEW.phone, 'Lead de campanha');
    INSERT INTO social_wiring.atendimentos
           (org_id, meta_ads_lead_id, etapa_id, titulo, kanban_pos)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo, v_pos)
    ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END
$function$;

COMMENT ON FUNCTION social_wiring.spawn_funil_card() IS
  'Spawns the funil card for an arriving lead. Fires on BOTH `leads` and '
  '`meta_ads_leads`; whichever arrives first creates the card and the second '
  'ATTACHES its id to it, so one arrival is one card (migration 090). The '
  'collapse in clientes_service remains as a backstop for historical pairs.';
