-- ============================================================================
-- 032_julia_v2_qualificacao.sql -- Julia v2 qualification standard + per-lead
-- state (products/agents/projects/julia-v2/CONTRACT.md section 3, 9, 11 risk 12).
--
-- OWNER DECISION 2026-10-19 (Q2): the standard `imob-lead` is ONE platform
-- standard for every org. There is NO per-org fork and NO `org_id` /
-- `origem_padrao_id` on the library tables. Org-specific context (price
-- bands, regions served) is org specs (another slice), never part of the
-- standard.
--
-- 1. Library: qualificacao_padroes / _versoes / _criterios / _estagios /
--    _parametros. A published version is immutable (triggers); a new version is
--    a draft copied from the last one.
-- 2. agent_versions.qualificacao_versao_id (nullable FK): a published agent
--    version pins a PUBLISHED standard version; the pin is frozen with the
--    agent version and a draft's pin change invalidates its compiled_hash.
-- 3. Per-lead tables (LGPD: lifestyle profile + literal quotes, 180-day
--    retention aligned with the channels purge, delete-by-lead):
--    lead_qualificacao_registros (append-only), lead_imovel_eventos,
--    lead_qualificacao_estado (cache recomputed by code, never by a model).
--    Service-role only, like every lead row (migration 025).
-- 4. agents.apagar_qualificacao_lead / purgar_qualificacao_inativos (erasure).
--
-- NOC-REMEDIATE[qual-lead-ref-fk]: lead_ref_id is declared WITHOUT a foreign key
-- here because agents.lead_refs is created by the threads migration (033). The
-- runtime slice adds `FOREIGN KEY (lead_ref_id) REFERENCES agents.lead_refs(id)
-- ON DELETE CASCADE` on the three per-lead tables once both have landed -- 2026-10-19.
--
-- Idempotent where it can be. NOT applied by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. library ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.qualificacao_padroes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z][a-z0-9_-]{1,63}$'),
    nome TEXT NOT NULL CHECK (btrim(nome) <> ''),
    descricao TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_qualificacao_padroes_chave UNIQUE (chave)
);

CREATE TABLE IF NOT EXISTS agents.qualificacao_versoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    padrao_id UUID NOT NULL REFERENCES agents.qualificacao_padroes(id),
    versao INT NOT NULL CHECK (versao >= 1),
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'publicada', 'arquivada')),
    notas TEXT NULL,
    publicada_em TIMESTAMPTZ NULL,
    publicada_por UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_qualificacao_versoes_padrao_versao UNIQUE (padrao_id, versao),
    CONSTRAINT qualificacao_versoes_publicada_completa CHECK (
        status = 'rascunho' OR (publicada_em IS NOT NULL AND publicada_por IS NOT NULL)
    )
);
-- One draft per standard.
CREATE UNIQUE INDEX IF NOT EXISTS uq_qualificacao_versoes_um_rascunho
    ON agents.qualificacao_versoes (padrao_id) WHERE status = 'rascunho';

CREATE TABLE IF NOT EXISTS agents.qualificacao_criterios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    versao_id UUID NOT NULL REFERENCES agents.qualificacao_versoes(id) ON DELETE CASCADE,
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z][a-z0-9_]{1,63}$'),
    grupo TEXT NOT NULL CHECK (grupo IN
        ('prontidao', 'bloqueios', 'interesse', 'perfil_imovel', 'perfil_vida', 'contato')),
    rotulo TEXT NOT NULL CHECK (btrim(rotulo) <> ''),
    descricao_modelo TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL CHECK (tipo IN ('enum', 'multi', 'bool', 'numero', 'faixa', 'texto', 'imovel_ref')),
    opcoes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(opcoes) = 'array'),
    unidade TEXT NULL,
    sensivel TEXT NULL CHECK (sensivel IS NULL OR sensivel IN ('faixa', 'nao_coletar')),
    pontuacao JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(pontuacao) IN ('object', 'array')),
    ordem INT NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    -- Named score axis (fit / intencao / urgencia ...); NULL = counts in the total only.
    eixo TEXT NULL CHECK (eixo IS NULL OR eixo ~ '^[a-z][a-z0-9_]{1,31}$'),
    -- A record older than this stops counting (the criterion is missing again).
    validade_dias INT NULL CHECK (validade_dias IS NULL OR validade_dias >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_qualificacao_criterios_chave UNIQUE (versao_id, chave)
);

CREATE TABLE IF NOT EXISTS agents.qualificacao_estagios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    versao_id UUID NOT NULL REFERENCES agents.qualificacao_versoes(id) ON DELETE CASCADE,
    chave TEXT NOT NULL CHECK (chave ~ '^[a-z][a-z0-9_]{1,63}$'),
    rotulo TEXT NOT NULL CHECK (btrim(rotulo) <> ''),
    descricao TEXT NOT NULL DEFAULT '',
    ordem INT NOT NULL,
    regra JSONB NOT NULL CHECK (jsonb_typeof(regra) = 'object'),
    conclusivo BOOLEAN NOT NULL DEFAULT FALSE,
    terminal BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_qualificacao_estagios_chave UNIQUE (versao_id, chave)
);

CREATE TABLE IF NOT EXISTS agents.qualificacao_parametros (
    versao_id UUID PRIMARY KEY REFERENCES agents.qualificacao_versoes(id) ON DELETE CASCADE,
    minimo_para_ofertar JSONB NOT NULL CHECK (jsonb_typeof(minimo_para_ofertar) = 'object'),
    lote_ofertas INT NOT NULL DEFAULT 3 CHECK (lote_ofertas BETWEEN 1 AND 5),
    score_max INT NOT NULL DEFAULT 100 CHECK (score_max >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE TRIGGER set_updated_at_qualificacao_versoes
    BEFORE UPDATE ON agents.qualificacao_versoes
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
CREATE OR REPLACE TRIGGER set_updated_at_qualificacao_criterios
    BEFORE UPDATE ON agents.qualificacao_criterios
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
CREATE OR REPLACE TRIGGER set_updated_at_qualificacao_estagios
    BEFORE UPDATE ON agents.qualificacao_estagios
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
CREATE OR REPLACE TRIGGER set_updated_at_qualificacao_parametros
    BEFORE UPDATE ON agents.qualificacao_parametros
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

-- ── immutability: a published version (and its children) never changes ─────

CREATE OR REPLACE FUNCTION agents.guard_qualificacao_versao_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status = 'rascunho' THEN
        -- A draft is editable and may be published; never archived directly.
        IF NEW.status = 'arquivada' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    -- Published: only publicada -> arquivada, every content column frozen.
    IF NOT (OLD.status = 'publicada' AND NEW.status = 'arquivada') THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF NEW.padrao_id IS DISTINCT FROM OLD.padrao_id
       OR NEW.versao IS DISTINCT FROM OLD.versao
       OR NEW.notas IS DISTINCT FROM OLD.notas
       OR NEW.publicada_em IS DISTINCT FROM OLD.publicada_em
       OR NEW.publicada_por IS DISTINCT FROM OLD.publicada_por
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_qualificacao_versao_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_qualificacao_versao_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_qualificacao_versao_immutable
    BEFORE UPDATE OR DELETE ON agents.qualificacao_versoes
    FOR EACH ROW EXECUTE FUNCTION agents.guard_qualificacao_versao_immutable();

-- Children keyed by versao_id: the parent row is locked FOR UPDATE before its
-- status is read (serialises against a concurrent publish).
CREATE OR REPLACE FUNCTION agents.guard_qualificacao_filho_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO v_status FROM agents.qualificacao_versoes WHERE id = OLD.versao_id FOR UPDATE;
        -- NULL = parent already gone (a cascade from a discarded draft).
        IF v_status IS NOT NULL AND v_status <> 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO v_status FROM agents.qualificacao_versoes WHERE id = NEW.versao_id FOR UPDATE;
        IF v_status IS DISTINCT FROM 'rascunho' THEN
            RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_qualificacao_filho_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_qualificacao_filho_immutable() TO service_role;

CREATE OR REPLACE TRIGGER guard_qualificacao_criterios_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.qualificacao_criterios
    FOR EACH ROW EXECUTE FUNCTION agents.guard_qualificacao_filho_immutable();
CREATE OR REPLACE TRIGGER guard_qualificacao_estagios_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.qualificacao_estagios
    FOR EACH ROW EXECUTE FUNCTION agents.guard_qualificacao_filho_immutable();
CREATE OR REPLACE TRIGGER guard_qualificacao_parametros_immutable
    BEFORE INSERT OR UPDATE OR DELETE ON agents.qualificacao_parametros
    FOR EACH ROW EXECUTE FUNCTION agents.guard_qualificacao_filho_immutable();

-- RLS: every authenticated user reads the (platform-wide) standard; writes are
-- service-role only (the platform-admin API route is the writer).
ALTER TABLE agents.qualificacao_padroes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.qualificacao_versoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.qualificacao_criterios ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.qualificacao_estagios ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.qualificacao_parametros ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS qualificacao_padroes_select_authenticated ON agents.qualificacao_padroes;
CREATE POLICY qualificacao_padroes_select_authenticated ON agents.qualificacao_padroes FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.qualificacao_padroes;
CREATE POLICY "service_role_bypass" ON agents.qualificacao_padroes FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.qualificacao_padroes FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.qualificacao_padroes FROM authenticated;

DROP POLICY IF EXISTS qualificacao_versoes_select_authenticated ON agents.qualificacao_versoes;
CREATE POLICY qualificacao_versoes_select_authenticated ON agents.qualificacao_versoes FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.qualificacao_versoes;
CREATE POLICY "service_role_bypass" ON agents.qualificacao_versoes FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.qualificacao_versoes FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.qualificacao_versoes FROM authenticated;

DROP POLICY IF EXISTS qualificacao_criterios_select_authenticated ON agents.qualificacao_criterios;
CREATE POLICY qualificacao_criterios_select_authenticated ON agents.qualificacao_criterios FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.qualificacao_criterios;
CREATE POLICY "service_role_bypass" ON agents.qualificacao_criterios FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.qualificacao_criterios FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.qualificacao_criterios FROM authenticated;

DROP POLICY IF EXISTS qualificacao_estagios_select_authenticated ON agents.qualificacao_estagios;
CREATE POLICY qualificacao_estagios_select_authenticated ON agents.qualificacao_estagios FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.qualificacao_estagios;
CREATE POLICY "service_role_bypass" ON agents.qualificacao_estagios FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.qualificacao_estagios FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.qualificacao_estagios FROM authenticated;

DROP POLICY IF EXISTS qualificacao_parametros_select_authenticated ON agents.qualificacao_parametros;
CREATE POLICY qualificacao_parametros_select_authenticated ON agents.qualificacao_parametros FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.qualificacao_parametros;
CREATE POLICY "service_role_bypass" ON agents.qualificacao_parametros FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.qualificacao_parametros FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.qualificacao_parametros FROM authenticated;

CREATE INDEX IF NOT EXISTS idx_qualificacao_criterios_versao ON agents.qualificacao_criterios (versao_id, ordem);
CREATE INDEX IF NOT EXISTS idx_qualificacao_estagios_versao ON agents.qualificacao_estagios (versao_id, ordem);

-- ── draft / publish as ONE transaction each ────────────────────────────────

-- New draft of a standard, optionally copied from an existing version.
CREATE OR REPLACE FUNCTION agents.criar_rascunho_qualificacao(
    p_padrao_id UUID,
    p_notas TEXT,
    p_copiar_de UUID
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_novo UUID;
    v_num INT;
BEGIN
    PERFORM 1 FROM agents.qualificacao_padroes WHERE id = p_padrao_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM agents.qualificacao_versoes WHERE padrao_id = p_padrao_id AND status = 'rascunho') THEN
        RAISE EXCEPTION 'draft_exists' USING ERRCODE = 'P0001';
    END IF;
    IF p_copiar_de IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM agents.qualificacao_versoes WHERE id = p_copiar_de AND padrao_id = p_padrao_id
    ) THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;

    SELECT COALESCE(MAX(versao), 0) + 1 INTO v_num
      FROM agents.qualificacao_versoes WHERE padrao_id = p_padrao_id;
    INSERT INTO agents.qualificacao_versoes (padrao_id, versao, status, notas)
    VALUES (p_padrao_id, v_num, 'rascunho', p_notas)
    RETURNING id INTO v_novo;

    IF p_copiar_de IS NOT NULL THEN
        INSERT INTO agents.qualificacao_criterios
            (versao_id, chave, grupo, rotulo, descricao_modelo, tipo, opcoes, unidade, sensivel, pontuacao, ordem, ativo, eixo, validade_dias)
        SELECT v_novo, chave, grupo, rotulo, descricao_modelo, tipo, opcoes, unidade, sensivel, pontuacao, ordem, ativo, eixo, validade_dias
          FROM agents.qualificacao_criterios WHERE versao_id = p_copiar_de;
        INSERT INTO agents.qualificacao_estagios
            (versao_id, chave, rotulo, descricao, ordem, regra, conclusivo, terminal)
        SELECT v_novo, chave, rotulo, descricao, ordem, regra, conclusivo, terminal
          FROM agents.qualificacao_estagios WHERE versao_id = p_copiar_de;
        INSERT INTO agents.qualificacao_parametros (versao_id, minimo_para_ofertar, lote_ofertas, score_max)
        SELECT v_novo, minimo_para_ofertar, lote_ofertas, score_max
          FROM agents.qualificacao_parametros WHERE versao_id = p_copiar_de;
    END IF;
    RETURN v_novo;
END;
$$;

-- Publish: the draft becomes `publicada`, the previous `publicada` is archived.
-- The rule validation happens in the application (engine.validar_versao) BEFORE this call.
CREATE OR REPLACE FUNCTION agents.publicar_qualificacao_versao(
    p_versao_id UUID,
    p_user_id UUID
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_status TEXT;
    v_padrao UUID;
BEGIN
    SELECT status, padrao_id INTO v_status, v_padrao
      FROM agents.qualificacao_versoes WHERE id = p_versao_id FOR UPDATE;
    IF v_status IS NULL THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF v_status <> 'rascunho' THEN
        RAISE EXCEPTION 'version_immutable' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM agents.qualificacao_parametros WHERE versao_id = p_versao_id) THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    UPDATE agents.qualificacao_versoes SET status = 'arquivada'
     WHERE padrao_id = v_padrao AND status = 'publicada';
    UPDATE agents.qualificacao_versoes
       SET status = 'publicada', publicada_em = now(), publicada_por = p_user_id
     WHERE id = p_versao_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.criar_rascunho_qualificacao(UUID, TEXT, UUID) TO service_role;
REVOKE ALL ON FUNCTION agents.publicar_qualificacao_versao(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.publicar_qualificacao_versao(UUID, UUID) TO service_role;

-- ── 2. the pin on the agent version ────────────────────────────────────────

ALTER TABLE agents.agent_versions
    ADD COLUMN IF NOT EXISTS qualificacao_versao_id UUID NULL REFERENCES agents.qualificacao_versoes(id);

CREATE INDEX IF NOT EXISTS idx_agent_versions_qualificacao
    ON agents.agent_versions (qualificacao_versao_id) WHERE qualificacao_versao_id IS NOT NULL;

-- Separate trigger (not a rewrite of 012's guard): the pin must target a
-- PUBLISHED standard version, is frozen once the agent version is published, and
-- a draft's pin change invalidates the judged compiled_hash (it is part of the hash).
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
        IF v_status IS DISTINCT FROM 'publicada' THEN
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

CREATE OR REPLACE TRIGGER guard_agent_version_qualificacao_pin
    BEFORE INSERT OR UPDATE OF qualificacao_versao_id ON agents.agent_versions
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_version_qualificacao_pin();

-- ── 3. per-lead tables (LGPD) ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.lead_qualificacao_registros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    lead_ref_id UUID NOT NULL,  -- NOC-REMEDIATE[qual-lead-ref-fk]: FK added after 033 (see header)
    thread_id UUID NULL REFERENCES agents.conversations(id) ON DELETE SET NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    message_id UUID NULL,
    versao_id UUID NOT NULL REFERENCES agents.qualificacao_versoes(id),
    criterio_chave TEXT NOT NULL CHECK (criterio_chave ~ '^[a-z][a-z0-9_]{1,63}$'),
    valor JSONB NOT NULL,
    trecho TEXT NULL CHECK (trecho IS NULL OR char_length(trecho) <= 160),
    fonte TEXT NOT NULL CHECK (fonte IN ('lead_informou', 'migracao', 'humano')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The model may only record what the lead said, in the lead's own words.
    CONSTRAINT lead_qualificacao_registros_trecho_lead_check CHECK (fonte <> 'lead_informou' OR trecho IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS agents.lead_imovel_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    lead_ref_id UUID NOT NULL,  -- NOC-REMEDIATE[qual-lead-ref-fk]
    thread_id UUID NULL REFERENCES agents.conversations(id) ON DELETE SET NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    codigo_imovel TEXT NOT NULL CHECK (btrim(codigo_imovel) <> '' AND char_length(codigo_imovel) <= 64),
    evento TEXT NOT NULL CHECK (evento IN
        ('oferecido', 'gostou', 'nao_gostou', 'quer_visitar', 'descartado', 'quer_ver_mais')),
    lote INT NULL CHECK (lote IS NULL OR lote >= 1),
    motivo TEXT NULL CHECK (motivo IS NULL OR char_length(motivo) <= 200),
    origem TEXT NOT NULL CHECK (origem IN ('campanha', 'similar', 'pedido_lead')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agents.lead_qualificacao_estado (
    lead_ref_id UUID PRIMARY KEY,  -- NOC-REMEDIATE[qual-lead-ref-fk]
    org_id UUID NOT NULL,
    versao_id UUID NOT NULL REFERENCES agents.qualificacao_versoes(id),
    valores JSONB NOT NULL DEFAULT '{}'::jsonb,
    score INT NOT NULL DEFAULT 0,
    scores JSONB NOT NULL DEFAULT '{}'::jsonb,  -- per axis
    estagio TEXT NOT NULL,
    faltando TEXT[] NOT NULL DEFAULT '{}',
    calculado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lead_qualificacao_registros_lead
    ON agents.lead_qualificacao_registros (org_id, lead_ref_id, created_at);
CREATE INDEX IF NOT EXISTS idx_lead_imovel_eventos_lead
    ON agents.lead_imovel_eventos (org_id, lead_ref_id, created_at);
CREATE INDEX IF NOT EXISTS idx_lead_qualificacao_estado_org ON agents.lead_qualificacao_estado (org_id);

-- Registros are append-only: no model, no API, no admin edits history. The two
-- erasure functions below are the only deleters (they set a transaction-local flag).
CREATE OR REPLACE FUNCTION agents.guard_lead_qualificacao_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('agents.erasing_lead_qualificacao', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_lead_qualificacao_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_lead_qualificacao_append_only() TO service_role;

CREATE OR REPLACE TRIGGER guard_lead_qualificacao_registros_append_only
    BEFORE UPDATE OR DELETE ON agents.lead_qualificacao_registros
    FOR EACH ROW EXECUTE FUNCTION agents.guard_lead_qualificacao_append_only();

-- Lead personal data (LGPD): service-role only, exactly like channel_inbound (025).
-- The API reads them org-scoped; a direct authenticated read never reaches a lead.
ALTER TABLE agents.lead_qualificacao_registros ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.lead_imovel_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.lead_qualificacao_estado ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.lead_qualificacao_registros;
CREATE POLICY "service_role_bypass" ON agents.lead_qualificacao_registros
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.lead_imovel_eventos;
CREATE POLICY "service_role_bypass" ON agents.lead_imovel_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.lead_qualificacao_estado;
CREATE POLICY "service_role_bypass" ON agents.lead_qualificacao_estado
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.lead_qualificacao_registros FROM anon, authenticated;
REVOKE ALL ON agents.lead_imovel_eventos FROM anon, authenticated;
REVOKE ALL ON agents.lead_qualificacao_estado FROM anon, authenticated;

-- ── 4. erasure (LGPD): by lead on request, and the 180-day inactivity purge ──

CREATE OR REPLACE FUNCTION agents.apagar_qualificacao_lead(
    p_org_id UUID,
    p_lead_ref_id UUID
) RETURNS INT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_n INT := 0;
    v_c INT;
BEGIN
    PERFORM set_config('agents.erasing_lead_qualificacao', 'on', true);
    DELETE FROM agents.lead_qualificacao_registros WHERE org_id = p_org_id AND lead_ref_id = p_lead_ref_id;
    GET DIAGNOSTICS v_c = ROW_COUNT; v_n := v_n + v_c;
    DELETE FROM agents.lead_imovel_eventos WHERE org_id = p_org_id AND lead_ref_id = p_lead_ref_id;
    GET DIAGNOSTICS v_c = ROW_COUNT; v_n := v_n + v_c;
    DELETE FROM agents.lead_qualificacao_estado WHERE org_id = p_org_id AND lead_ref_id = p_lead_ref_id;
    GET DIAGNOSTICS v_c = ROW_COUNT; v_n := v_n + v_c;
    PERFORM set_config('agents.erasing_lead_qualificacao', 'off', true);
    RETURN v_n;
END;
$$;

-- Retention purge: a lead is erased as a whole once its LAST activity (any record,
-- event or state recompute) is older than the cutoff -- never row-by-row, which
-- would silently change a live lead's computed state.
CREATE OR REPLACE FUNCTION agents.purgar_qualificacao_inativos(
    p_cutoff TIMESTAMPTZ
) RETURNS INT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_n INT := 0;
    v_c INT;
BEGIN
    PERFORM set_config('agents.erasing_lead_qualificacao', 'on', true);
    DROP TABLE IF EXISTS _qual_inativos;
    CREATE TEMP TABLE _qual_inativos ON COMMIT DROP AS
    SELECT org_id, lead_ref_id FROM (
        SELECT org_id, lead_ref_id, created_at AS ts FROM agents.lead_qualificacao_registros
        UNION ALL SELECT org_id, lead_ref_id, created_at FROM agents.lead_imovel_eventos
        UNION ALL SELECT org_id, lead_ref_id, calculado_em FROM agents.lead_qualificacao_estado
    ) a GROUP BY org_id, lead_ref_id HAVING MAX(ts) < p_cutoff;
    DELETE FROM agents.lead_qualificacao_registros r USING _qual_inativos i
     WHERE r.org_id = i.org_id AND r.lead_ref_id = i.lead_ref_id;
    GET DIAGNOSTICS v_c = ROW_COUNT; v_n := v_n + v_c;
    DELETE FROM agents.lead_imovel_eventos r USING _qual_inativos i
     WHERE r.org_id = i.org_id AND r.lead_ref_id = i.lead_ref_id;
    GET DIAGNOSTICS v_c = ROW_COUNT; v_n := v_n + v_c;
    DELETE FROM agents.lead_qualificacao_estado r USING _qual_inativos i
     WHERE r.org_id = i.org_id AND r.lead_ref_id = i.lead_ref_id;
    GET DIAGNOSTICS v_c = ROW_COUNT; v_n := v_n + v_c;
    PERFORM set_config('agents.erasing_lead_qualificacao', 'off', true);
    RETURN v_n;
END;
$$;

REVOKE ALL ON FUNCTION agents.apagar_qualificacao_lead(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.apagar_qualificacao_lead(UUID, UUID) TO service_role;
REVOKE ALL ON FUNCTION agents.purgar_qualificacao_inativos(TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.purgar_qualificacao_inativos(TIMESTAMPTZ) TO service_role;
