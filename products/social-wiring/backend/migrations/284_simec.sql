-- ============================================================================
-- Migration 284 -- social_wiring: SIMEC (marketing-intelligence P1, slice S2)
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/marketing-intelligence/specs/phase0-audit.md
-- (section 3 module split, section 5 P1) + DECISIONS.md 2026-10-19 ("nothing hardcoded -- every
-- SIMEC number is configuration"). The calculator is the pure seed module
-- noctusai_lib.domain.content_performance; this file holds only what is per org:
--
--   simec_configs           per-org (account_id NULL) and per-profile (account_id = the Instagram
--                           connection) PARTIAL overrides layered on the seed defaults. `overrides`
--                           is validated by the seed (ConfigError -> 422) before it is written;
--                           `version` increments on every save.
--   simec_config_historico  append-only copy of every saved override (who, when, which version), so
--                           a past readout's config layer can be explained months later.
--   simec_readouts          one computed readout: period, the RESOLVED config + its version label +
--                           sha256 fingerprint (reliability rule 1: every number names the config
--                           that produced it), the per-window panel, baselines, alerts, and which
--                           metrics source produced the readings (instagram snapshots | fake).
--   simec_leituras          the per-content readings behind a readout (one row per content x window):
--                           validation status, age, metric + indicator cells, and source_ref (the
--                           ig_media_snapshots row/date the numbers came from).
--   status_pagina           'simec' row, seeded 'desenvolvimento' (visible to owner/dev/admin only,
--                           per 036) until the owner releases the page.
--
-- RLS: select_own_org + service_role on every table (writes go through the backend with the
-- service-role client and an explicit org filter; config writes are owner/admin-gated in the
-- router), pattern 281. NO SECURITY DEFINER function in this file. FORWARD-ONLY, IDEMPOTENT.
-- PREREQUISITES: core 070 (public.current_org_id_for), 005 (integration_accounts), 001
-- (status_pagina). Applied by the tech-lead with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.integration_accounts') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.integration_accounts (migration 005) -- apply 005 first';
  END IF;
  IF to_regclass('social_wiring.status_pagina') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.status_pagina (migration 001) -- apply 001 first';
  END IF;
END
$guard$;

-- ── config overrides (org + profile layers) ────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.simec_configs (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid        NOT NULL,
    platform    text        NOT NULL,
    account_id  uuid        REFERENCES social_wiring.integration_accounts (id) ON DELETE CASCADE,
    overrides   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    version     integer     NOT NULL DEFAULT 1,
    updated_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT simec_configs_platform_valida CHECK (platform IN ('instagram', 'tiktok')),
    CONSTRAINT simec_configs_overrides_objeto CHECK (jsonb_typeof(overrides) = 'object'),
    CONSTRAINT simec_configs_version_positiva CHECK (version >= 1)
);

COMMENT ON TABLE social_wiring.simec_configs IS
    'SIMEC config overrides (migration 284): account_id NULL = org layer, else the profile layer; partial JSON layered on the seed content_performance defaults.';

-- One org layer per platform, one profile layer per (platform, account).
CREATE UNIQUE INDEX IF NOT EXISTS uq_simec_configs_org
    ON social_wiring.simec_configs (org_id, platform) WHERE account_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_simec_configs_conta
    ON social_wiring.simec_configs (org_id, platform, account_id) WHERE account_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS social_wiring.simec_config_historico (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id   uuid        NOT NULL REFERENCES social_wiring.simec_configs (id) ON DELETE CASCADE,
    org_id      uuid        NOT NULL,
    platform    text        NOT NULL,
    account_id  uuid,
    version     integer     NOT NULL,
    overrides   jsonb       NOT NULL,
    changed_by  uuid,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT simec_config_historico_versao_uq UNIQUE (config_id, version)
);

COMMENT ON TABLE social_wiring.simec_config_historico IS
    'Append-only history of every saved SIMEC override layer (migration 284).';

-- ── readouts ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.simec_readouts (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid        NOT NULL,
    account_id          uuid        NOT NULL REFERENCES social_wiring.integration_accounts (id) ON DELETE CASCADE,
    platform            text        NOT NULL,
    source              text        NOT NULL,
    period_start        date        NOT NULL,
    period_end          date        NOT NULL,
    history_start       date        NOT NULL,
    config_version      text        NOT NULL,
    config_fingerprint  text        NOT NULL,
    config              jsonb       NOT NULL,
    status_counts       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    panel               jsonb       NOT NULL DEFAULT '{}'::jsonb,
    baselines           jsonb       NOT NULL DEFAULT '[]'::jsonb,
    alerts              jsonb       NOT NULL DEFAULT '{}'::jsonb,
    computed_by         uuid,
    computed_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT simec_readouts_platform_valida CHECK (platform IN ('instagram', 'tiktok')),
    CONSTRAINT simec_readouts_periodo_valido CHECK (period_start <= period_end AND history_start <= period_start),
    CONSTRAINT simec_readouts_fingerprint_sha256 CHECK (config_fingerprint ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE social_wiring.simec_readouts IS
    'SIMEC computed readouts (migration 284): panel/baselines/alerts for a period, stamped with the resolved config, its version label and sha256 fingerprint, and the metrics source.';

CREATE INDEX IF NOT EXISTS idx_simec_readouts_conta
    ON social_wiring.simec_readouts (org_id, account_id, computed_at DESC);

CREATE TABLE IF NOT EXISTS social_wiring.simec_leituras (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    readout_id    uuid        NOT NULL REFERENCES social_wiring.simec_readouts (id) ON DELETE CASCADE,
    org_id        uuid        NOT NULL,
    account_id    uuid        NOT NULL,
    content_id    text,
    janela        text,
    published_on  date,
    collected_on  date,
    formato       text,
    tema          text,
    status        text        NOT NULL,
    age_days      double precision,
    metrics       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    indicators    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    source_ref    jsonb,
    CONSTRAINT simec_leituras_status_valido CHECK (status IN
        ('ok', 'incompleto', 'data_invalida', 'fora_da_janela', 'duplicado', 'janela_desconhecida'))
);

COMMENT ON TABLE social_wiring.simec_leituras IS
    'Per-content SIMEC readings behind a readout (migration 284): one row per content x window with validation status and source_ref to the snapshot that produced the numbers.';

CREATE INDEX IF NOT EXISTS idx_simec_leituras_readout
    ON social_wiring.simec_leituras (readout_id);
CREATE INDEX IF NOT EXISTS idx_simec_leituras_conteudo
    ON social_wiring.simec_leituras (account_id, content_id);

-- ── RLS ─────────────────────────────────────────────────────────────────────
ALTER TABLE social_wiring.simec_configs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "simec_configs_select_own_org" ON social_wiring.simec_configs;
CREATE POLICY "simec_configs_select_own_org" ON social_wiring.simec_configs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "simec_configs_service_role" ON social_wiring.simec_configs;
CREATE POLICY "simec_configs_service_role" ON social_wiring.simec_configs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.simec_config_historico ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "simec_config_historico_select_own_org" ON social_wiring.simec_config_historico;
CREATE POLICY "simec_config_historico_select_own_org" ON social_wiring.simec_config_historico
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "simec_config_historico_service_role" ON social_wiring.simec_config_historico;
CREATE POLICY "simec_config_historico_service_role" ON social_wiring.simec_config_historico
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.simec_readouts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "simec_readouts_select_own_org" ON social_wiring.simec_readouts;
CREATE POLICY "simec_readouts_select_own_org" ON social_wiring.simec_readouts
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "simec_readouts_service_role" ON social_wiring.simec_readouts;
CREATE POLICY "simec_readouts_service_role" ON social_wiring.simec_readouts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.simec_leituras ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "simec_leituras_select_own_org" ON social_wiring.simec_leituras;
CREATE POLICY "simec_leituras_select_own_org" ON social_wiring.simec_leituras
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "simec_leituras_service_role" ON social_wiring.simec_leituras;
CREATE POLICY "simec_leituras_service_role" ON social_wiring.simec_leituras
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── page visibility ─────────────────────────────────────────────────────────
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
VALUES ('simec', 'desenvolvimento', 'SIMEC — Inteligência de marketing (Instagram)')
ON CONFLICT (nome_pagina) DO NOTHING;
