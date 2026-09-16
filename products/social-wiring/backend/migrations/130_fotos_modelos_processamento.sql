-- 130_fotos_modelos_processamento.sql -- social_wiring: model catalog
-- overrides, per-step model settings, the processing pause switch
--
-- Edição de Fotos W8 (plan §1 "Models" + §6; PROJECT.md C8).
--
-- 1. `llm_model_overrides` + `llm_model_override_versions` -- instantiated
--    from `noctusai_lib/integrations/llm/migrations/llm_model_overrides.sql.template`
--    ({{SCHEMA_NAME}} -> social_wiring, no other change). The platform admin
--    edits model rows in the UI (name, snapshot, per-1M prices, batch flag,
--    performance/cheap tag, enabled); every save is a new immutable version.
--    This is how `gpt-image-2` gets a price and the batch flag (C8) without a
--    deploy.
-- 2. `fotos_platform_settings` -- one model per engine step (style-guide
--    builder, evaluator, rule proposer, note writer; NULL = the engine
--    default) and `processamento_ativo`, the live pause switch the worker
--    reads before every claim. DEFAULT false: the worker is built and
--    running, but claims nothing until the platform admin turns it on
--    (OpenAI has no credits yet -- PROJECT.md §4c). A database without
--    this column reads as paused too (the seed decoder's default).
-- 3. Fix-on-contact: `fotos_modelo_metricas` (126) is SECURITY DEFINER and
--    returns cross-org aggregates (approval rate, cost per approved photo),
--    but 126 never revoked the default PUBLIC execute grant -- any
--    authenticated caller could reach it through PostgREST. Only the
--    service role (the API's admin-gated route) may call it now.
-- 2b. The rule-proposer tunables (`rule_proposal_debounce_seconds`,
--    `max_rejections_per_proposal`) move from engine-only config to this
--    table so the W7 "Regras" panel can edit them (resolves
--    the W7 remediation marker `fotos-rule-proposer-settings-migration`).
-- 4. `status_pagina` row for the new admin page `edicao-fotos-processamento`
--    (`edicao-fotos-modelos` already exists, 128). Insert-if-missing only.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. Model catalog overrides (from the seed template)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.llm_model_overrides (
    provider                        TEXT NOT NULL CHECK (length(provider) BETWEEN 1 AND 40),
    kind                            TEXT NOT NULL
                                        CHECK (kind IN ('chat', 'embedding', 'audio', 'vision', 'image_edit')),
    model_id                        TEXT NOT NULL CHECK (length(model_id) BETWEEN 1 AND 120),
    enabled                         BOOLEAN NOT NULL DEFAULT true,
    label                           TEXT CHECK (label IS NULL OR length(label) <= 120),
    description                     TEXT CHECK (description IS NULL OR length(description) <= 500),
    snapshot                        TEXT CHECK (snapshot IS NULL OR length(snapshot) <= 60),
    cost_per_1m_input_tokens        NUMERIC(12, 4) CHECK (cost_per_1m_input_tokens IS NULL OR cost_per_1m_input_tokens >= 0),
    cost_per_1m_output_tokens       NUMERIC(12, 4) CHECK (cost_per_1m_output_tokens IS NULL OR cost_per_1m_output_tokens >= 0),
    cost_per_1m_image_input_tokens  NUMERIC(12, 4) CHECK (cost_per_1m_image_input_tokens IS NULL OR cost_per_1m_image_input_tokens >= 0),
    cost_per_1m_image_output_tokens NUMERIC(12, 4) CHECK (cost_per_1m_image_output_tokens IS NULL OR cost_per_1m_image_output_tokens >= 0),
    supports_batch                  BOOLEAN NOT NULL DEFAULT false,
    tag_performance                 TEXT CHECK (tag_performance IS NULL OR tag_performance IN ('performance', 'economico')),
    version                         INTEGER NOT NULL CHECK (version > 0),
    updated_by                      UUID,
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, kind, model_id)
);

CREATE TABLE IF NOT EXISTS social_wiring.llm_model_override_versions (
    id                              BIGSERIAL PRIMARY KEY,
    provider                        TEXT NOT NULL,
    kind                            TEXT NOT NULL,
    model_id                        TEXT NOT NULL,
    enabled                         BOOLEAN NOT NULL,
    label                           TEXT,
    description                     TEXT,
    snapshot                        TEXT,
    cost_per_1m_input_tokens        NUMERIC(12, 4),
    cost_per_1m_output_tokens       NUMERIC(12, 4),
    cost_per_1m_image_input_tokens  NUMERIC(12, 4),
    cost_per_1m_image_output_tokens NUMERIC(12, 4),
    supports_batch                  BOOLEAN NOT NULL,
    tag_performance                 TEXT,
    version                         INTEGER NOT NULL CHECK (version > 0),
    updated_by                      UUID,
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The optimistic lock: two concurrent saves cannot both claim version N.
    UNIQUE (provider, kind, model_id, version)
);

-- History is append-only: a price that was in force must stay provable.
CREATE OR REPLACE FUNCTION social_wiring.llm_model_override_versions_imutavel()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'llm_model_override_versions is append-only'
        USING ERRCODE = 'P0001';
END;
$$;

DROP TRIGGER IF EXISTS trg_llm_model_override_versions_imutavel
    ON social_wiring.llm_model_override_versions;
CREATE TRIGGER trg_llm_model_override_versions_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.llm_model_override_versions
    FOR EACH ROW
    EXECUTE FUNCTION social_wiring.llm_model_override_versions_imutavel();

REVOKE EXECUTE ON FUNCTION social_wiring.llm_model_override_versions_imutavel() FROM PUBLIC;

ALTER TABLE social_wiring.llm_model_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.llm_model_override_versions ENABLE ROW LEVEL SECURITY;

-- Platform scope (not org data): platform admins may read; nobody but the
-- service role writes.
CREATE POLICY "llm_model_overrides_select_platform_admin" ON social_wiring.llm_model_overrides
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.llm_model_overrides
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "llm_model_override_versions_select_platform_admin" ON social_wiring.llm_model_override_versions
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.llm_model_override_versions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS ix_llm_model_override_versions_model
    ON social_wiring.llm_model_override_versions (provider, kind, model_id, version DESC);

-- ----------------------------------------------------------------------------
-- 2. Per-step models + the processing pause switch
-- ----------------------------------------------------------------------------

ALTER TABLE social_wiring.fotos_platform_settings
    ADD COLUMN IF NOT EXISTS modelo_guia TEXT
        CHECK (modelo_guia IS NULL OR length(modelo_guia) BETWEEN 1 AND 120),
    ADD COLUMN IF NOT EXISTS modelo_avaliador TEXT
        CHECK (modelo_avaliador IS NULL OR length(modelo_avaliador) BETWEEN 1 AND 120),
    ADD COLUMN IF NOT EXISTS modelo_regras TEXT
        CHECK (modelo_regras IS NULL OR length(modelo_regras) BETWEEN 1 AND 120),
    ADD COLUMN IF NOT EXISTS modelo_notas TEXT
        CHECK (modelo_notas IS NULL OR length(modelo_notas) BETWEEN 1 AND 120),
    ADD COLUMN IF NOT EXISTS processamento_ativo BOOLEAN NOT NULL DEFAULT false,
    -- Rule-proposer tunables (W7's panel, editable since W8). Defaults =
    -- `PhotoEditingConfig` (1800 s debounce, 50 rejections per call).
    ADD COLUMN IF NOT EXISTS rule_proposal_debounce_seconds INTEGER NOT NULL DEFAULT 1800
        CHECK (rule_proposal_debounce_seconds BETWEEN 0 AND 604800),
    ADD COLUMN IF NOT EXISTS max_rejections_per_proposal INTEGER NOT NULL DEFAULT 50
        CHECK (max_rejections_per_proposal BETWEEN 1 AND 500);

COMMENT ON COLUMN social_wiring.fotos_platform_settings.processamento_ativo IS
    'Live pause switch for the photo-editing job worker. false = claim nothing (jobs wait in social_wiring.jobs).';

-- ----------------------------------------------------------------------------
-- 3. Metrics RPC: service role only
-- ----------------------------------------------------------------------------

REVOKE EXECUTE ON FUNCTION social_wiring.fotos_modelo_metricas(TEXT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION social_wiring.fotos_modelo_metricas(TEXT) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.fotos_modelo_metricas(TEXT) TO service_role;

-- ----------------------------------------------------------------------------
-- 4. Nav page row
-- ----------------------------------------------------------------------------

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao) VALUES
    ('edicao-fotos-processamento', 'desenvolvimento', 'Edição de Fotos — processamento e saúde da fila (admin)')
ON CONFLICT (nome_pagina) DO NOTHING;
