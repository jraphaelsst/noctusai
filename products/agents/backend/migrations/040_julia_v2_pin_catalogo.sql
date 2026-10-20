-- ============================================================================
-- 040_julia_v2_pin_catalogo.sql -- Julia v2 A-RT2.
--
-- 1. Qualification-standard pin (CONTRACT 3.1/2.6):
--    * `guard_agent_version_qualificacao_pin` (032) accepted a pin only on a PUBLISHED standard
--      version. A newer standard publish ARCHIVES the previous one, so a draft inheriting the active
--      version's pin (still the previous standard) would be refused. The pin may now target a
--      published OR archived standard version (never a draft); freezing on a published agent version
--      and the compiled_hash invalidation are unchanged.
--    * `agent_versions_inherit_qualificacao`: a new draft copies the pin of the version it is based on
--      (the draft inherits, the platform admin moves it on purpose). Named so it fires BEFORE the
--      guard (triggers fire in name order).
-- 2. Agent catalogue (`GET /api/agents/catalogo`): display-level rows only, edited by platform admins.
--    `catalogo_agentes` (one row per listed agent key: role + public description) and
--    `catalogo_capacidades` (the capability labels). Service-role only, like every content table (036).
-- 3. status_pagina row for the `/agentes/catalogo` nav entry ('desenvolvimento': visible to dev/owner
--    until promoted). status_pagina stays SELECT-only for the browser roles (036 untouched).
--
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. the pin ──────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION agents.guard_agent_version_qualificacao_pin()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.qualificacao_versao_id IS NOT DISTINCT FROM OLD.qualificacao_versao_id THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF NEW.qualificacao_versao_id IS NOT NULL THEN
        SELECT status INTO v_status FROM agents.qualificacao_versoes WHERE id = NEW.qualificacao_versao_id;
        IF v_status IS NULL OR v_status NOT IN ('publicada', 'arquivada') THEN
            RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF NEW.status = 'rascunho' THEN
        NEW.compiled_hash := NULL;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_version_qualificacao_pin() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_version_qualificacao_pin() TO service_role;

CREATE OR REPLACE FUNCTION agents.inherit_agent_version_qualificacao()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF NEW.status = 'rascunho' AND NEW.qualificacao_versao_id IS NULL AND NEW.based_on_version_id IS NOT NULL THEN
        SELECT v.qualificacao_versao_id INTO NEW.qualificacao_versao_id
          FROM agents.agent_versions v WHERE v.id = NEW.based_on_version_id;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.inherit_agent_version_qualificacao() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.inherit_agent_version_qualificacao() TO service_role;

CREATE OR REPLACE TRIGGER agent_versions_inherit_qualificacao
    BEFORE INSERT ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.inherit_agent_version_qualificacao();

-- ── 2. the catalogue ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.catalogo_agentes (
    agent_key TEXT PRIMARY KEY CHECK (agent_key ~ '^[a-z][a-z0-9-]{1,63}$'),
    papel TEXT NOT NULL CHECK (papel ~ '^[a-z][a-z0-9_-]{1,31}$'),
    descricao_publica TEXT NOT NULL CHECK (length(descricao_publica) BETWEEN 1 AND 600),
    ordem INTEGER NOT NULL DEFAULT 0,
    visivel BOOLEAN NOT NULL DEFAULT true,
    updated_by UUID NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agents.catalogo_capacidades (
    agent_key TEXT NOT NULL REFERENCES agents.catalogo_agentes(agent_key) ON DELETE CASCADE,
    ordem INTEGER NOT NULL CHECK (ordem >= 0),
    rotulo TEXT NOT NULL CHECK (length(rotulo) BETWEEN 1 AND 120),
    PRIMARY KEY (agent_key, ordem)
);

ALTER TABLE agents.catalogo_agentes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.catalogo_capacidades ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.catalogo_agentes;
CREATE POLICY "service_role_bypass" ON agents.catalogo_agentes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.catalogo_capacidades;
CREATE POLICY "service_role_bypass" ON agents.catalogo_capacidades
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.catalogo_agentes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON agents.catalogo_capacidades FROM PUBLIC, anon, authenticated;

-- Display rows for the agents that exist today (editable by a platform admin afterwards; ON CONFLICT keeps an
-- edited row). Julia stays leads-only; One Chat stays the separate operator agent (owner, 2026-10-20).
INSERT INTO agents.catalogo_agentes (agent_key, papel, descricao_publica, ordem) VALUES
    ('julia', 'sdr', 'Atende os leads de imóveis no WhatsApp, entende o interesse de cada um e encaminha para a equipe.', 10),
    ('one-chat', 'operador', 'Responde automaticamente as conversas do WhatsApp conectado, em nome do operador.', 20)
ON CONFLICT (agent_key) DO NOTHING;

INSERT INTO agents.catalogo_capacidades (agent_key, ordem, rotulo) VALUES
    ('julia', 0, 'Atendimento de leads no WhatsApp'),
    ('julia', 1, 'Sugestão de imóveis'),
    ('julia', 2, 'Encaminhamento para a equipe'),
    ('one-chat', 0, 'Resposta automática no WhatsApp'),
    ('one-chat', 1, 'Liga e desliga por conexão')
ON CONFLICT (agent_key, ordem) DO NOTHING;

-- ── 3. nav page ─────────────────────────────────────────────────────────────

INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('agentes-catalogo', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
