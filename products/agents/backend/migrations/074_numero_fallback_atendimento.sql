-- ============================================================================
-- 074_numero_fallback_atendimento.sql -- the FALLBACK NUMBER for agent hand-offs (roadmap agent-templates-2026-11,
-- owner 2026-11-09).
--
-- When an agent hands a conversation to a human, the team is notified at this number. For now ONE number serves
-- every organization (owner: "same fallback number for all orgs, we're gonna change that in the future"), so it is
-- a platform runtime setting, edited on the platform-admin page "Configurações do agente". Readiness refuses to
-- publish a conversational agent while it is unset (409 numero_fallback_ausente).
--
-- 1. agents.runtime_settings accepts the key 'numero_fallback_atendimento'.
-- 2. Its value must be an E.164 string (+, country code, national number): the app normalizes with
--    noctusai_lib.primitives.phone.normalize_phone; this CHECK is the backstop.
--
-- No row is inserted: the owner types the number. Forward-only + idempotent.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.runtime_settings DROP CONSTRAINT IF EXISTS runtime_settings_key_check;
ALTER TABLE agents.runtime_settings ADD CONSTRAINT runtime_settings_key_check
    CHECK (key IN ('approval_timeout_seconds', 'max_turns', 'messages_rate_limit', 'numero_fallback_atendimento'));

ALTER TABLE agents.runtime_settings DROP CONSTRAINT IF EXISTS runtime_settings_numero_fallback_e164;
ALTER TABLE agents.runtime_settings ADD CONSTRAINT runtime_settings_numero_fallback_e164
    CHECK (key <> 'numero_fallback_atendimento'
           OR (jsonb_typeof(value) = 'string' AND (value #>> '{}') ~ '^\+[1-9][0-9]{7,14}$'));
