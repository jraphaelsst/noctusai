-- ============================================================================
-- Migration 272 -- social_wiring: Lais wave 5, Visitas (pre-scheduling)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md
--   section 7 (Wave 5) and section 17 (LGPD: CPF = hash + last 3 digits only).
--
--   lais_visitas_config  one row per org: the "Pre-agendamento de visita" drawer
--                        (separar_operacao + per-profile config: ativo, cpf_obrigatorio,
--                        min_dias/min_horas, max_dias, weekday grade).
--   lais_visitas         one visit request. `cpf_hash` (sha256 of the digits) and
--                        `cpf_final` (last 3 digits) are the ONLY CPF columns: the clear
--                        number is never stored. `agendamento_id` points at the
--                        atendimento_agendamentos row created on Confirmar; it stays NULL
--                        when the contato has no lead/card yet.
--
-- Guards: status vocabulary, fim > inicio, cpf shape, config is a JSON object, and ONE
-- live visit per (org, inicio) so two requests can never book the same slot.
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 267.
--
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 061 (atendimento_agendamentos), 267 (lais_contatos),
-- core 070. Applied by the tech-lead with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.lais_contatos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_contatos (migration 267) -- apply 267 first';
  END IF;
END
$guard$;

-- -- 1. lais_visitas_config -------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_visitas_config (
    org_id           uuid        PRIMARY KEY,
    separar_operacao boolean     NOT NULL DEFAULT false,
    config           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_visitas_config_objeto CHECK (jsonb_typeof(config) = 'object')
);

COMMENT ON TABLE social_wiring.lais_visitas_config IS
    'Per-org visit pre-scheduling config (migration 272, contract 7): config = {geral|compra|aluguel: '
    '{ativo, cpf_obrigatorio, min_dias, min_horas, max_dias, grade:{seg..dom:[{inicio,fim}]}}}.';

-- -- 2. lais_visitas --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_visitas (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid        NOT NULL,
    contato_id          uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    codigo_imovel       text,
    operacao            text,
    inicio              timestamptz NOT NULL,
    fim                 timestamptz NOT NULL,
    cpf_hash            text,
    cpf_final           text,
    status              text        NOT NULL DEFAULT 'solicitada',
    motivo_cancelamento text,
    agendamento_id      uuid        REFERENCES social_wiring.atendimento_agendamentos (id) ON DELETE SET NULL,
    responsavel_user_id uuid,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_visitas_status_valido
        CHECK (status IN ('solicitada', 'confirmada', 'remarcada', 'cancelada')),
    CONSTRAINT lais_visitas_fim_apos_inicio CHECK (fim > inicio),
    CONSTRAINT lais_visitas_cpf_formato
        CHECK ((cpf_hash IS NULL AND cpf_final IS NULL)
            OR (cpf_hash ~ '^[0-9a-f]{64}$' AND cpf_final ~ '^[0-9]{3}$'))
);

COMMENT ON TABLE social_wiring.lais_visitas IS
    'One visit request from Julia (migration 272, contract 7). CPF: hash + last 3 digits only (LGPD, contract 17).';

CREATE UNIQUE INDEX IF NOT EXISTS lais_visitas_slot_vivo_uq
    ON social_wiring.lais_visitas (org_id, inicio)
    WHERE status IN ('solicitada', 'confirmada', 'remarcada');
CREATE INDEX IF NOT EXISTS idx_lais_visitas_org_inicio
    ON social_wiring.lais_visitas (org_id, inicio);
CREATE INDEX IF NOT EXISTS idx_lais_visitas_contato
    ON social_wiring.lais_visitas (contato_id);

-- -- 3. RLS ------------------------------------------------------------------------
ALTER TABLE social_wiring.lais_visitas_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_visitas        ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_visitas_config_select_own_org" ON social_wiring.lais_visitas_config;
CREATE POLICY "lais_visitas_config_select_own_org" ON social_wiring.lais_visitas_config
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_visitas_config_service_role" ON social_wiring.lais_visitas_config;
CREATE POLICY "lais_visitas_config_service_role" ON social_wiring.lais_visitas_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_visitas_select_own_org" ON social_wiring.lais_visitas;
CREATE POLICY "lais_visitas_select_own_org" ON social_wiring.lais_visitas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_visitas_service_role" ON social_wiring.lais_visitas;
CREATE POLICY "lais_visitas_service_role" ON social_wiring.lais_visitas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 4. status_pagina: Lais > Visitas (copies whatsapp_chat, like 259) -----------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('lais_visitas', 'Lais — Visitas')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
