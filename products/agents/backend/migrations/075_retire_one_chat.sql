-- ============================================================================
-- 075_retire_one_chat.sql -- the "One Chat" operator bot is retired (owner decision 2026-11-04, reconfirmed
-- 2026-11-10): Julia IS the WhatsApp line. This removes what 006 / 040 seeded for it, per org and platform-wide.
--
--   1. agents.catalogo_capacidades / agents.catalogo_agentes -- the display rows 040 inserted for 'one-chat'.
--   2. agents.agents -- the per-org control row (key 'one-chat', runtime 'external') that
--      `AgentStore.ensure_default_agents` used to re-create on every request (no longer seeded). Deleted when
--      nothing references it; a row that still owns history (an FK says so) is ARCHIVED instead -- same
--      shape 053 gives a retired code-defined agent (definition_mode 'arquivado', key freed) -- never failed.
--   3. agents.app_integration_config -- the stored SOCIAL_WIRING_API_TOKEN (the One Chat bridge credential,
--      010); its spec left the credential registry. (Revoking the matching social-wiring api_tokens row is a
--      data step on that product, not here.)
--
-- Forward-only and idempotent: a second run finds nothing left. Applied migrations 006/031/040 are untouched.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. catalogue display rows (children first) ──────────────────────────────
DELETE FROM agents.catalogo_capacidades WHERE agent_key = 'one-chat';
DELETE FROM agents.catalogo_agentes WHERE agent_key = 'one-chat';

-- ── 2. the control-plane rows ───────────────────────────────────────────────
DO $$
DECLARE
    v_row agents.agents;
BEGIN
    FOR v_row IN
        SELECT * FROM agents.agents WHERE key = 'one-chat' AND definition_mode = 'legacy'
    LOOP
        BEGIN
            DELETE FROM agents.agents WHERE id = v_row.id;
        EXCEPTION WHEN foreign_key_violation THEN
            UPDATE agents.agents
               SET definition_mode = 'arquivado', ativo = false,
                   key = v_row.key || '-arquivado-' || left(v_row.id::text, 8)
             WHERE id = v_row.id;
        END;
    END LOOP;
END
$$;

-- ── 3. the retired bridge credential ────────────────────────────────────────
DELETE FROM agents.app_integration_config WHERE key = 'social_wiring_api_token';
