-- ============================================================================
-- 033_julia_v2_threads.sql -- the shared lead thread (Julia v2, A-THREAD;
-- contract products/agents/projects/julia-v2/CONTRACT.md section 6, 9, 10 W1).
--
-- One conversation row per (org, channel, channel_ref) is the THREAD of a lead,
-- shared by every agent that ever talks to the lead (Julia now, Juridico later).
-- Each message carries the author agent and the lead; each agent that took part
-- is a PARTICIPANT with its own state. This is the M1 + M2 half of the section
-- 6.5 migration (nullable columns/tables + backfill). The NOT NULL / uniqueness
-- swap (M4) is a SEPARATE file, 035, applied only after the backfill is verified.
--
--  1. agents.lead_refs -- the lead identity (SW julia_contatos.id is ref_externa);
--     the ONLY place the lead's contact lives next to the qualification records.
--  2. agents.conversations gains tipo / lead_ref_id / ultima_mensagem_lead_em.
--     (ultima_mensagem_lead_em = last LEAD message: the drain-idle clock, derived
--     once at write time instead of a messages scan per open thread.)
--  3. agents.thread_participantes (+ thread_participante_eventos audit) with the
--     one-ACTIVE-participant-per-thread partial unique index (risk 11), and
--     agents.set_participante_estado -- one transaction: compare-and-set the
--     state, append the event row, and (for a pause/resume) the agent audit row.
--  4. agents.messages gains agent_id / lead_ref_id / autor_user_id and the role
--     CHECK grows 'humano' (a human attendant) and 'evento'.
--  5. agents.thread_skill_aberturas, agents.agent_message_feedback.
--  6. agents.apagar_lead -- LGPD delete-by-lead across every thread of every
--     agent (qualification rows go with the lead_ref through their FK cascade);
--     delete_channel_conversation / purge_channel_conversations updated so the
--     retention purge cascades the same way and drops an orphaned lead_ref.
--  7. M2 backfill: every existing channel conversation becomes a thread_lead,
--     its assistant messages get agent_id, its agent becomes the ACTIVE
--     participant. Idempotent (guarded UPDATE / ON CONFLICT DO NOTHING).
--
-- Idempotent (IF NOT EXISTS / OR REPLACE / guarded DO blocks). NOT applied to any
-- database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. lead identity ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.lead_refs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    produto TEXT NOT NULL CHECK (produto = 'social-wiring'),
    -- SW julia_contatos.id: SW is authoritative for the lead identity.
    ref_externa TEXT NOT NULL CHECK (ref_externa <> ''),
    -- SW leads.id once the CRM lead exists (informational).
    crm_lead_id UUID NULL,
    -- {nome, telefone_e164}: personal data (LGPD) -- same 180-day retention.
    contato JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_agents_lead_refs_externa UNIQUE (org_id, produto, ref_externa)
);

ALTER TABLE agents.lead_refs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.lead_refs;
CREATE POLICY "service_role_bypass" ON agents.lead_refs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Lead personal data: service-role only, like every channel row.
REVOKE ALL ON agents.lead_refs FROM anon, authenticated;

CREATE OR REPLACE TRIGGER set_updated_at_lead_refs
    BEFORE UPDATE ON agents.lead_refs
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

-- ── 2. conversations: the thread ──────────────────────────────────────────

ALTER TABLE agents.conversations
    ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'chat';
ALTER TABLE agents.conversations
    ADD COLUMN IF NOT EXISTS lead_ref_id UUID NULL REFERENCES agents.lead_refs(id) ON DELETE CASCADE;
ALTER TABLE agents.conversations
    ADD COLUMN IF NOT EXISTS ultima_mensagem_lead_em TIMESTAMPTZ NULL;

-- M2: every channel conversation is a lead thread.
UPDATE agents.conversations
   SET tipo = 'thread_lead'
 WHERE channel IS NOT NULL AND tipo <> 'thread_lead';

ALTER TABLE agents.conversations DROP CONSTRAINT IF EXISTS conversations_tipo_check;
ALTER TABLE agents.conversations
    ADD CONSTRAINT conversations_tipo_check CHECK (tipo IN ('chat', 'thread_lead'));

-- The weak half of the section 6.1 CHECK: a thread is a channel row. The
-- lead_ref_id half (and NOT NULL) waits for 035, once every thread is linked.
ALTER TABLE agents.conversations DROP CONSTRAINT IF EXISTS conversations_thread_channel_check;
ALTER TABLE agents.conversations
    ADD CONSTRAINT conversations_thread_channel_check
        CHECK (tipo <> 'thread_lead' OR channel IS NOT NULL);

-- Last LEAD message of a thread (the drain-idle clock). Backfilled from messages.
UPDATE agents.conversations c
   SET ultima_mensagem_lead_em = s.ultima
  FROM (
        SELECT conversation_id, max(created_at) AS ultima
          FROM agents.messages
         WHERE role = 'user'
         GROUP BY conversation_id
       ) s
 WHERE c.id = s.conversation_id
   AND c.channel IS NOT NULL
   AND c.ultima_mensagem_lead_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_agents_conversations_lead_ref
    ON agents.conversations (lead_ref_id)
    WHERE lead_ref_id IS NOT NULL;

-- Thread lookup by channel identity WITHOUT the agent (the thread is shared).
CREATE INDEX IF NOT EXISTS idx_agents_conversations_thread_channel
    ON agents.conversations (org_id, channel)
    WHERE tipo = 'thread_lead';

-- ── 3. participants ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.thread_participantes (
    thread_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    org_id UUID NOT NULL,
    estado TEXT NOT NULL DEFAULT 'ativo'
        CHECK (estado IN ('ativo', 'pausado', 'concluido', 'encerrado', 'transferido')),
    entrou_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    saiu_em TIMESTAMPTZ NULL,
    motivo TEXT NULL,
    ultimo_turno_em TIMESTAMPTZ NULL,
    PRIMARY KEY (thread_id, agent_id)
);

ALTER TABLE agents.thread_participantes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.thread_participantes;
CREATE POLICY "service_role_bypass" ON agents.thread_participantes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.thread_participantes FROM anon, authenticated;

-- Risk 11: at most ONE active participant per thread, enforced by the database.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_thread_participantes_one_active
    ON agents.thread_participantes (thread_id)
    WHERE estado = 'ativo';

-- Drain progress / open-thread counts: per agent and state.
CREATE INDEX IF NOT EXISTS idx_agents_thread_participantes_agent_estado
    ON agents.thread_participantes (org_id, agent_id, estado);

CREATE TABLE IF NOT EXISTS agents.thread_participante_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    thread_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    de TEXT NULL,
    para TEXT NOT NULL,
    ator_tipo TEXT NOT NULL CHECK (ator_tipo IN ('agente', 'usuario', 'token', 'sistema')),
    ator_id UUID NULL,
    motivo TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.thread_participante_eventos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.thread_participante_eventos;
CREATE POLICY "service_role_bypass" ON agents.thread_participante_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.thread_participante_eventos FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_agents_thread_participante_eventos_thread
    ON agents.thread_participante_eventos (thread_id, created_at);

-- ── 4. messages: author agent, lead, human attendant ──────────────────────

ALTER TABLE agents.messages
    ADD COLUMN IF NOT EXISTS agent_id UUID NULL REFERENCES agents.agents(id);
ALTER TABLE agents.messages
    ADD COLUMN IF NOT EXISTS lead_ref_id UUID NULL REFERENCES agents.lead_refs(id) ON DELETE CASCADE;
ALTER TABLE agents.messages
    ADD COLUMN IF NOT EXISTS autor_user_id UUID NULL;

-- The role CHECK was an unnamed inline constraint (006): drop whatever CHECK
-- constrains `role` (by definition, so the lookup does not depend on the
-- generated name), then add the named, widened one.
DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.messages'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%role%'
    LOOP
        EXECUTE format('ALTER TABLE agents.messages DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.messages
    ADD CONSTRAINT messages_role_check
        CHECK (role IN ('user', 'assistant', 'system', 'humano', 'evento'));

-- Cross-agent reads and LGPD delete-by-lead.
CREATE INDEX IF NOT EXISTS idx_agents_messages_lead_ref
    ON agents.messages (lead_ref_id)
    WHERE lead_ref_id IS NOT NULL;

-- M2: the author of an existing assistant message is the agent of its channel thread.
UPDATE agents.messages m
   SET agent_id = c.agent_id
  FROM agents.conversations c
 WHERE m.conversation_id = c.id
   AND c.channel IS NOT NULL
   AND m.role = 'assistant'
   AND m.agent_id IS NULL;

-- ── 5. skill openings + message feedback ──────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.thread_skill_aberturas (
    thread_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    skill TEXT NOT NULL CHECK (skill <> ''),
    compiled_hash TEXT NOT NULL CHECK (compiled_hash <> ''),
    aberta_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, skill, compiled_hash)
);

ALTER TABLE agents.thread_skill_aberturas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.thread_skill_aberturas;
CREATE POLICY "service_role_bypass" ON agents.thread_skill_aberturas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.thread_skill_aberturas FROM anon, authenticated;

CREATE TABLE IF NOT EXISTS agents.agent_message_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    message_id UUID NOT NULL REFERENCES agents.messages(id) ON DELETE CASCADE,
    nota TEXT NOT NULL CHECK (nota IN ('like', 'dislike')),
    comentario TEXT NULL CHECK (comentario IS NULL OR char_length(comentario) <= 1000),
    user_id UUID NULL,
    origem TEXT NOT NULL CHECK (origem IN ('sw', 'studio')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.agent_message_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_message_feedback;
CREATE POLICY "service_role_bypass" ON agents.agent_message_feedback
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON agents.agent_message_feedback FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS idx_agents_agent_message_feedback_message
    ON agents.agent_message_feedback (message_id);

-- ── 6. M2 backfill: the existing agent becomes the ACTIVE participant ─────

INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado, entrou_em, ultimo_turno_em)
SELECT c.id, c.agent_id, c.org_id, 'ativo', c.created_at, c.last_message_at
  FROM agents.conversations c
 WHERE c.tipo = 'thread_lead'
ON CONFLICT (thread_id, agent_id) DO NOTHING;

-- ── 7. participant state: one transaction (state + event + audit) ─────────

-- Compare-and-set the participant's state. Returns TRUE when it moved, FALSE
-- when the participant is not in one of `p_de` (somebody else moved it first --
-- the caller re-reads). A pause/resume also lands in agent_audit_log
-- ('conversa_pausada' / 'conversa_retomada'). Raises `participante_not_found`
-- and (from the one-active index) a 23505 when another agent is ACTIVE.
CREATE OR REPLACE FUNCTION agents.set_participante_estado(
    p_org_id UUID,
    p_thread_id UUID,
    p_agent_id UUID,
    p_de TEXT[],
    p_para TEXT,
    p_ator_tipo TEXT,
    p_ator_id UUID,
    p_motivo TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_atual TEXT;
BEGIN
    SELECT estado INTO v_atual FROM agents.thread_participantes
     WHERE thread_id = p_thread_id AND agent_id = p_agent_id AND org_id = p_org_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'participante_not_found' USING ERRCODE = 'P0001';
    END IF;
    IF NOT (v_atual = ANY (p_de)) THEN
        RETURN FALSE;
    END IF;

    UPDATE agents.thread_participantes
       SET estado = p_para,
           motivo = p_motivo,
           saiu_em = CASE
               WHEN p_para = 'ativo' THEN NULL
               WHEN p_para = 'pausado' THEN saiu_em
               ELSE now()
           END
     WHERE thread_id = p_thread_id AND agent_id = p_agent_id AND org_id = p_org_id;

    INSERT INTO agents.thread_participante_eventos
        (org_id, thread_id, agent_id, de, para, ator_tipo, ator_id, motivo)
    VALUES (p_org_id, p_thread_id, p_agent_id, v_atual, p_para, p_ator_tipo, p_ator_id, p_motivo);

    IF p_para = 'pausado' THEN
        INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
        VALUES (p_org_id, p_agent_id, p_ator_id, 'conversa_pausada',
                jsonb_build_object('thread_id', p_thread_id, 'estado', v_atual),
                jsonb_build_object('thread_id', p_thread_id, 'estado', p_para, 'motivo', p_motivo));
    ELSIF v_atual = 'pausado' AND p_para = 'ativo' THEN
        INSERT INTO agents.agent_audit_log (org_id, agent_id, actor, acao, antes, depois)
        VALUES (p_org_id, p_agent_id, p_ator_id, 'conversa_retomada',
                jsonb_build_object('thread_id', p_thread_id, 'estado', v_atual),
                jsonb_build_object('thread_id', p_thread_id, 'estado', p_para, 'motivo', p_motivo));
    END IF;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION agents.set_participante_estado(UUID, UUID, UUID, TEXT[], TEXT, TEXT, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_participante_estado(UUID, UUID, UUID, TEXT[], TEXT, TEXT, UUID, TEXT)
    TO service_role;

-- ── 8. LGPD: delete-by-lead + the cascading retention RPCs ────────────────

-- Erases ONE lead across every agent, in one transaction: every thread of the
-- lead_ref (messages, approvals, the idempotency rows, participants/events/skill
-- openings/feedback via FK cascade) and the lead_ref itself (the qualification
-- tables FK lead_ref_id ON DELETE CASCADE, so they go with it). Returns the
-- counts (never any content); {"encontrado": false} when the lead is unknown --
-- the caller treats that as success (idempotent).
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

    DELETE FROM agents.messages
     WHERE org_id = p_org_id
       AND (conversation_id = ANY (v_threads) OR lead_ref_id = v_lead);
    GET DIAGNOSTICS v_msgs = ROW_COUNT;
    DELETE FROM agents.approvals WHERE conversation_id = ANY (v_threads) AND org_id = p_org_id;
    DELETE FROM agents.channel_inbound WHERE conversation_id = ANY (v_threads) AND org_id = p_org_id;
    DELETE FROM agents.conversations WHERE id = ANY (v_threads) AND org_id = p_org_id;
    DELETE FROM agents.lead_refs WHERE id = v_lead AND org_id = p_org_id;

    RETURN jsonb_build_object(
        'encontrado', true,
        'threads', COALESCE(array_length(v_threads, 1), 0),
        'mensagens', v_msgs
    );
END;
$$;

REVOKE ALL ON FUNCTION agents.apagar_lead(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.apagar_lead(UUID, TEXT, TEXT) TO service_role;

-- Deletion of ONE thread (the pre-v2 alias of "apagar meus dados"): same as 025,
-- plus the lead_ref is dropped when this was its last thread.
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
        DELETE FROM agents.lead_refs lr
         WHERE lr.id = v_lead AND lr.org_id = p_org_id
           AND NOT EXISTS (SELECT 1 FROM agents.conversations c WHERE c.lead_ref_id = lr.id);
    END IF;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION agents.delete_channel_conversation(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.delete_channel_conversation(UUID, UUID) TO service_role;

-- The 180-day purge runs on the THREAD's last activity (every agent's and the
-- lead's messages touch it) and cascades like apagar_lead: when the last thread
-- of a lead_ref is purged the lead_ref goes too (and its qualification with it).
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
    DELETE FROM agents.lead_refs lr
     WHERE lr.id = ANY (v_leads)
       AND NOT EXISTS (SELECT 1 FROM agents.conversations c WHERE c.lead_ref_id = lr.id);
    RETURN array_length(v_ids, 1);
END;
$$;

REVOKE ALL ON FUNCTION agents.purge_channel_conversations(TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.purge_channel_conversations(TIMESTAMPTZ) TO service_role;
