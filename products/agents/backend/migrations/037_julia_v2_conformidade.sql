-- ============================================================================
-- 037_julia_v2_conformidade.sql -- Julia v2, slice A-RT (CONTRACT sections 3.5 E3,
-- 6.4, 10.3; owner round 2: IP protection + abuse limits).
--
-- 1. agents.conformidade_regras / agents.conformidade_violacoes -- the post-turn
--    conformance detectors' per-agent on/off + policy (registrar | bloquear) and the
--    violations they write. Content (the correction text a block re-runs with) is a
--    REGISTRY KEY into agent_version_textos (`mensagem_correcao_texto_chave`), never a
--    string here (D2/D3). A rule with no row runs on the code-side default policy
--    (registrar everywhere; bloquear for vazamento_prompt -- the owner's IP mandate).
-- 2. agents.conformidade_impressoes -- the prompt-leak fingerprint of a version
--    (hashed 12-token shingles of the compiled prompt + texts), computed at publish.
--    Hashes only: the fingerprint can detect a leak but cannot reconstruct the prompt.
-- 3. agents.canal_limites -- abuse limits per agent instance, in DATA (per-chat turn
--    rate, per-chat daily turns and spend, distinct properties offered per thread,
--    gate-refusal and tool-error budgets of a turn). Defaults live in the column
--    DEFAULTs; the application upserts a row on first use.
-- 4. NOC-REMEDIATE[qual-lead-ref-fk] closed: lead_ref_id of the five per-lead
--    qualification tables becomes a FOREIGN KEY to agents.lead_refs ON DELETE CASCADE.
--    The append-only guard (032) refuses a DELETE unless the transaction-local flag
--    `agents.erasing_lead_qualificacao` is on, so the three functions that delete a
--    lead_ref (apagar_lead, delete_channel_conversation, purge_channel_conversations)
--    are re-created to raise the flag around that delete (cascade = erasure).
--    lead_identificacao_acessos (the access audit, no personal data) deliberately keeps
--    NO FK and NO erasure exception: accountability outlives the lead.
--
-- 5. agents.transferir_thread accepts 'concluido' as the giver's end state, so
--    concluir_qualificacao writes the hand-off note to the owner and moves the
--    participant in ONE transaction.
--
-- Idempotent. NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. conformance rules + violations ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.conformidade_regras (
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id) ON DELETE CASCADE,
    regra TEXT NOT NULL CHECK (regra ~ '^[a-z][a-z0-9_]{2,63}$'),
    ativo BOOLEAN NOT NULL DEFAULT true,
    politica TEXT NOT NULL DEFAULT 'registrar' CHECK (politica IN ('registrar', 'bloquear')),
    mensagem_correcao_texto_chave TEXT NULL
        CHECK (mensagem_correcao_texto_chave IS NULL OR mensagem_correcao_texto_chave ~ '^[a-z0-9]+(\.[a-z0-9_]+)+$'),
    -- Rule parameters that are DATA (patterns the deterministic escalations match, the property-code
    -- regex of imovel_sem_ferramenta, ...). Never read back to a model verbatim.
    parametros JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_id, regra)
);

CREATE TABLE IF NOT EXISTS agents.conformidade_violacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id) ON DELETE CASCADE,
    thread_id UUID NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    lead_ref_id UUID NULL REFERENCES agents.lead_refs(id) ON DELETE CASCADE,
    message_id UUID NULL REFERENCES agents.messages(id) ON DELETE SET NULL,
    regra TEXT NOT NULL CHECK (regra ~ '^[a-z][a-z0-9_]{2,63}$'),
    politica TEXT NOT NULL CHECK (politica IN ('registrar', 'bloquear', 'sinal')),
    bloqueada BOOLEAN NOT NULL DEFAULT false,
    -- Codes and counts only (never the reply text, never the lead's words, never a prompt fragment).
    detalhe JSONB NOT NULL DEFAULT '{}'::jsonb,
    compiled_hash TEXT NULL,
    origem TEXT NOT NULL DEFAULT 'canal' CHECK (origem IN ('canal', 'teste', 'eval')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conformidade_violacoes_agent
    ON agents.conformidade_violacoes (org_id, agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conformidade_violacoes_thread
    ON agents.conformidade_violacoes (thread_id, created_at) WHERE thread_id IS NOT NULL;

-- ── 2. prompt-leak fingerprint per version ─────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.conformidade_impressoes (
    version_id UUID PRIMARY KEY REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    shingle_tokens INTEGER NOT NULL DEFAULT 12 CHECK (shingle_tokens BETWEEN 4 AND 64),
    -- Hashes (first 8 bytes of sha256, as signed bigint) of every normalised k-token window.
    shingles BIGINT[] NOT NULL DEFAULT '{}',
    criada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 3. abuse limits (data, per agent instance) ─────────────────────────────

CREATE TABLE IF NOT EXISTS agents.canal_limites (
    agent_id UUID PRIMARY KEY REFERENCES agents.agents(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    janela_segundos INTEGER NOT NULL DEFAULT 60 CHECK (janela_segundos BETWEEN 1 AND 86400),
    max_turnos_janela INTEGER NOT NULL DEFAULT 6 CHECK (max_turnos_janela BETWEEN 1 AND 1000),
    max_turnos_dia INTEGER NOT NULL DEFAULT 200 CHECK (max_turnos_dia BETWEEN 1 AND 100000),
    max_custo_dia_usd NUMERIC(10, 4) NOT NULL DEFAULT 2.0 CHECK (max_custo_dia_usd > 0),
    max_imoveis_distintos INTEGER NOT NULL DEFAULT 30 CHECK (max_imoveis_distintos BETWEEN 1 AND 1000),
    max_recusas_por_turno INTEGER NOT NULL DEFAULT 2 CHECK (max_recusas_por_turno BETWEEN 1 AND 20),
    max_erros_ferramenta_por_turno INTEGER NOT NULL DEFAULT 3 CHECK (max_erros_ferramenta_por_turno BETWEEN 1 AND 20),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.conformidade_regras ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.conformidade_violacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.conformidade_impressoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.canal_limites ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.conformidade_regras;
CREATE POLICY "service_role_bypass" ON agents.conformidade_regras
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.conformidade_violacoes;
CREATE POLICY "service_role_bypass" ON agents.conformidade_violacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.conformidade_impressoes;
CREATE POLICY "service_role_bypass" ON agents.conformidade_impressoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.canal_limites;
CREATE POLICY "service_role_bypass" ON agents.canal_limites
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Platform-internal tables: no direct client access of any kind (the API reads them org-scoped).
REVOKE ALL ON agents.conformidade_regras FROM anon, authenticated;
REVOKE ALL ON agents.conformidade_violacoes FROM anon, authenticated;
REVOKE ALL ON agents.conformidade_impressoes FROM anon, authenticated;
REVOKE ALL ON agents.canal_limites FROM anon, authenticated;

-- ── 4. lead_ref_id foreign keys (NOC-REMEDIATE[qual-lead-ref-fk]) ──────────
--
-- NOT VALID first, VALIDATE second: an orphan row fails the migration LOUDLY (a per-lead row
-- without a lead cannot be linked or erased by lead -- it must be looked at, not deleted here).

DO $$
DECLARE
    t TEXT;
    c TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'lead_qualificacao_registros', 'lead_imovel_eventos', 'lead_qualificacao_estado',
        'lead_qualificacao_confirmacoes', 'lead_identificacao'
    ] LOOP
        c := t || '_lead_ref_fk';
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conname = c AND conrelid = ('agents.' || t)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE agents.%I ADD CONSTRAINT %I FOREIGN KEY (lead_ref_id) '
                'REFERENCES agents.lead_refs(id) ON DELETE CASCADE NOT VALID', t, c);
        END IF;
        EXECUTE format('ALTER TABLE agents.%I VALIDATE CONSTRAINT %I', t, c);
    END LOOP;
END
$$;

-- The functions that delete a lead_ref now cascade into the append-only qualification tables:
-- they raise the erasure flag (transaction-local) around that delete, exactly like
-- agents.apagar_qualificacao_lead does for its own deletes.

CREATE OR REPLACE FUNCTION agents.apagar_lead(
    p_org_id UUID,
    p_produto TEXT,
    p_ref_externa TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_lead UUID;
    v_threads UUID[];
    v_msgs INTEGER;
BEGIN
    SELECT id INTO v_lead FROM agents.lead_refs
     WHERE org_id = p_org_id AND produto = p_produto AND ref_externa = p_ref_externa
     FOR UPDATE;
    IF v_lead IS NULL THEN
        RETURN jsonb_build_object('encontrado', false);
    END IF;

    SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]) INTO v_threads
      FROM agents.conversations
     WHERE lead_ref_id = v_lead AND org_id = p_org_id;

    PERFORM set_config('agents.erasing_lead_qualificacao', 'on', true);
    DELETE FROM agents.messages
     WHERE org_id = p_org_id
       AND (conversation_id = ANY (v_threads) OR lead_ref_id = v_lead);
    GET DIAGNOSTICS v_msgs = ROW_COUNT;
    DELETE FROM agents.approvals WHERE conversation_id = ANY (v_threads) AND org_id = p_org_id;
    DELETE FROM agents.channel_inbound WHERE conversation_id = ANY (v_threads) AND org_id = p_org_id;
    DELETE FROM agents.conversations WHERE id = ANY (v_threads) AND org_id = p_org_id;
    DELETE FROM agents.lead_refs WHERE id = v_lead AND org_id = p_org_id;
    PERFORM set_config('agents.erasing_lead_qualificacao', 'off', true);

    RETURN jsonb_build_object(
        'encontrado', true,
        'threads', COALESCE(array_length(v_threads, 1), 0),
        'mensagens', v_msgs
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.apagar_lead(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.apagar_lead(UUID, TEXT, TEXT) TO service_role;

CREATE OR REPLACE FUNCTION agents.delete_channel_conversation(
    p_org_id UUID,
    p_conversation_id UUID
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_found UUID;
    v_lead UUID;
BEGIN
    SELECT id, lead_ref_id INTO v_found, v_lead FROM agents.conversations
     WHERE id = p_conversation_id AND org_id = p_org_id AND channel IS NOT NULL
     FOR UPDATE;
    IF v_found IS NULL THEN
        RETURN FALSE;
    END IF;
    DELETE FROM agents.messages WHERE conversation_id = v_found AND org_id = p_org_id;
    DELETE FROM agents.approvals WHERE conversation_id = v_found AND org_id = p_org_id;
    DELETE FROM agents.channel_inbound WHERE conversation_id = v_found AND org_id = p_org_id;
    DELETE FROM agents.conversations WHERE id = v_found AND org_id = p_org_id;
    IF v_lead IS NOT NULL THEN
        PERFORM set_config('agents.erasing_lead_qualificacao', 'on', true);
        DELETE FROM agents.lead_refs lr
         WHERE lr.id = v_lead AND lr.org_id = p_org_id
           AND NOT EXISTS (SELECT 1 FROM agents.conversations c WHERE c.lead_ref_id = lr.id);
        PERFORM set_config('agents.erasing_lead_qualificacao', 'off', true);
    END IF;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION agents.delete_channel_conversation(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.delete_channel_conversation(UUID, UUID) TO service_role;

CREATE OR REPLACE FUNCTION agents.purge_channel_conversations(
    p_cutoff TIMESTAMPTZ
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_ids UUID[];
    v_leads UUID[];
BEGIN
    SELECT COALESCE(array_agg(id), ARRAY[]::UUID[]),
           COALESCE(array_agg(lead_ref_id) FILTER (WHERE lead_ref_id IS NOT NULL), ARRAY[]::UUID[])
      INTO v_ids, v_leads
      FROM agents.conversations
     WHERE channel IS NOT NULL
       AND COALESCE(last_message_at, created_at) < p_cutoff
       AND (turn_lock_until IS NULL OR turn_lock_until < now());
    IF array_length(v_ids, 1) IS NULL THEN
        RETURN 0;
    END IF;
    DELETE FROM agents.messages WHERE conversation_id = ANY (v_ids);
    DELETE FROM agents.approvals WHERE conversation_id = ANY (v_ids);
    DELETE FROM agents.channel_inbound WHERE conversation_id = ANY (v_ids);
    DELETE FROM agents.conversations WHERE id = ANY (v_ids);
    PERFORM set_config('agents.erasing_lead_qualificacao', 'on', true);
    DELETE FROM agents.lead_refs lr
     WHERE lr.id = ANY (v_leads)
       AND NOT EXISTS (SELECT 1 FROM agents.conversations c WHERE c.lead_ref_id = lr.id);
    PERFORM set_config('agents.erasing_lead_qualificacao', 'off', true);
    RETURN array_length(v_ids, 1);
END;
$$;

REVOKE ALL ON FUNCTION agents.purge_channel_conversations(TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.purge_channel_conversations(TIMESTAMPTZ) TO service_role;

-- ── 5. a hand-off may end the giver `concluido` (concluir_qualificacao) ────
--
-- Same function as 033 with ONE change: p_para_estado also accepts 'concluido', so concluding the
-- qualification writes the hand-off note to the owner and moves the participant in one transaction.

CREATE OR REPLACE FUNCTION agents.transferir_thread(
    p_org_id UUID,
    p_thread_id UUID,
    p_de_agent_id UUID,
    p_de TEXT[],
    p_para_estado TEXT,
    p_para_tipo TEXT,
    p_para_agent_id UUID,
    p_para_user_id UUID,
    p_para_papel TEXT,
    p_motivo_codigo TEXT,
    p_resumo TEXT,
    p_perguntas JSONB,
    p_compromissos JSONB,
    p_ator_tipo TEXT,
    p_ator_id UUID,
    p_perfil JSONB DEFAULT '{}'::jsonb,
    p_identificacao_completa BOOLEAN DEFAULT false,
    p_identificacao_mascarada JSONB DEFAULT '{}'::jsonb
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_id UUID;
    v_lead UUID;
BEGIN
    IF p_para_estado NOT IN ('transferido', 'pausado', 'concluido') THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = 'P0001';
    END IF;
    SELECT lead_ref_id INTO v_lead FROM agents.conversations
     WHERE id = p_thread_id AND org_id = p_org_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'participante_not_found' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO agents.thread_handoffs (
        org_id, thread_id, lead_ref_id, de_agent_id, para_tipo, para_agent_id, para_user_id, para_papel,
        motivo_codigo, resumo, perguntas_abertas, compromissos, perfil, identificacao_completa, identificacao_mascarada
    ) VALUES (
        p_org_id, p_thread_id, v_lead, p_de_agent_id, p_para_tipo, p_para_agent_id, p_para_user_id, p_para_papel,
        p_motivo_codigo, p_resumo, COALESCE(p_perguntas, '[]'::jsonb), COALESCE(p_compromissos, '[]'::jsonb),
        COALESCE(p_perfil, '{}'::jsonb), COALESCE(p_identificacao_completa, false), COALESCE(p_identificacao_mascarada, '{}'::jsonb)
    ) RETURNING id INTO v_id;

    IF NOT agents.set_participante_estado(
        p_org_id, p_thread_id, p_de_agent_id, p_de, p_para_estado, p_ator_tipo, p_ator_id, p_motivo_codigo, NULL
    ) THEN
        RAISE EXCEPTION 'participante_estado_mudou' USING ERRCODE = 'P0001';
    END IF;

    IF p_para_tipo = 'agente' THEN
        INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado, motivo)
        VALUES (p_thread_id, p_para_agent_id, p_org_id, 'ativo', p_motivo_codigo)
        ON CONFLICT (thread_id, agent_id) DO UPDATE
            SET estado = 'ativo', saiu_em = NULL, motivo = EXCLUDED.motivo, pausado_ate = NULL;
        INSERT INTO agents.thread_participante_eventos
            (org_id, thread_id, agent_id, de, para, ator_tipo, ator_id, motivo)
        VALUES (p_org_id, p_thread_id, p_para_agent_id, NULL, 'ativo', p_ator_tipo, p_ator_id, p_motivo_codigo);
    END IF;
    RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.transferir_thread(UUID, UUID, UUID, TEXT[], TEXT, TEXT, UUID, UUID, TEXT, TEXT, TEXT, JSONB, JSONB, TEXT, UUID, JSONB, BOOLEAN, JSONB)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.transferir_thread(UUID, UUID, UUID, TEXT[], TEXT, TEXT, UUID, UUID, TEXT, TEXT, TEXT, JSONB, JSONB, TEXT, UUID, JSONB, BOOLEAN, JSONB)
    TO service_role;
