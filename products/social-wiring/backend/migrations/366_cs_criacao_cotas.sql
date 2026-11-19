-- ============================================================================
-- Migration 366 · social_wiring: CoreStudio criação pipeline, M-E -- per-org vendor quota + month-to-date spend
-- ============================================================================
-- WHY
-- ---
-- Spec: criacao-pipeline-contract.md sections 2 (M-E), 5 (limits), 10.5 (owner: US$15 per month per org by default,
-- editable in the UI by org admins). Vendor credits (ElevenLabs / HeyGen / LLM) are real money; a batch of N cards must not
-- run away. The worker pre-flights each paid step against the quota and, over it, fails the step `falhou(cota)` visibly
-- on the card (363's RPC also writes `cota_excedida`) -- never a silent skip.
--
--   * cs_criacao_cotas          -- one row per org (org_id PK): limite_usd_mes (default 15), updated_by / updated_at.
--                                  An org with no row is on the default (cs_criacao_cota_estado reads it that way).
--   * cs_criacao_cotas_eventos  -- append-only: EVERY change (first set or edit) is an event (cota_alterada) with who,
--                                  when, from -> to, written by an AFTER trigger in the same transaction (EOA).
--   * cs_criacao_gasto_mes      -- view: per org per calendar month (America/Sao_Paulo) the cost summed from the
--                                  cs_criacao_jobs ledger, plus how many finished steps carried no cost (unmeasured stays
--                                  visible, never folded into zero).
--   * cs_criacao_cota_estado(org) -- the pre-flight read: {limite_usd_mes, gasto_usd_mes, restante_usd, passos_sem_custo}.
--
-- Records -> metrics: spend vs quota per org per month, quota changes (who/when/how much), quota refusals
-- (cota_excedida events, falhou/cota steps). Backward compatible with the previous image: NEW objects only.
-- Tier: org (service-only grants; admin edits go through the backend). FORWARD-ONLY, IDEMPOTENT. Requires 363.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_criacao_jobs') IS NULL THEN
    RAISE EXCEPTION 'Migration 366 requires cs_criacao_jobs (363) -- apply it first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. the quota
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_criacao_cotas (
    org_id          UUID PRIMARY KEY REFERENCES public.organizations (id) ON DELETE CASCADE,
    limite_usd_mes  NUMERIC(10, 2) NOT NULL DEFAULT 15,
    updated_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_criacao_cotas_limite_check CHECK (limite_usd_mes >= 0 AND limite_usd_mes <= 100000)
);

-- ----------------------------------------------------------------------------
-- 2. every change is an event (append-only; no FK: the history outlives the org row)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_criacao_cotas_eventos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    tipo          TEXT NOT NULL DEFAULT 'cota_alterada',
    limite_de     NUMERIC(10, 2),
    limite_para   NUMERIC(10, 2) NOT NULL,
    ator_id       UUID,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_criacao_cotas_eventos_tipo_check CHECK (tipo IN ('cota_alterada'))
);
CREATE INDEX IF NOT EXISTS cs_criacao_cotas_eventos_org_idx ON social_wiring.cs_criacao_cotas_eventos (org_id, criado_em);

CREATE OR REPLACE FUNCTION social_wiring.cs_criacao_cotas_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'cs_criacao_cotas_eventos_imutavel: cs_criacao_cotas_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$;
DROP TRIGGER IF EXISTS cs_criacao_cotas_eventos_imutavel ON social_wiring.cs_criacao_cotas_eventos;
CREATE TRIGGER cs_criacao_cotas_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_criacao_cotas_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_criacao_cotas_eventos_imutavel();

CREATE OR REPLACE FUNCTION social_wiring.cs_criacao_cotas_evento()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO social_wiring.cs_criacao_cotas_eventos (org_id, limite_de, limite_para, ator_id)
        VALUES (NEW.org_id, NULL, NEW.limite_usd_mes, NEW.updated_by);
    ELSIF NEW.limite_usd_mes IS DISTINCT FROM OLD.limite_usd_mes THEN
        INSERT INTO social_wiring.cs_criacao_cotas_eventos (org_id, limite_de, limite_para, ator_id)
        VALUES (NEW.org_id, OLD.limite_usd_mes, NEW.limite_usd_mes, NEW.updated_by);
    END IF;
    RETURN NULL;
END;
$$;
REVOKE ALL ON FUNCTION social_wiring.cs_criacao_cotas_evento() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_criacao_cotas_eventos_imutavel() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS cs_criacao_cotas_evento ON social_wiring.cs_criacao_cotas;
CREATE TRIGGER cs_criacao_cotas_evento
    AFTER INSERT OR UPDATE ON social_wiring.cs_criacao_cotas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_criacao_cotas_evento();

-- ----------------------------------------------------------------------------
-- 3. month-to-date spend, from the ledger
-- ----------------------------------------------------------------------------
-- A finished step spent its vendor cost whether it succeeded or failed; a step with no measured cost is COUNTED, not
-- folded into zero. The month is the Brazilian calendar month of terminado_em.
CREATE OR REPLACE VIEW social_wiring.cs_criacao_gasto_mes WITH (security_invoker = true) AS
SELECT j.org_id,
       (date_trunc('month', j.terminado_em AT TIME ZONE 'America/Sao_Paulo'))::date AS mes,
       COALESCE(sum(j.custo_usd), 0)::numeric(14, 6) AS custo_usd,
       COALESCE(sum(j.custo_brl), 0)::numeric(14, 6) AS custo_brl,
       count(*) AS passos,
       count(*) FILTER (WHERE j.custo_usd IS NULL) AS passos_sem_custo
  FROM social_wiring.cs_criacao_jobs j
 WHERE j.terminado_em IS NOT NULL AND j.status IN ('concluido', 'falhou')
 GROUP BY j.org_id, (date_trunc('month', j.terminado_em AT TIME ZONE 'America/Sao_Paulo'))::date;

CREATE OR REPLACE FUNCTION social_wiring.cs_criacao_cota_estado(p_org UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
    SELECT jsonb_build_object(
        'limite_usd_mes', l.limite,
        'gasto_usd_mes', COALESCE(g.custo_usd, 0),
        'restante_usd', l.limite - COALESCE(g.custo_usd, 0),
        'passos_sem_custo', COALESCE(g.passos_sem_custo, 0))
      FROM (SELECT COALESCE((SELECT c.limite_usd_mes FROM social_wiring.cs_criacao_cotas c WHERE c.org_id = p_org), 15) AS limite) l
      LEFT JOIN social_wiring.cs_criacao_gasto_mes g
        ON g.org_id = p_org AND g.mes = (date_trunc('month', now() AT TIME ZONE 'America/Sao_Paulo'))::date;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_criacao_cota_estado(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_criacao_cota_estado(UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- 4. RLS + grants (service-only), tiers
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_criacao_cotas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_criacao_cotas_service_role" ON social_wiring.cs_criacao_cotas;
CREATE POLICY "cs_criacao_cotas_service_role" ON social_wiring.cs_criacao_cotas FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_criacao_cotas FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE social_wiring.cs_criacao_cotas TO service_role;

ALTER TABLE social_wiring.cs_criacao_cotas_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_criacao_cotas_eventos_service_role" ON social_wiring.cs_criacao_cotas_eventos;
CREATE POLICY "cs_criacao_cotas_eventos_service_role" ON social_wiring.cs_criacao_cotas_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_criacao_cotas_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_criacao_cotas_eventos TO service_role;

REVOKE ALL ON social_wiring.cs_criacao_gasto_mes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON social_wiring.cs_criacao_gasto_mes TO service_role;

COMMENT ON TABLE social_wiring.cs_criacao_cotas IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_criacao_cotas_eventos IS 'tier:org';
COMMENT ON VIEW social_wiring.cs_criacao_gasto_mes IS 'tier:org';
