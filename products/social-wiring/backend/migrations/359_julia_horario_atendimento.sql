-- ============================================================================
-- 359_julia_horario_atendimento.sql -- Julia business hours per org + the portal opener's own text
-- ============================================================================
-- Owner request 2026-11-18: the window Julia may start/continue automatic outbound (re-engagement hours tier, regua attempts,
-- the portal first contact) was a fixed 08:00-19:59 America/Sao_Paulo in code. It is now a per-org setting on the existing
-- `julia_reengajamento_config` row, and the portal first contact gets its own optional text.
--
--   horario_abertura / horario_fechamento  time   opening < closing (same day: a window crossing midnight is refused).
--                                                 Closing is exclusive (20:00 = already outside), the old behaviour.
--   dias_atendimento                       int[]  ISO weekdays served (1 = Monday .. 7 = Sunday), 1..7 entries.
--   portal_primeiro_contato_texto          text   optional opener for a portal lead; NULL = the org's `mensagem_inicial`.
--                                                 When set it MUST carry `{link}` (the LGPD privacy notice is not optional).
--
-- Defaults reproduce today's behaviour exactly (08:00-20:00, every day, no custom text): nothing changes until an admin edits.
-- FORWARD-ONLY, IDEMPOTENT. No SECURITY DEFINER; RLS of the table is untouched. Config changes are recorded as the existing
-- append-only `configuracao_alterada` Julia event (no new table).
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.julia_reengajamento_config
    ADD COLUMN IF NOT EXISTS horario_abertura time NOT NULL DEFAULT '08:00',
    ADD COLUMN IF NOT EXISTS horario_fechamento time NOT NULL DEFAULT '20:00',
    ADD COLUMN IF NOT EXISTS dias_atendimento smallint[] NOT NULL DEFAULT ARRAY[1,2,3,4,5,6,7]::smallint[],
    ADD COLUMN IF NOT EXISTS portal_primeiro_contato_texto text;

ALTER TABLE social_wiring.julia_reengajamento_config DROP CONSTRAINT IF EXISTS julia_reeng_horario_valido;
ALTER TABLE social_wiring.julia_reengajamento_config
    ADD CONSTRAINT julia_reeng_horario_valido CHECK (horario_abertura < horario_fechamento);

ALTER TABLE social_wiring.julia_reengajamento_config DROP CONSTRAINT IF EXISTS julia_reeng_dias_validos;
ALTER TABLE social_wiring.julia_reengajamento_config
    ADD CONSTRAINT julia_reeng_dias_validos CHECK (
        cardinality(dias_atendimento) BETWEEN 1 AND 7 AND dias_atendimento <@ ARRAY[1,2,3,4,5,6,7]::smallint[]
    );

ALTER TABLE social_wiring.julia_reengajamento_config DROP CONSTRAINT IF EXISTS julia_reeng_portal_texto_valido;
ALTER TABLE social_wiring.julia_reengajamento_config
    ADD CONSTRAINT julia_reeng_portal_texto_valido CHECK (
        portal_primeiro_contato_texto IS NULL
        OR (position('{link}' in portal_primeiro_contato_texto) > 0 AND char_length(portal_primeiro_contato_texto) <= 1024)
    );

COMMENT ON COLUMN social_wiring.julia_reengajamento_config.horario_abertura IS
    'Migration 359: Julia''s daily opening (America/Sao_Paulo). Must be before horario_fechamento.';
COMMENT ON COLUMN social_wiring.julia_reengajamento_config.horario_fechamento IS
    'Migration 359: Julia''s daily closing, exclusive (America/Sao_Paulo).';
COMMENT ON COLUMN social_wiring.julia_reengajamento_config.dias_atendimento IS
    'Migration 359: ISO weekdays (1=Mon..7=Sun) Julia works. At least one.';
COMMENT ON COLUMN social_wiring.julia_reengajamento_config.portal_primeiro_contato_texto IS
    'Migration 359: optional opener text for portal leads (must carry {link}); NULL = the org mensagem_inicial.';
