-- ============================================================================
-- 006_agents.sql — Julia's agent control plane (contract §E.1)
--
-- Tables: agents, agent_personas, conversations, messages, approvals.
-- Every table carries the common columns (id, org_id, created_at, updated_at),
-- RLS enabled with an org-scoped SELECT policy via public.current_org_id()
-- plus a literal "service_role_bypass" policy (the keeper
-- check_admin_endpoint_service_role_bypass matches this name verbatim — see
-- KB § PATTERNS/backend/database-rls.md). Routes use the admin client and
-- therefore bypass RLS by design (contract §E.0 / §B.0); RLS here is defence
-- in depth, never the authorization boundary.
--
-- TURN-LOCK DESIGN (G1 engineer decision, see CONTRACT §E.2
-- "one in-flight turn per conversation, DB lock"):
--
-- `conversations` carries two extra columns beyond §E.1's list:
--   turn_lock_until       timestamptz null
--   turn_lock_instance_id text        null
--
-- `try_acquire_turn` is a single atomic `UPDATE ... WHERE` — no advisory
-- lock, no `SELECT ... FOR UPDATE` + separate `UPDATE` pair. Postgres holds
-- the row lock for the full duration of one `UPDATE` statement, so the
-- read-the-current-lock-state-and-decide-whether-to-write step is atomic
-- by construction:
--
--   UPDATE conversations
--   SET turn_lock_until = now() + ttl, turn_lock_instance_id = <instance>
--   WHERE id = <id> AND org_id = <org_id>
--     AND (turn_lock_until IS NULL OR turn_lock_until < now())
--   RETURNING id;
--
-- Zero rows returned ⇒ another instance already holds a live lock ⇒ the
-- store call returns False (409 `turn_in_progress` at the router, wave 1b).
-- `release_turn` clears both columns, scoped by id AND org_id AND
-- turn_lock_instance_id — a stale/foreign instance can never clear a lock
-- it doesn't hold (the same instance-scoping discipline the approvals
-- startup-expiry sweep uses, contract §E.2 "never other instances' rows").
--
-- PERSONA VERSIONING: `create_persona_version` is a SECURITY DEFINER
-- PL/pgSQL function (declared below) so the "insert versao = max+1 and flip
-- ativa" pair runs inside ONE Postgres transaction — a PostgREST `.rpc()`
-- call is one HTTP request = one transaction, unlike two separate
-- `.update()` / `.insert()` calls from the admin client which would each
-- open their own transaction and could interleave under concurrent writes.
-- ============================================================================

SET search_path = agents, public;

-- ────────────────────────────────────────────────────────────────────────
-- agents — the two control-plane rows (julia / one-chat), per org.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    key TEXT NOT NULL CHECK (key <> ''),
    nome TEXT NOT NULL,
    runtime TEXT NOT NULL CHECK (runtime IN ('claude_sdk', 'external')),
    owner_product TEXT NULL,
    external_ref JSONB NULL,
    ativo BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, key)
);

ALTER TABLE agents.agents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agents_select_own_org" ON agents.agents
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agents
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agents_org ON agents.agents(org_id);

CREATE OR REPLACE FUNCTION agents.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE OR REPLACE TRIGGER set_updated_at_agents
    BEFORE UPDATE ON agents.agents
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- agent_personas — append-only-by-version. Exactly one ativa row per agent.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.agent_personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    versao INT NOT NULL,
    nome TEXT NOT NULL,
    papel TEXT NOT NULL,
    tom TEXT NULL,
    system_prompt_append TEXT NULL,
    model TEXT NOT NULL CHECK (model IN ('claude-opus-5', 'claude-sonnet-5')),
    effort TEXT NOT NULL CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max')),
    idioma TEXT NOT NULL DEFAULT 'pt-BR',
    org_display_name TEXT NULL,
    project_display_name TEXT NULL,
    ativa BOOLEAN NOT NULL DEFAULT false,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, versao)
);

ALTER TABLE agents.agent_personas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_personas_select_own_org" ON agents.agent_personas
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.agent_personas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_agent_personas_org ON agents.agent_personas(org_id);

-- Exactly one active version per agent.
CREATE UNIQUE INDEX agent_personas_one_active_idx
    ON agents.agent_personas (agent_id) WHERE ativa;

CREATE OR REPLACE TRIGGER set_updated_at_agent_personas
    BEFORE UPDATE ON agents.agent_personas
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

-- Atomic "insert next version, flip ativa" — see header. SECURITY DEFINER +
-- locked search_path so it behaves identically regardless of caller role.
CREATE OR REPLACE FUNCTION agents.create_persona_version(
    p_org_id UUID,
    p_agent_id UUID,
    p_nome TEXT,
    p_papel TEXT,
    p_tom TEXT,
    p_system_prompt_append TEXT,
    p_model TEXT,
    p_effort TEXT,
    p_idioma TEXT,
    p_org_display_name TEXT,
    p_project_display_name TEXT,
    p_created_by UUID
) RETURNS agents.agent_personas
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_next_versao INT;
    v_row agents.agent_personas;
BEGIN
    SELECT COALESCE(MAX(versao), 0) + 1 INTO v_next_versao
    FROM agents.agent_personas
    WHERE org_id = p_org_id AND agent_id = p_agent_id;

    UPDATE agents.agent_personas
    SET ativa = false
    WHERE org_id = p_org_id AND agent_id = p_agent_id AND ativa;

    INSERT INTO agents.agent_personas (
        org_id, agent_id, versao, nome, papel, tom, system_prompt_append,
        model, effort, idioma, org_display_name, project_display_name,
        ativa, created_by
    ) VALUES (
        p_org_id, p_agent_id, v_next_versao, p_nome, p_papel, p_tom,
        p_system_prompt_append, p_model, p_effort,
        COALESCE(p_idioma, 'pt-BR'), p_org_display_name,
        p_project_display_name, true, p_created_by
    )
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;


-- ────────────────────────────────────────────────────────────────────────
-- conversations
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    owner_user_id UUID NOT NULL,
    titulo TEXT NULL,
    sdk_session_id TEXT NULL,
    status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'arquivada')),
    last_message_at TIMESTAMPTZ NULL,
    -- One-in-flight-turn support — see header "TURN-LOCK DESIGN".
    turn_lock_until TIMESTAMPTZ NULL,
    turn_lock_instance_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "conversations_select_own_org" ON agents.conversations
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.conversations
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_conversations_org ON agents.conversations(org_id);
CREATE INDEX idx_agents_conversations_owner ON agents.conversations(org_id, owner_user_id);

CREATE OR REPLACE TRIGGER set_updated_at_conversations
    BEFORE UPDATE ON agents.conversations
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- messages
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    conversation_id UUID NOT NULL REFERENCES agents.conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    texto TEXT NOT NULL,
    blocks JSONB NOT NULL DEFAULT '[]'::jsonb,
    token_usage JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "messages_select_own_org" ON agents.messages
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.messages
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_messages_org ON agents.messages(org_id);
CREATE INDEX idx_agents_messages_conversation ON agents.messages(conversation_id, created_at);

CREATE OR REPLACE TRIGGER set_updated_at_messages
    BEFORE UPDATE ON agents.messages
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- approvals
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    conversation_id UUID NOT NULL REFERENCES agents.conversations(id),
    tool_name TEXT NOT NULL,
    tool_input JSONB NOT NULL,
    classe TEXT NOT NULL DEFAULT 'escrita' CHECK (classe IN ('escrita')),
    resumo TEXT NOT NULL,
    diff JSONB NULL,
    decision TEXT NOT NULL DEFAULT 'pendente'
        CHECK (decision IN ('pendente', 'aprovada', 'negada', 'expirada')),
    decided_by UUID NULL,
    decided_at TIMESTAMPTZ NULL,
    requested_by UUID NOT NULL,
    -- Scopes the startup-expiry sweep to THIS process instance only
    -- (contract §E.2 "never other instances' rows", security finding 5).
    instance_id TEXT NOT NULL,
    consumed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.approvals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "approvals_select_own_org" ON agents.approvals
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.approvals
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_approvals_org ON agents.approvals(org_id);
CREATE INDEX idx_agents_approvals_conversation ON agents.approvals(conversation_id);
CREATE INDEX idx_agents_approvals_instance_pending
    ON agents.approvals(instance_id) WHERE decision = 'pendente';

CREATE OR REPLACE TRIGGER set_updated_at_approvals
    BEFORE UPDATE ON agents.approvals
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();
