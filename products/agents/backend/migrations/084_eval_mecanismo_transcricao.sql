-- ============================================================================
-- 084_eval_mecanismo_transcricao.sql -- the mechanism eval keeps WHAT the agent said and called.
--
-- eval_mecanismo_execucoes (038) stored only tool NAMES, so a failing case (e.g. zero tool calls over 2 turns) was
-- undiagnosable. Adds one nullable jsonb column written in the same insert as the rest of the (append-only) result:
--   transcricao  [{"lead"|"retomada": ..., "bolhas": [str], "ferramentas": [{"nome","args","ok"}]}, ...] per turn;
--                on status 'erro' it holds the turns completed before the failing one.
-- Synthetic fixtures only (eval_pii refuses real data when a case is stored).
--
-- Access tier unchanged: the table is Platform IP (tier:platform), RLS on, service role only (038).
-- Backward compatible with the previous image: N-1 never reads or writes the column (nullable, no default needed).
-- Forward-only + idempotent (applies twice on the replay).
-- ============================================================================

SET search_path = agents, public;

SET LOCAL lock_timeout = '5s';

ALTER TABLE agents.eval_mecanismo_execucoes ADD COLUMN IF NOT EXISTS transcricao JSONB NULL;

COMMENT ON TABLE agents.eval_mecanismo_execucoes IS 'tier:platform';
COMMENT ON COLUMN agents.eval_mecanismo_execucoes.transcricao IS
    'per turn: lead|retomada, bolhas, ferramentas[{nome,args,ok}]; partial on status erro; synthetic fixtures only';
