-- ============================================================================
-- Migration 019 -- Assistant: the Google connection (D50) -- per-org OAuth grant + the single-use consent state
--
-- * `oauth_credentials` -- the seed `SupabaseCredentialStore` shape verbatim: one row per (org_id, provider), the token
--   bundle Fernet-encrypted into `encrypted_tokens` (ENCRYPTION_KEY), `metadata` = non-secret facts only (granted
--   scopes, connected account email, who connected, needs_reconnection). Integration keys live HERE per org, never .env.
-- * `oauth_states` -- the seed `SupabaseOAuthStateStore` shape: the consent `state` is stored as its SHA-256 only, the
--   PKCE verifier Fernet-encrypted, 10 minute expiry, bound to the starting BROWSER (`binding_hash` = sha256 of the nonce in
--   its host-only cookie), consumed by a single DELETE ... RETURNING (single-use).
-- * `google_conexao_eventos` -- append-only: connect / disconnect / reconnect_needed (who, when, account, scopes), written by
--   a trigger on `oauth_credentials` in the SAME transaction as the change; `google_desconectar` is the deleting RPC.
--
-- Access: service role only (no browser grant, no browser policy); every route is admin-gated or state-gated in the
-- backend. Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it -- the tech-lead applies it.
-- ============================================================================

SET search_path = assistant, public;

CREATE TABLE IF NOT EXISTS assistant.oauth_credentials (
    org_id           text NOT NULL,
    provider         text NOT NULL,
    encrypted_tokens text NOT NULL,                       -- Fernet(JSON(bundle)); never plaintext
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- non-secret: scopes, account_email, connected_by, needs_reconnection
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, provider)
);

ALTER TABLE assistant.oauth_credentials ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.oauth_credentials;
CREATE POLICY "service_role_bypass" ON assistant.oauth_credentials FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.oauth_credentials IS 'tier:org';
REVOKE ALL ON assistant.oauth_credentials FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.oauth_credentials TO service_role;

CREATE TABLE IF NOT EXISTS assistant.oauth_states (
    state_hash              text PRIMARY KEY,              -- sha256(state), hex: the raw state is never stored
    binding_hash            text NOT NULL,                 -- sha256(browser nonce): the callback must present the cookie
    provider                text NOT NULL,
    org_id                  text NOT NULL,
    user_id                 text NOT NULL,
    redirect_uri            text NOT NULL,
    encrypted_code_verifier text NOT NULL,                 -- Fernet(PKCE code_verifier)
    expires_at              timestamptz NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assistant_oauth_states_expires ON assistant.oauth_states (expires_at);

ALTER TABLE assistant.oauth_states ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.oauth_states;
CREATE POLICY "service_role_bypass" ON assistant.oauth_states FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.oauth_states IS 'tier:org';
REVOKE ALL ON assistant.oauth_states FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.oauth_states TO service_role;

-- ----- Events (append-only): who / when / what, written by a TRIGGER on oauth_credentials so the grant change and its
-- event are ONE transaction (G-7). connect = a grant stored (first consent or re-consent); disconnect = the grant
-- deleted (by `google_desconectar`, which names the actor); reconnect_needed = the refresh token died (system). -----
CREATE TABLE IF NOT EXISTS assistant.google_conexao_eventos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        text NOT NULL,
    event_type    text NOT NULL CHECK (event_type IN ('connect', 'disconnect', 'reconnect_needed')),
    account_email text,                                   -- non-secret: the connected Google account
    scopes        jsonb NOT NULL DEFAULT '[]'::jsonb,     -- granted scopes at that moment
    actor_id      uuid,
    actor_kind    text NOT NULL DEFAULT 'user' CHECK (actor_kind IN ('user', 'agent', 'system', 'integration')),
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_google_conexao_eventos_org ON assistant.google_conexao_eventos (org_id, occurred_at DESC);

ALTER TABLE assistant.google_conexao_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.google_conexao_eventos;
CREATE POLICY "service_role_bypass" ON assistant.google_conexao_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.google_conexao_eventos IS 'tier:org';
REVOKE ALL ON assistant.google_conexao_eventos FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.google_conexao_eventos TO service_role;

CREATE OR REPLACE FUNCTION assistant.guard_google_conexao_eventos_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$ BEGIN RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001'; END; $$;
REVOKE ALL ON FUNCTION assistant.guard_google_conexao_eventos_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.guard_google_conexao_eventos_append_only() TO service_role;
DROP TRIGGER IF EXISTS guard_google_conexao_eventos_append_only ON assistant.google_conexao_eventos;
CREATE TRIGGER guard_google_conexao_eventos_append_only
    BEFORE UPDATE OR DELETE ON assistant.google_conexao_eventos
    FOR EACH ROW EXECUTE FUNCTION assistant.guard_google_conexao_eventos_append_only();

CREATE OR REPLACE FUNCTION assistant.registrar_google_conexao_evento()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE
    v_type  text;
    v_meta  jsonb;
    v_org   text;
    v_actor text;
    v_kind  text := 'user';
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_type := 'connect'; v_meta := NEW.metadata; v_org := NEW.org_id;
        v_actor := NEW.metadata ->> 'connected_by';
    ELSIF TG_OP = 'DELETE' THEN
        v_type := 'disconnect'; v_meta := OLD.metadata; v_org := OLD.org_id;
        v_actor := nullif(current_setting('assistant.google_actor', true), '');
    ELSE
        v_meta := NEW.metadata; v_org := NEW.org_id;
        IF coalesce((NEW.metadata ->> 'needs_reconnection')::boolean, false)
           AND NOT coalesce((OLD.metadata ->> 'needs_reconnection')::boolean, false) THEN
            v_type := 'reconnect_needed'; v_kind := 'system';
        ELSIF NEW.encrypted_tokens IS DISTINCT FROM OLD.encrypted_tokens THEN
            v_type := 'connect'; v_actor := NEW.metadata ->> 'connected_by';   -- re-consent
        ELSE
            RETURN NEW;                                                        -- nothing the owner measures
        END IF;
    END IF;

    INSERT INTO assistant.google_conexao_eventos (org_id, event_type, account_email, scopes, actor_id, actor_kind)
    VALUES (v_org, v_type, v_meta ->> 'account_email', coalesce(v_meta -> 'scopes', '[]'::jsonb),
            CASE WHEN v_kind = 'user' AND v_actor ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                 THEN v_actor::uuid END,
            CASE WHEN v_kind = 'user' AND (v_actor IS NULL OR v_actor !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
                 THEN 'system' ELSE v_kind END);
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION assistant.registrar_google_conexao_evento() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.registrar_google_conexao_evento() TO service_role;

DROP TRIGGER IF EXISTS registrar_google_conexao_evento ON assistant.oauth_credentials;
CREATE TRIGGER registrar_google_conexao_evento
    AFTER INSERT OR UPDATE OR DELETE ON assistant.oauth_credentials
    FOR EACH ROW EXECUTE FUNCTION assistant.registrar_google_conexao_evento();

-- google_desconectar: the ONLY way the app deletes a grant. One RPC = one transaction: it names the actor (a
-- transaction-local setting the delete trigger reads) and deletes, so the `disconnect` event carries who did it.
CREATE OR REPLACE FUNCTION assistant.google_desconectar(p_org_id text, p_provider text, p_actor_id text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = assistant, public
AS $$
DECLARE v_deleted integer;
BEGIN
    PERFORM set_config('assistant.google_actor', coalesce(p_actor_id, ''), true);
    DELETE FROM assistant.oauth_credentials WHERE org_id = p_org_id AND provider = p_provider;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted > 0;
END;
$$;
REVOKE ALL ON FUNCTION assistant.google_desconectar(text, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assistant.google_desconectar(text, text, text) TO service_role;
