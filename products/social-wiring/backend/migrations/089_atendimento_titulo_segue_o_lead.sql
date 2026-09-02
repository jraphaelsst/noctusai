-- ============================================================================
-- Migration 089 — A card's title follows its lead's name
--
-- WHY THIS EXISTS
-- ---------------
-- `spawn_funil_card` (migration 034) names the card at INSERT and nothing ever
-- revisits it. A lead created without a name gets the literal placeholder
-- "Lead sem nome"; when the operator types the name in a minute later, the
-- lead is correct and the CARD still says "Lead sem nome" forever.
--
-- Reported from production 2026-09-02: `José Roberto` was created empty and
-- completed 27 minutes later. The board showed "Lead sem nome" beside his
-- phone number while his lead record held his actual name.
--
-- 🔴 ONLY WHILE THE TITLE IS STILL THE PLACEHOLDER.
--
-- `atendimentos.titulo` is editable by hand (the card dialog writes it), so a
-- trigger that always mirrored the lead would silently revert an operator's
-- rename every time anything touched the lead row. The rule is therefore the
-- same fill-if-empty contract the contact columns use: a title a human chose
-- outranks a derived one and is never overwritten.
--
-- The placeholders are matched literally because they ARE literals in
-- `spawn_funil_card` — a card whose title equals one of them is provably
-- still unnamed, never a name someone chose.
--
-- IDEMPOTENT: CREATE OR REPLACE + DROP TRIGGER IF EXISTS.
-- ============================================================================

CREATE OR REPLACE FUNCTION social_wiring.refresh_atendimento_titulo()
  RETURNS trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'social_wiring', 'public'
AS $function$
DECLARE
  v_titulo TEXT;
BEGIN
  v_titulo := COALESCE(NULLIF(btrim(NEW.cliente_nome), ''), NEW.contato);
  IF v_titulo IS NULL THEN
    RETURN NEW;  -- nothing better to offer than the placeholder already there
  END IF;

  UPDATE social_wiring.atendimentos
     SET titulo = v_titulo
   WHERE lead_id = NEW.id
     AND org_id = NEW.org_id
     -- Never clobber a title a person chose.
     AND (titulo IS NULL
          OR btrim(titulo) = ''
          OR titulo = 'Lead sem nome'
          OR titulo = 'Lead de campanha'
          OR titulo = OLD.contato);
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS trg_refresh_atendimento_titulo ON social_wiring.leads;

CREATE TRIGGER trg_refresh_atendimento_titulo
  AFTER UPDATE OF cliente_nome, contato ON social_wiring.leads
  FOR EACH ROW
  WHEN (
    NEW.cliente_nome IS DISTINCT FROM OLD.cliente_nome
    OR NEW.contato IS DISTINCT FROM OLD.contato
  )
  EXECUTE FUNCTION social_wiring.refresh_atendimento_titulo();

-- Repair the cards already stuck on a placeholder whose lead has since been
-- named. Same guard: only placeholders are touched.
UPDATE social_wiring.atendimentos a
   SET titulo = COALESCE(NULLIF(btrim(l.cliente_nome), ''), l.contato)
  FROM social_wiring.leads l
 WHERE a.lead_id = l.id
   AND COALESCE(NULLIF(btrim(l.cliente_nome), ''), l.contato) IS NOT NULL
   AND (a.titulo IS NULL OR btrim(a.titulo) = '' OR a.titulo = 'Lead sem nome');
