-- ============================================================================
-- 219 — "visita aconteceu?": structured feedback on visitas + roteiros
-- ============================================================================
-- CONTRACT sw-lead-to-contract §3.1. Four additive columns, no new table (RLS
-- and the acting-audit triggers on `roteiros` / `visitas` are unchanged).
--
--   visitas.nao_realizada_motivo  why a visit did not happen (closed enum, so
--                                 the funnel metric can group by it)
--   visitas.realizada_em          when status became 'realizada'
--   roteiros.feedback_status      'pendente' until the corretor answers the
--                                 roteiro-level "visita aconteceu?"
--   roteiros.feedback_em          when it was answered
--   roteiros.hora_visita          optional time of day; data_visita stays DATE
--
-- Forward-only, idempotent. `feedback_status` defaults to 'pendente' for every
-- existing roteiro on purpose: legacy roteiros whose visitas were already
-- marked by hand are NOT silently flipped to 'respondido' here; the prompt
-- only fires for roteiros with a data_visita in the past, and answering it is
-- one click.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.visitas
    ADD COLUMN IF NOT EXISTS nao_realizada_motivo TEXT,
    ADD COLUMN IF NOT EXISTS realizada_em TIMESTAMPTZ;

ALTER TABLE social_wiring.visitas
    DROP CONSTRAINT IF EXISTS visitas_nao_realizada_motivo_valido;
ALTER TABLE social_wiring.visitas
    ADD CONSTRAINT visitas_nao_realizada_motivo_valido
    CHECK (
        nao_realizada_motivo IS NULL
        OR nao_realizada_motivo IN (
            'cliente_desistiu', 'cliente_nao_compareceu',
            'imovel_indisponivel', 'reagendada', 'outro'
        )
    );

ALTER TABLE social_wiring.roteiros
    ADD COLUMN IF NOT EXISTS feedback_status TEXT NOT NULL DEFAULT 'pendente',
    ADD COLUMN IF NOT EXISTS feedback_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS hora_visita TIME;

ALTER TABLE social_wiring.roteiros
    DROP CONSTRAINT IF EXISTS roteiros_feedback_status_valido;
ALTER TABLE social_wiring.roteiros
    ADD CONSTRAINT roteiros_feedback_status_valido
    CHECK (feedback_status IN ('pendente', 'respondido'));

COMMENT ON COLUMN social_wiring.visitas.nao_realizada_motivo IS
    'Why a visit did not happen. Closed enum; set only with status=nao_realizada. Migration 219.';
COMMENT ON COLUMN social_wiring.visitas.realizada_em IS
    'When status became realizada. Migration 219.';
COMMENT ON COLUMN social_wiring.roteiros.feedback_status IS
    'pendente until the corretor answers "visita aconteceu?" for the roteiro. Migration 219.';
COMMENT ON COLUMN social_wiring.roteiros.feedback_em IS
    'When the roteiro-level feedback was answered. Migration 219.';
COMMENT ON COLUMN social_wiring.roteiros.hora_visita IS
    'Optional time of the visit; data_visita stays the DATE. Migration 219.';

-- The daily prompt job and GET /api/roteiros/pendentes-feedback scan exactly
-- these rows.
CREATE INDEX IF NOT EXISTS idx_sw_roteiros_feedback_pendente
    ON social_wiring.roteiros (org_id, data_visita)
    WHERE deleted_at IS NULL AND feedback_status = 'pendente'
      AND data_visita IS NOT NULL;

NOTIFY pgrst, 'reload schema';
