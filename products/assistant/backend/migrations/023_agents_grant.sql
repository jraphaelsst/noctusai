-- ============================================================================
-- Migration 023 -- Assistant: the platform grant that wires an org to the `agents` product (KB § PATTERNS/backend/platform-grants.md)
--
-- `agents` MINTS the personal channel token of the owner's assistant agent and DELIVERS it over one authenticated call
-- (`PUT /api/platform/grants/agents`, a one-shot delivery token). Nobody pastes it. This migration is the product half:
--
--   * `api_tokens`           the Assistant never had one: the delivery token (and any future M2M token) is minted into THIS
--                            table by `agents` (service role) and resolved by the seed `SupabaseApiTokenResolver`. Same
--                            SEED-1 shape as academia-de-reciclagem 008 / social-wiring 105. NO browser access (tier:service).
--   * `agent_grants`         the received channel credential, Fernet at rest (`encrypted_tokens`, the seed CredentialStore shape,
--                            same as `oauth_credentials`), one row per (org, provider='agents'); `metadata` is non-secret
--                            (grant_id, agent_key, token_prefix, scopes). Service role only (tier:service).
--   * `agent_grants_eventos` EOA: who/when/what, APPEND-ONLY, written by a TRIGGER on `agent_grants` so the change and its
--                            event are ONE transaction: concedido (first grant) / rotacionado (a new credential replaced the
--                            old) / revogado (the row deleted by the platform's DELETE). Holds the token PREFIX, never the secret.
-- Forward-only + idempotent (re-apply safe).
-- ============================================================================
SET search_path = assistant, public;

-- ----- api_tokens ---------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assistant.api_tokens (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL,
    label               text NOT NULL,
    token_hash          text NOT NULL UNIQUE,
    token_prefix        text NOT NULL,
    scopes              text[] NOT NULL DEFAULT '{}',
    created_by          uuid,
    created_at          timestamptz NOT NULL DEFAULT now(),
    last_used_at        timestamptz,
    revoked_at          timestamptz,
    expires_at          timestamptz,                      -- NULL = no expiry (revocation + last_used_at still apply)
    principal_agent_id  uuid,
    issuer              text,
    human_personal      boolean NOT NULL DEFAULT false,
    minted_by           uuid
);
CREATE INDEX IF NOT EXISTS idx_assistant_api_tokens_org ON assistant.api_tokens (org_id) WHERE revoked_at IS NULL;

ALTER TABLE assistant.api_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.api_tokens;
CREATE POLICY "service_role_bypass" ON assistant.api_tokens FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON assistant.api_tokens FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.api_tokens TO service_role;
COMMENT ON TABLE assistant.api_tokens IS 'tier:service';

-- ----- agent_grants ---------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assistant.agent_grants (
    org_id           text NOT NULL,
    provider         text NOT NULL CHECK (provider = 'agents'),
    encrypted_tokens text NOT NULL,                       -- Fernet(JSON({"value": <channel token>})); never plaintext
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- non-secret: grant_id, agent_key, agent_id, token_prefix, scopes
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, provider)
);

ALTER TABLE assistant.agent_grants ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.agent_grants;
CREATE POLICY "service_role_bypass" ON assistant.agent_grants FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON assistant.agent_grants FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.agent_grants TO service_role;
COMMENT ON TABLE assistant.agent_grants IS 'tier:service';

-- ----- agent_grants_eventos (append-only) -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assistant.agent_grants_eventos (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       text NOT NULL,
    event_type   text NOT NULL CHECK (event_type IN ('concedido', 'rotacionado', 'revogado')),
    agent_key    text,                                    -- non-secret: which agent the platform wired
    grant_id     text,                                    -- agents' grant row id
    token_prefix text,                                    -- non-secret display prefix (noc_ab12...), NEVER the secret
    actor_kind   text NOT NULL DEFAULT 'integration' CHECK (actor_kind IN ('user', 'agent', 'system', 'integration')),
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assistant_agent_grants_eventos_org ON assistant.agent_grants_eventos (org_id, occurred_at DESC);

ALTER TABLE assistant.agent_grants_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.agent_grants_eventos;
CREATE POLICY "service_role_bypass" ON assistant.agent_grants_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON assistant.agent_grants_eventos FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.agent_grants_eventos TO service_role;
COMMENT ON TABLE assistant.agent_grants_eventos IS 'tier:service';

CREATE OR REPLACE FUNCTION assistant.guard_agent_grants_eventos_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$ BEGIN RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001'; END; $$;
REVOKE ALL ON FUNCTION assistant.guard_agent_grants_eventos_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.guard_agent_grants_eventos_append_only() TO service_role;
DROP TRIGGER IF EXISTS guard_agent_grants_eventos_append_only ON assistant.agent_grants_eventos;
CREATE TRIGGER guard_agent_grants_eventos_append_only
    BEFORE UPDATE OR DELETE ON assistant.agent_grants_eventos
    FOR EACH ROW EXECUTE FUNCTION assistant.guard_agent_grants_eventos_append_only();

CREATE OR REPLACE FUNCTION assistant.registrar_agent_grant_evento()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_type text;
    v_row  assistant.agent_grants;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_type := 'concedido'; v_row := NEW;
    ELSIF TG_OP = 'DELETE' THEN
        v_type := 'revogado'; v_row := OLD;
    ELSIF NEW.encrypted_tokens IS DISTINCT FROM OLD.encrypted_tokens THEN
        v_type := 'rotacionado'; v_row := NEW;      -- a new credential replaced the old one
    ELSE
        RETURN NEW;                                  -- metadata-only touch: nothing the owner measures
    END IF;

    INSERT INTO assistant.agent_grants_eventos (org_id, event_type, agent_key, grant_id, token_prefix)
    VALUES (v_row.org_id, v_type, v_row.metadata ->> 'agent_key', v_row.metadata ->> 'grant_id', v_row.metadata ->> 'token_prefix');
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION assistant.registrar_agent_grant_evento() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.registrar_agent_grant_evento() TO service_role;

DROP TRIGGER IF EXISTS registrar_agent_grant_evento ON assistant.agent_grants;
CREATE TRIGGER registrar_agent_grant_evento
    AFTER INSERT OR UPDATE OR DELETE ON assistant.agent_grants
    FOR EACH ROW EXECUTE FUNCTION assistant.registrar_agent_grant_evento();
