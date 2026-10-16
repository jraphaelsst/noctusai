-- ============================================================================
-- Migration 280 -- social_wiring: Lais wave 13 "Avaliacoes no Google" + CAPI signals
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 15 (wave 13: Avaliacoes + CAPI),
--   section 17 (LGPD), specs/page-map-v2.md "Avaliacoes no Google".
--   lais_avaliacao_config   per-org: google_review_url (the link sent in the review ask), gbp_location_id
--                           (Google Business Profile location the reviews are read from), capi_ativo +
--                           capi_pixel_id (Meta Conversions API signals).
--   lais_avaliacao_pedidos  one row per review-ask message Julia sent (at most one per contato per 90 days:
--                           the service reads this table; the 90-day rule is a business rule, not a constraint).
--   lais_avaliacoes_cache   reviews fetched from the Google Business Profile API (idempotent on external_id).
--   lais_capi_eventos       one row per Meta CAPI signal (lead_qualificado | visita_agendada | resposta_cliente),
--                           only for contatos whose lead came from Meta ads; `nao_configurado` rows record that the
--                           org has not enabled/configured CAPI (never sent). dedupe_key makes a replay a no-op.
--   status_pagina           `lais_avaliacoes` (copies whatsapp_chat, like 259/270).
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 267/278.
-- NO SECURITY DEFINER function in this file. FORWARD-ONLY, IDEMPOTENT.
-- PREREQUISITES: core 070, 014 (status_pagina), 267 (lais_contatos). Applied by the tech-lead with
-- noctus.dev.migrate_product.
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

-- -- 1. config ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_avaliacao_config (
    org_id            uuid        PRIMARY KEY,
    google_review_url text,
    gbp_location_id   text,
    capi_ativo        boolean     NOT NULL DEFAULT false,
    capi_pixel_id     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_avaliacao_config_review_url_https
        CHECK (google_review_url IS NULL OR (google_review_url ~ '^https://\S+$' AND char_length(google_review_url) <= 500)),
    CONSTRAINT lais_avaliacao_config_pixel_valido
        CHECK (capi_pixel_id IS NULL OR capi_pixel_id ~ '^[0-9]{5,20}$')
);

COMMENT ON TABLE social_wiring.lais_avaliacao_config IS
    'Lais wave 13 per-org config (migration 280): review link, GBP location, Meta CAPI switch + pixel id. '
    'The CAPI access token is NOT stored here: it is the workspace Meta Ads token (app_integration_config).';

-- -- 2. review asks -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_avaliacao_pedidos (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid        NOT NULL,
    contato_id   uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    interacao_id uuid,
    enviado_at   timestamptz NOT NULL DEFAULT now(),
    status       text        NOT NULL DEFAULT 'enviado',
    erro         text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_avaliacao_pedidos_status_valido CHECK (status IN ('enviado', 'erro')),
    CONSTRAINT lais_avaliacao_pedidos_erro_exige_mensagem CHECK (status <> 'erro' OR erro IS NOT NULL)
);

COMMENT ON TABLE social_wiring.lais_avaliacao_pedidos IS
    'One review-ask message per row (migration 280, contract 15/17): the 90-day-per-contato rule reads this ledger.';

CREATE INDEX IF NOT EXISTS idx_lais_avaliacao_pedidos_contato
    ON social_wiring.lais_avaliacao_pedidos (org_id, contato_id, enviado_at DESC);
CREATE INDEX IF NOT EXISTS idx_lais_avaliacao_pedidos_org_mes
    ON social_wiring.lais_avaliacao_pedidos (org_id, enviado_at DESC);

-- -- 3. reviews cache -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_avaliacoes_cache (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid        NOT NULL,
    external_id  text        NOT NULL,
    autor        text,
    nota         integer     NOT NULL,
    texto        text,
    publicado_at timestamptz,
    link         text,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_avaliacoes_cache_nota_valida CHECK (nota BETWEEN 1 AND 5)
);

COMMENT ON TABLE social_wiring.lais_avaliacoes_cache IS
    'Google Business Profile reviews mirrored per org (migration 280); idempotent on (org_id, external_id).';

CREATE UNIQUE INDEX IF NOT EXISTS lais_avaliacoes_cache_org_externo_uq
    ON social_wiring.lais_avaliacoes_cache (org_id, external_id);
CREATE INDEX IF NOT EXISTS idx_lais_avaliacoes_cache_publicado
    ON social_wiring.lais_avaliacoes_cache (org_id, publicado_at DESC);

-- -- 4. CAPI signals ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_capi_eventos (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid        NOT NULL,
    contato_id  uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    evento      text        NOT NULL,
    dedupe_key  text        NOT NULL,
    status      text        NOT NULL DEFAULT 'pendente',
    erro        text,
    enviado_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_capi_eventos_evento_valido
        CHECK (evento IN ('lead_qualificado', 'visita_agendada', 'resposta_cliente')),
    CONSTRAINT lais_capi_eventos_status_valido
        CHECK (status IN ('pendente', 'enviado', 'erro', 'nao_configurado')),
    CONSTRAINT lais_capi_eventos_erro_exige_mensagem CHECK (status <> 'erro' OR erro IS NOT NULL),
    CONSTRAINT lais_capi_eventos_enviado_exige_data CHECK (status <> 'enviado' OR enviado_at IS NOT NULL)
);

COMMENT ON TABLE social_wiring.lais_capi_eventos IS
    'Meta Conversions API signals (migration 280, contract 15/17): only for Meta-ads leads; identifiers are hashed '
    '(SHA-256) in the payload sent to Meta and are NOT stored here.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_capi_eventos_dedupe_uq
    ON social_wiring.lais_capi_eventos (org_id, dedupe_key);
CREATE INDEX IF NOT EXISTS idx_lais_capi_eventos_contato
    ON social_wiring.lais_capi_eventos (org_id, contato_id, created_at DESC);

-- -- 5. RLS -----------------------------------------------------------------------------
ALTER TABLE social_wiring.lais_avaliacao_config  ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_avaliacao_pedidos ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_avaliacoes_cache  ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_capi_eventos      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_avaliacao_config_select_own_org" ON social_wiring.lais_avaliacao_config;
CREATE POLICY "lais_avaliacao_config_select_own_org" ON social_wiring.lais_avaliacao_config
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_avaliacao_config_service_role" ON social_wiring.lais_avaliacao_config;
CREATE POLICY "lais_avaliacao_config_service_role" ON social_wiring.lais_avaliacao_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_avaliacao_pedidos_select_own_org" ON social_wiring.lais_avaliacao_pedidos;
CREATE POLICY "lais_avaliacao_pedidos_select_own_org" ON social_wiring.lais_avaliacao_pedidos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_avaliacao_pedidos_service_role" ON social_wiring.lais_avaliacao_pedidos;
CREATE POLICY "lais_avaliacao_pedidos_service_role" ON social_wiring.lais_avaliacao_pedidos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_avaliacoes_cache_select_own_org" ON social_wiring.lais_avaliacoes_cache;
CREATE POLICY "lais_avaliacoes_cache_select_own_org" ON social_wiring.lais_avaliacoes_cache
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_avaliacoes_cache_service_role" ON social_wiring.lais_avaliacoes_cache;
CREATE POLICY "lais_avaliacoes_cache_service_role" ON social_wiring.lais_avaliacoes_cache
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_capi_eventos_select_own_org" ON social_wiring.lais_capi_eventos;
CREATE POLICY "lais_capi_eventos_select_own_org" ON social_wiring.lais_capi_eventos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_capi_eventos_service_role" ON social_wiring.lais_capi_eventos;
CREATE POLICY "lais_capi_eventos_service_role" ON social_wiring.lais_capi_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 6. status_pagina -----------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT 'lais_avaliacoes', origem.status, 'Lais — Avaliações no Google'
  FROM social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
