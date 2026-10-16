-- ============================================================================
-- Migration 275 -- social_wiring: Lais wave 12 "Cloud-API pages"
--                  (transport per connection, Modelos, Disparos, Atualizacao de imoveis)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md
--   section 14 (wave 12) + 17 (owners opt-out) + 0 / A6 (WAHA free text is NEVER a mass send).
--
--   whatsapp_connections.transporte  waha | cloud (default waha) + the Cloud ids (phone number / WABA).
--   lais_modelos                     Meta message templates: 8 categories, body <= 1024, status
--                                    rascunho -> enviado_meta -> aprovado | rejeitado.
--   lais_disparos                    mass sends: remarketing | atualizacao_anuncios, a segment, a modelo.
--   lais_disparo_alvos               one row per target, status flow
--                                    pendente -> enviado -> respondido -> enviado_sw | erro.
--   lais_proprietarios_contatos      owners contacted to refresh their listings; "parar" opt-out honoured.
--
-- Everything can be created/saved/scheduled; the DISPATCH is gated in the application (409
-- transporte_indisponivel while the connection is not Cloud). RLS: select-own-org + service_role per
-- table (pattern 267); writes go through the backend service client. NO SECURITY DEFINER function.
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: core 070 (current_org_id_for), 014 (status_pagina),
-- 258 (whatsapp_connections Julia columns), 267 (lais_contatos).
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
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'this migration requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

-- -- 1. transport per connection ---------------------------------------------------------
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS transporte text NOT NULL DEFAULT 'waha';
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS cloud_phone_number_id text;
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS cloud_waba_id text;

ALTER TABLE social_wiring.whatsapp_connections
    DROP CONSTRAINT IF EXISTS whatsapp_connections_transporte_valido;
ALTER TABLE social_wiring.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_transporte_valido CHECK (transporte IN ('waha', 'cloud'));

COMMENT ON COLUMN social_wiring.whatsapp_connections.transporte IS
    'waha (default) or cloud (Meta Cloud API, migration 275). Only cloud may dispatch templates / mass sends; '
    'for cloud the encrypted api_key holds the Meta access token.';

-- -- 2. lais_modelos -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_modelos (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid        NOT NULL,
    nome             text        NOT NULL,
    categoria        text        NOT NULL DEFAULT 'outros',
    corpo            text        NOT NULL,
    parametros       jsonb       NOT NULL DEFAULT '[]'::jsonb,
    idioma           text        NOT NULL DEFAULT 'pt_BR',
    status           text        NOT NULL DEFAULT 'rascunho',
    meta_template_id text,
    motivo_rejeicao  text,
    created_by       uuid,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_modelos_nome_valido CHECK (length(btrim(nome)) BETWEEN 1 AND 80),
    CONSTRAINT lais_modelos_categoria_valida CHECK (categoria IN (
        'administrativo', 'campanha', 'cobranca', 'documentacao',
        'primeiro_contato', 'reativacao', 'visita', 'outros')),
    CONSTRAINT lais_modelos_corpo_valido CHECK (length(btrim(corpo)) BETWEEN 1 AND 1024),
    CONSTRAINT lais_modelos_parametros_lista CHECK (jsonb_typeof(parametros) = 'array'),
    CONSTRAINT lais_modelos_status_valido CHECK (status IN ('rascunho', 'enviado_meta', 'aprovado', 'rejeitado'))
);

COMMENT ON TABLE social_wiring.lais_modelos IS
    'Message templates (migration 275, contract 14 / page-map 59.0 a4): body <= 1024, parameters from the '
    '10-parameter registry (derived from the body), status rascunho|enviado_meta|aprovado|rejeitado.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_modelos_org_nome_uq
    ON social_wiring.lais_modelos (org_id, lower(nome));

-- -- 3. lais_disparos ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_disparos (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    nome           text        NOT NULL,
    tipo           text        NOT NULL DEFAULT 'remarketing',
    segmento       text        NOT NULL,
    modelo_id      uuid        NOT NULL REFERENCES social_wiring.lais_modelos (id) ON DELETE RESTRICT,
    connection_id  uuid,
    status         text        NOT NULL DEFAULT 'rascunho',
    agendado_para  timestamptz,
    total_alvos    integer     NOT NULL DEFAULT 0,
    disparado_at   timestamptz,
    created_by     uuid,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_disparos_nome_valido CHECK (length(btrim(nome)) BETWEEN 1 AND 80),
    CONSTRAINT lais_disparos_tipo_valido CHECK (tipo IN ('remarketing', 'atualizacao_anuncios')),
    CONSTRAINT lais_disparos_segmento_valido CHECK (segmento IN ('leads_3_15', 'leads_7_30', 'proprietarios')),
    CONSTRAINT lais_disparos_status_valido CHECK (status IN (
        'rascunho', 'agendado', 'enviando', 'enviado', 'cancelado', 'erro')),
    CONSTRAINT lais_disparos_tipo_segmento CHECK (
        (tipo = 'atualizacao_anuncios') = (segmento = 'proprietarios')),
    CONSTRAINT lais_disparos_agendado_exige_data CHECK (status <> 'agendado' OR agendado_para IS NOT NULL),
    CONSTRAINT lais_disparos_total_nao_negativo CHECK (total_alvos >= 0)
);

COMMENT ON TABLE social_wiring.lais_disparos IS
    'Mass sends (migration 275, contract 14): remarketing | atualizacao_anuncios, a segment, an approved modelo. '
    'A send is capped at 15 % of the org month volume (application guard).';

CREATE INDEX IF NOT EXISTS idx_lais_disparos_org_status ON social_wiring.lais_disparos (org_id, status, created_at DESC);

-- -- 4. lais_proprietarios_contatos ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_proprietarios_contatos (
    id                 uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid          NOT NULL,
    nome               text,
    telefone           text          NOT NULL,
    imovel_codigo      text          NOT NULL,
    opt_out            boolean       NOT NULL DEFAULT false,
    opt_out_at         timestamptz,
    status_confirmado  text,
    preco_confirmado   numeric(14,2),
    confirmado_at      timestamptz,
    ultimo_contato_at  timestamptz,
    created_at         timestamptz   NOT NULL DEFAULT now(),
    updated_at         timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT lais_proprietarios_telefone_valido CHECK (telefone ~ '^[0-9]{10,15}$'),
    CONSTRAINT lais_proprietarios_codigo_valido CHECK (length(btrim(imovel_codigo)) BETWEEN 1 AND 60),
    CONSTRAINT lais_proprietarios_opt_out_coerente CHECK (opt_out = (opt_out_at IS NOT NULL)),
    CONSTRAINT lais_proprietarios_preco_positivo CHECK (preco_confirmado IS NULL OR preco_confirmado > 0)
);

COMMENT ON TABLE social_wiring.lais_proprietarios_contatos IS
    'Owners contacted to refresh a listing (migration 275, contract 14 / 17). LGPD: an owner who answers '
    '"parar" is opted out (opt_out + opt_out_at, never contacted again); Cloud templates only.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_proprietarios_org_tel_imovel_uq
    ON social_wiring.lais_proprietarios_contatos (org_id, telefone, imovel_codigo);

-- -- 5. lais_disparo_alvos ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_disparo_alvos (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid        NOT NULL,
    disparo_id       uuid        NOT NULL REFERENCES social_wiring.lais_disparos (id) ON DELETE CASCADE,
    contato_id       uuid        REFERENCES social_wiring.lais_contatos (id) ON DELETE SET NULL,
    proprietario_id  uuid        REFERENCES social_wiring.lais_proprietarios_contatos (id) ON DELETE SET NULL,
    telefone         text        NOT NULL,
    status           text        NOT NULL DEFAULT 'pendente',
    erro             text,
    message_id       text,
    enviado_at       timestamptz,
    respondido_at    timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_alvos_status_valido CHECK (status IN ('pendente', 'enviado', 'respondido', 'enviado_sw', 'erro')),
    CONSTRAINT lais_alvos_um_destino CHECK (num_nonnulls(contato_id, proprietario_id) <= 1),
    CONSTRAINT lais_alvos_telefone_valido CHECK (telefone ~ '^[0-9]{10,15}$')
);

COMMENT ON TABLE social_wiring.lais_disparo_alvos IS
    'Targets of a disparo (migration 275), status flow pendente -> enviado -> respondido -> enviado_sw | erro. '
    'A reply re-enters Julia''s normal lead path.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_alvos_disparo_telefone_uq
    ON social_wiring.lais_disparo_alvos (disparo_id, telefone);
CREATE INDEX IF NOT EXISTS idx_lais_alvos_org_telefone
    ON social_wiring.lais_disparo_alvos (org_id, telefone, enviado_at DESC);

-- -- 6. RLS: select own org + service_role (writes through the backend only) ----------------------------------
ALTER TABLE social_wiring.lais_modelos                ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_disparos               ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_disparo_alvos          ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_proprietarios_contatos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_modelos_select_own_org" ON social_wiring.lais_modelos;
CREATE POLICY "lais_modelos_select_own_org" ON social_wiring.lais_modelos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_modelos_service_role" ON social_wiring.lais_modelos;
CREATE POLICY "lais_modelos_service_role" ON social_wiring.lais_modelos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_disparos_select_own_org" ON social_wiring.lais_disparos;
CREATE POLICY "lais_disparos_select_own_org" ON social_wiring.lais_disparos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_disparos_service_role" ON social_wiring.lais_disparos;
CREATE POLICY "lais_disparos_service_role" ON social_wiring.lais_disparos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_disparo_alvos_select_own_org" ON social_wiring.lais_disparo_alvos;
CREATE POLICY "lais_disparo_alvos_select_own_org" ON social_wiring.lais_disparo_alvos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_disparo_alvos_service_role" ON social_wiring.lais_disparo_alvos;
CREATE POLICY "lais_disparo_alvos_service_role" ON social_wiring.lais_disparo_alvos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_proprietarios_contatos_select_own_org" ON social_wiring.lais_proprietarios_contatos;
CREATE POLICY "lais_proprietarios_contatos_select_own_org" ON social_wiring.lais_proprietarios_contatos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_proprietarios_contatos_service_role" ON social_wiring.lais_proprietarios_contatos;
CREATE POLICY "lais_proprietarios_contatos_service_role" ON social_wiring.lais_proprietarios_contatos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 7. status_pagina: Lais > Modelos / Disparos / Atualizacao de imoveis ----------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_modelos', 'Lais — Modelos'),
          ('lais_disparos', 'Lais — Disparos'),
          ('lais_proprietarios', 'Lais — Atualização de imóveis')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
