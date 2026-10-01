-- ============================================================================
-- 180 — meta_ads_leads.codigo_imovel(+_norm): the imóvel a Meta lead is about
-- ============================================================================
-- Owner decision D1 (2026-10-01): a Meta lead carries its código in the form
-- answer `REF` (100% of 1,895 rows, e.g. `ONE9441`) and nothing ever read it.
--
-- Same shape as migration 062 (`leads.codigo_imovel_norm`): original spelling in
-- `codigo_imovel`, case-folded join key in `codigo_imovel_norm`, derived by a
-- trigger for EVERY write path. One deliberate extension over 062: when
-- `codigo_imovel` is blank the trigger fills it from `answers->>'REF'`, so a
-- Meta sync/webhook writer that only stores `answers` is correct by
-- construction — no ingest path can forget to copy it.
--
-- Forward-only, idempotent. Backfill touches only rows with a non-blank REF.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.meta_ads_leads
    ADD COLUMN IF NOT EXISTS codigo_imovel      TEXT,
    ADD COLUMN IF NOT EXISTS codigo_imovel_norm TEXT;

COMMENT ON COLUMN social_wiring.meta_ads_leads.codigo_imovel IS
    'Imóvel código as the lead form delivered it (answers->>''REF''). Original '
    'spelling; the join key is codigo_imovel_norm. Migration 180.';
COMMENT ON COLUMN social_wiring.meta_ads_leads.codigo_imovel_norm IS
    'upper(btrim(codigo_imovel)) — join key for imovel_registry.codigo_canonical. '
    'NULL = the lead carries no código (never "rejected"). Derived by trigger.';

CREATE OR REPLACE FUNCTION social_wiring.canonicalize_meta_lead_codigo_imovel()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
  v_value TEXT;
BEGIN
  v_value := btrim(COALESCE(NEW.codigo_imovel, ''));
  IF v_value = '' THEN
    v_value := btrim(COALESCE(NEW.answers ->> 'REF', ''));
    IF v_value <> '' THEN
      NEW.codigo_imovel := v_value;
    END IF;
  END IF;

  IF v_value = '' THEN
    NEW.codigo_imovel_norm := NULL;
  ELSE
    NEW.codigo_imovel_norm := upper(v_value);
  END IF;
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS canonicalize_meta_lead_codigo_imovel_trigger
    ON social_wiring.meta_ads_leads;
CREATE TRIGGER canonicalize_meta_lead_codigo_imovel_trigger
    BEFORE INSERT OR UPDATE OF codigo_imovel, answers ON social_wiring.meta_ads_leads
    FOR EACH ROW EXECUTE FUNCTION social_wiring.canonicalize_meta_lead_codigo_imovel();

-- Backfill: the trigger fires on this UPDATE (answers is in the column list),
-- so it fills codigo_imovel from REF and derives the norm.
UPDATE social_wiring.meta_ads_leads
   SET answers = answers
 WHERE btrim(COALESCE(answers ->> 'REF', '')) <> ''
   AND codigo_imovel_norm IS DISTINCT FROM upper(btrim(answers ->> 'REF'));

CREATE INDEX IF NOT EXISTS idx_sw_meta_ads_leads_org_codigo_norm
    ON social_wiring.meta_ads_leads (org_id, codigo_imovel_norm)
    WHERE codigo_imovel_norm IS NOT NULL;

-- Register every código we have now learned, exactly as `registrar_imovel`
-- does (origem_descoberta='lead', ativo_no_vista=FALSE; ON CONFLICT leaves a
-- catalog-known código untouched). SQL-feasible, so no Python backfill needed.
INSERT INTO social_wiring.imovel_registry (
    org_id, codigo_canonical, codigo_display, primeiro_visto_em,
    ativo_no_vista, origem_descoberta
)
SELECT m.org_id,
       m.codigo_imovel_norm,
       (array_agg(m.codigo_imovel ORDER BY COALESCE(m.created_time, m.created_at)))[1],
       min(COALESCE(m.created_time, m.created_at)),
       FALSE,
       'lead'
  FROM social_wiring.meta_ads_leads m
 WHERE m.codigo_imovel_norm IS NOT NULL
 GROUP BY m.org_id, m.codigo_imovel_norm
ON CONFLICT (org_id, codigo_canonical) DO NOTHING;

NOTIFY pgrst, 'reload schema';
