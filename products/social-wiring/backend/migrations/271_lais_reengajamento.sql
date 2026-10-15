-- ============================================================================
-- Migration 271 -- social_wiring: Lais wave 4 "Reengajamento"
--                  (config padrao, reguas, tentativas) + status_pagina
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md
--   section 6 (wave 4) + specs/page-map-v2.md 59.0 a2 / 59.0b b2.
--
--   lais_reengajamento_config  one row per org: the two default tiers.
--                              minutos: every 5..60 min (step 5), any hour;
--                              horas: every 1..11 h, only 08-20 Sao Paulo.
--   lais_reguas                named re-engagement rulers (compra and/or aluguel);
--                              an ACTIVE regua must own >= 1 ACTIVE tentativa.
--   lais_regua_tentativas      <= 3 attempts per regua, by construction:
--                              ordem is CHECKed 1..3 and unique per regua.
--                              Each carries free `texto` (Julia may rewrite it) XOR a
--                              Cloud-API `template_id` (needs wave 12's transport).
--
-- The "active regua needs an active attempt" rule is a DB guard (two triggers) AND an
-- application 409, so a direct write cannot slip past the router.
--
-- RLS: select-own-org + service_role policy per table (pattern 267); writes go through
-- the backend service client only. NO SECURITY DEFINER function in this file.
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: core 070 (current_org_id_for), 014
-- (status_pagina). The tech-lead applies it with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'this migration requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

-- -- 1. lais_reengajamento_config -------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_reengajamento_config (
    org_id            uuid        PRIMARY KEY,
    minutos_ativo     boolean     NOT NULL DEFAULT false,
    minutos_intervalo integer     NOT NULL DEFAULT 5,
    horas_ativo       boolean     NOT NULL DEFAULT false,
    horas_intervalo   integer     NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_reeng_minutos_intervalo_valido
        CHECK (minutos_intervalo BETWEEN 5 AND 60 AND minutos_intervalo % 5 = 0),
    CONSTRAINT lais_reeng_horas_intervalo_valido
        CHECK (horas_intervalo BETWEEN 1 AND 11)
);

COMMENT ON TABLE social_wiring.lais_reengajamento_config IS
    'Default re-engagement tiers of an org (migration 271, page-map 59.0 a2): minutes (5..60 step 5, any hour) '
    'and hours (1..11, only 08-20 Sao Paulo).';

-- -- 2. lais_reguas -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_reguas (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    nome       text        NOT NULL,
    ativa      boolean     NOT NULL DEFAULT false,
    compra     boolean     NOT NULL DEFAULT false,
    aluguel    boolean     NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_reguas_nome_valido CHECK (length(btrim(nome)) BETWEEN 1 AND 80)
);

COMMENT ON TABLE social_wiring.lais_reguas IS
    'Re-engagement reguas (migration 271, page-map 59.0b b2). An active regua owns >= 1 active tentativa '
    '(trigger lais_regua_ativa_exige_tentativa).';

CREATE INDEX IF NOT EXISTS idx_lais_reguas_org ON social_wiring.lais_reguas (org_id, created_at);

-- -- 3. lais_regua_tentativas ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_regua_tentativas (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    regua_id       uuid        NOT NULL REFERENCES social_wiring.lais_reguas (id) ON DELETE CASCADE,
    ordem          integer     NOT NULL,
    espera_valor   integer     NOT NULL DEFAULT 1,
    espera_unidade text        NOT NULL DEFAULT 'dias',
    texto          text,
    template_id    uuid,
    ativa          boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_regua_tentativas_ordem_1_a_3 CHECK (ordem BETWEEN 1 AND 3),
    CONSTRAINT lais_regua_tentativas_espera_valida CHECK (espera_valor BETWEEN 1 AND 999),
    CONSTRAINT lais_regua_tentativas_unidade_valida CHECK (espera_unidade IN ('minutos', 'horas', 'dias')),
    CONSTRAINT lais_regua_tentativas_texto_ou_template CHECK (
        num_nonnulls(texto, template_id) = 1 AND (texto IS NULL OR length(btrim(texto)) BETWEEN 1 AND 1024)
    )
);

COMMENT ON TABLE social_wiring.lais_regua_tentativas IS
    'Attempts of a regua (migration 271): at most 3 (ordem 1..3, unique per regua); free `texto` '
    '(Julia may rewrite) XOR a Cloud-API `template_id`.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_regua_tentativas_ordem_uq
    ON social_wiring.lais_regua_tentativas (regua_id, ordem);

-- -- 4. the active-regua guard (two triggers; no SECURITY DEFINER) ------------------------
CREATE OR REPLACE FUNCTION social_wiring.lais_regua_ativa_exige_tentativa_fn() RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $fn$
BEGIN
  IF NEW.ativa AND NOT EXISTS (
    SELECT 1 FROM social_wiring.lais_regua_tentativas t WHERE t.regua_id = NEW.id AND t.ativa
  ) THEN
    RAISE EXCEPTION 'an active regua needs at least one active tentativa'
      USING ERRCODE = '23514', CONSTRAINT = 'lais_regua_ativa_exige_tentativa_fn';
  END IF;
  RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS lais_regua_ativa_exige_tentativa ON social_wiring.lais_reguas;
CREATE TRIGGER lais_regua_ativa_exige_tentativa
    BEFORE INSERT OR UPDATE OF ativa ON social_wiring.lais_reguas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.lais_regua_ativa_exige_tentativa_fn();

CREATE OR REPLACE FUNCTION social_wiring.lais_regua_ultima_tentativa_ativa_fn() RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $fn$
BEGIN
  -- only a change that REMOVES an active attempt from an ACTIVE regua can break the invariant;
  -- a regua being deleted (cascade) is already gone when its attempts are visited.
  IF OLD.ativa
     AND (TG_OP = 'DELETE' OR NOT NEW.ativa OR NEW.regua_id IS DISTINCT FROM OLD.regua_id)
     AND EXISTS (SELECT 1 FROM social_wiring.lais_reguas r WHERE r.id = OLD.regua_id AND r.ativa)
     AND NOT EXISTS (
       SELECT 1 FROM social_wiring.lais_regua_tentativas t
        WHERE t.regua_id = OLD.regua_id AND t.ativa AND t.id <> OLD.id
     ) THEN
    RAISE EXCEPTION 'the last active tentativa of an active regua cannot be removed'
      USING ERRCODE = '23514', CONSTRAINT = 'lais_regua_ultima_tentativa_ativa_fn';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS lais_regua_ultima_tentativa_ativa ON social_wiring.lais_regua_tentativas;
CREATE TRIGGER lais_regua_ultima_tentativa_ativa
    BEFORE UPDATE OF ativa, regua_id OR DELETE ON social_wiring.lais_regua_tentativas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.lais_regua_ultima_tentativa_ativa_fn();

-- -- 5. RLS: select own org + service_role (writes through the backend only) --------------
ALTER TABLE social_wiring.lais_reengajamento_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_reguas               ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_regua_tentativas     ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_reengajamento_config_select_own_org" ON social_wiring.lais_reengajamento_config;
CREATE POLICY "lais_reengajamento_config_select_own_org" ON social_wiring.lais_reengajamento_config
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_reengajamento_config_service_role" ON social_wiring.lais_reengajamento_config;
CREATE POLICY "lais_reengajamento_config_service_role" ON social_wiring.lais_reengajamento_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_reguas_select_own_org" ON social_wiring.lais_reguas;
CREATE POLICY "lais_reguas_select_own_org" ON social_wiring.lais_reguas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_reguas_service_role" ON social_wiring.lais_reguas;
CREATE POLICY "lais_reguas_service_role" ON social_wiring.lais_reguas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_regua_tentativas_select_own_org" ON social_wiring.lais_regua_tentativas;
CREATE POLICY "lais_regua_tentativas_select_own_org" ON social_wiring.lais_regua_tentativas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_regua_tentativas_service_role" ON social_wiring.lais_regua_tentativas;
CREATE POLICY "lais_regua_tentativas_service_role" ON social_wiring.lais_regua_tentativas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 6. status_pagina: Lais > Reengajamento (copies whatsapp_chat's status, as 259 does) ----
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_reengajamento', 'Lais — Reengajamento')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
