-- ============================================================================
-- 079_emergencia_inatividade.sql -- an emergency stays open and closes by inactivity.
--
--   * `agents.thread_participantes.fecha_inativo_min`: the participant's inactivity window in minutes (NULL = no
--     window, the agent never closes by silence). The deadline is NOT stored: it is
--     `conversations.last_message_at + window`, so every message (lead, agent, human) refreshes it by construction.
--     Only the emergency alert sets it today (NOC-REMEDIATE[inatividade-por-agente] in the code: a per-agent window).
--   * partial index for the per-minute scheduler job (`list_inativos_vencidos`): only windowed ACTIVE rows.
--   * `agents.thread_alertas.tipo` gains 'emergencia' (the alert row is the recorded emergency marking).
--
-- Forward-only + idempotent; old code ignores the new column and never writes the new tipo (N-1 safe).
-- Deploy order: apply this migration, THEN the new image.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.thread_participantes
    ADD COLUMN IF NOT EXISTS fecha_inativo_min SMALLINT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'agents.thread_participantes'::regclass AND conname = 'ck_thread_participantes_fecha_inativo_min'
    ) THEN
        ALTER TABLE agents.thread_participantes
            ADD CONSTRAINT ck_thread_participantes_fecha_inativo_min
            CHECK (fecha_inativo_min IS NULL OR fecha_inativo_min BETWEEN 1 AND 1440);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agents_thread_participantes_inatividade
    ON agents.thread_participantes (estado, fecha_inativo_min)
    WHERE estado = 'ativo' AND fecha_inativo_min IS NOT NULL;

ALTER TABLE agents.thread_alertas DROP CONSTRAINT IF EXISTS thread_alertas_tipo_check;
ALTER TABLE agents.thread_alertas
    ADD CONSTRAINT thread_alertas_tipo_check
    CHECK (tipo IN ('lead_insatisfeito', 'erro_agente', 'desvio', 'outro', 'emergencia'));
