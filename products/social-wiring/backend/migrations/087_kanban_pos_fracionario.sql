-- ============================================================================
-- Migration 087 — Persistent card ordering: fractional `kanban_pos`
--
-- WHY THIS EXISTS
-- ---------------
-- Dragging a card to reorder it inside a column did nothing. Two reasons, and
-- both had to go:
--
--   1. `PipelineBoard.onMove` early-returned on a same-column drop, so the
--      reorder never reached the API at all (fixed in the same commit).
--   2. `kanban_pos` was `integer DEFAULT 0` and NOTHING ever wrote it: all
--      1.850 open atendimentos sat at position 0, so the displayed order came
--      entirely from the `created_at` tiebreak. There was no saved order to
--      preserve — this migration creates one.
--
-- WHY `numeric` AND NOT `integer`
-- -------------------------------
-- A card's position is now the MIDPOINT of its two new neighbours, so a drag
-- is ONE update instead of renumbering the column. On an integer column the
-- midpoint of 1 and 2 rounds and the card lands on the wrong side of its
-- neighbour — silently, and only sometimes. `numeric` is arbitrary-precision
-- (not float), so repeated subdivision stays exact instead of drifting until
-- two positions compare equal.
--
-- The alternative — dense integers renumbered on every move — is 1.850 UPDATEs
-- per gesture on the intake column, plus a race that interleaves two people's
-- renumberings. Rejected on both counts.
--
-- NEW CARDS GO ON TOP
-- -------------------
-- `spawn_funil_card` gave every new card position 0. With ordering now live
-- that would bury a fresh lead in the middle of whatever operators had
-- arranged. It now takes `min(kanban_pos) - 1` of the destination stage, so a
-- new lead always lands ABOVE everything — the "newest first" behaviour asked
-- for — while anything a human dragged keeps exactly the spot they chose.
-- This replaces the force-sort-by-date approach: a forced sort would have made
-- the intake column the one place where dragging silently did nothing.
--
-- IDEMPOTENT: type changes are conditional, the backfill only touches rows
-- still at the default 0, and the function is CREATE OR REPLACE.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Widen the position columns to numeric.
-- ---------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimentos
  ALTER COLUMN kanban_pos TYPE numeric USING kanban_pos::numeric;

ALTER TABLE social_wiring.processos_venda
  ALTER COLUMN kanban_pos TYPE numeric USING kanban_pos::numeric;

-- ---------------------------------------------------------------------------
-- 2. Backfill a real order.
--
-- Every row is at 0, so ALL of them tie and the order is arbitrary-ish today.
-- Seed positions NEWEST-FIRST per stage, which is both what the intake column
-- is being asked to show and — since every open card currently sits in that
-- one stage — the only column this can affect.
--
-- Guarded on `kanban_pos = 0`: a re-run after people have dragged cards must
-- not wipe their arrangement. Rows that already carry a real position are left
-- alone.
-- ---------------------------------------------------------------------------
WITH ordenado AS (
  SELECT id,
         row_number() OVER (PARTITION BY etapa_id ORDER BY created_at DESC, id) AS n
    FROM social_wiring.atendimentos
   WHERE kanban_pos = 0
)
UPDATE social_wiring.atendimentos a
   SET kanban_pos = ordenado.n
  FROM ordenado
 WHERE a.id = ordenado.id;

WITH ordenado AS (
  SELECT id,
         row_number() OVER (PARTITION BY etapa_id ORDER BY created_at DESC, id) AS n
    FROM social_wiring.processos_venda
   WHERE kanban_pos = 0
)
UPDATE social_wiring.processos_venda p
   SET kanban_pos = ordenado.n
  FROM ordenado
 WHERE p.id = ordenado.id;

-- ---------------------------------------------------------------------------
-- 3. A new card lands on top of its stage.
--
-- Body is migration 034's verbatim, with only the position added — keeping the
-- diff to the one thing that changed, so a future reader can see that stage
-- resolution and the ON CONFLICT guard are untouched.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.spawn_funil_card()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'social_wiring', 'public'
AS $function$
DECLARE
  v_stage_id UUID;
  v_titulo   TEXT;
  v_pos      NUMERIC;
BEGIN
  PERFORM social_wiring.ensure_default_pipeline_stages(NEW.org_id);
  SELECT id INTO v_stage_id FROM social_wiring.pipeline_stages
   WHERE org_id = NEW.org_id AND pipeline = 'funil' AND ativo
   ORDER BY posicao, slug LIMIT 1;
  IF v_stage_id IS NULL THEN
    RAISE EXCEPTION 'spawn_funil_card: org % has no active funil stages', NEW.org_id;
  END IF;

  -- Above every card already in the stage. COALESCE covers the empty column.
  SELECT COALESCE(MIN(kanban_pos), 1) - 1 INTO v_pos
    FROM social_wiring.atendimentos
   WHERE org_id = NEW.org_id AND etapa_id = v_stage_id;

  IF TG_TABLE_NAME = 'leads' THEN
    v_titulo := COALESCE(NULLIF(trim(NEW.cliente_nome), ''), NEW.contato, 'Lead sem nome');
    INSERT INTO social_wiring.atendimentos (org_id, lead_id, etapa_id, titulo, kanban_pos)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo, v_pos) ON CONFLICT DO NOTHING;
  ELSE
    v_titulo := COALESCE(NULLIF(trim(NEW.full_name), ''), NEW.email, NEW.phone, 'Lead de campanha');
    INSERT INTO social_wiring.atendimentos (org_id, meta_ads_lead_id, etapa_id, titulo, kanban_pos)
    VALUES (NEW.org_id, NEW.id, v_stage_id, v_titulo, v_pos) ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END
$function$;

COMMENT ON COLUMN social_wiring.atendimentos.kanban_pos IS
  'Fractional position within the stage — smaller sorts higher. A drag stores '
  'the midpoint of its new neighbours (ONE update, never a column renumber). '
  'New cards get min()-1 so arrivals stack on top. Migration 087.';
