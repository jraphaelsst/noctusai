-- ============================================================================
-- 010_credentials_and_runtime_settings.sql — the DB side of the
-- "Credenciais e integrações" + "Configurações do agente" pages
-- (contract §B.0 / §D / §E.5 notes, 2026-09-16).
--
-- 1. agents.app_integration_config — app-wide Fernet-encrypted key→value
--    store backing `noctusai_lib.security.app_config.RealAppConfigStore`
--    (same shape as social_wiring.app_integration_config, migration 022).
--    Holds ACADEMIA_API_TOKEN / SOCIAL_WIRING_API_TOKEN / the Julia
--    Anthropic key / JULIA_AGENT_ID and the §D approval key RING
--    (`approval_assertion_secrets:academia-de-reciclagem`). The env values
--    stay the fallback. academia-de-reciclagem READS the ring row through
--    its own service-role client (contract §D "Rotation").
--
-- 2. agents.runtime_settings — admin overrides of the runtime specs whose
--    defaults come from env (approval timeout, max turns, rate limit).
--    Plain values, never secrets.
--
-- 3. status_pagina rows for the two new nav pages (every nav-listed route
--    needs one — see 008's header).
--
-- SERVICE-ROLE ONLY for both tables (same posture as 009): no
-- authenticated policy, and the schema-wide default grant from
-- 001_agents.sql is REVOKEd explicitly. The only sanctioned read/write
-- path is the platform-admin API.
--
-- Forward-only + idempotent. NOT applied by the slice that adds it — the
-- tech-lead applies it (`noctus.dev.migrate_product product=agents`).
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- app_integration_config
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.app_integration_config (
    key             TEXT PRIMARY KEY,
    encrypted_value TEXT NOT NULL,              -- Fernet(value) — never plaintext
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.app_integration_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.app_integration_config;
CREATE POLICY "service_role_bypass" ON agents.app_integration_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.app_integration_config FROM anon, authenticated;

-- ────────────────────────────────────────────────────────────────────────
-- runtime_settings
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.runtime_settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_by UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.runtime_settings
    DROP CONSTRAINT IF EXISTS runtime_settings_key_check;

ALTER TABLE agents.runtime_settings
    ADD CONSTRAINT runtime_settings_key_check
        CHECK (key IN ('approval_timeout_seconds', 'max_turns', 'messages_rate_limit'));

ALTER TABLE agents.runtime_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.runtime_settings;
CREATE POLICY "service_role_bypass" ON agents.runtime_settings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.runtime_settings FROM anon, authenticated;

-- ────────────────────────────────────────────────────────────────────────
-- page visibility (platform-admin pages — gated server-side regardless)
-- ────────────────────────────────────────────────────────────────────────

INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('credenciais', 'desenvolvimento'),
    ('configuracoes-agente', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
