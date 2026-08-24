-- ============================================================================
-- Migration 072 -- social_wiring: make a stuck extraction recoverable
--
-- THE HOLE 068 LEFT
-- -----------------
-- Extraction runs in a FastAPI BackgroundTask, detached from the request that
-- uploaded the document. `extracao_status` moves to 'processando' before the
-- work starts and to 'ok'/'sem_dados'/'erro' after it. If the process dies in
-- between — a deploy, an OOM kill, the container restarting — nothing ever
-- moves it again. The document sits in 'processando' forever, the checklist
-- item never ticks, and NOTHING SURFACES: no error, no log line, no retry.
-- The same is true of 'pendente', which is stamped at insert time and would
-- never advance if the task was never scheduled at all.
--
-- 068's own comment called a retry sweep "possible later". This is later.
--
-- 🔴 WHY AN ATTEMPT COUNTER, NOT JUST A SWEEP
-- -------------------------------------------
-- A sweep with no bound is an unbounded bill. The second rung of the ladder
-- rasterizes pages and calls a vision model; a document that fails
-- deterministically (corrupt bytes, a password-protected PDF, an object
-- deleted from storage) would be retried on every pass, forever, paying for a
-- vision call each time and never succeeding. The counter is what turns
-- "retry until it works" into "retry until we have evidence it will not".
--
-- Exhausted rows land on 'erro' with the reason recorded, which is a state a
-- human can see and act on — the opposite of the silent 'processando' this
-- migration exists to end.
-- ============================================================================

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_tentativas INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_tentativas IS
    'How many times extraction has been STARTED for this document, including '
    'the first. Bounded by identidade_extracao_service.MAX_TENTATIVAS; once '
    'reached the sweep stops retrying and records a terminal error rather than '
    'paying for another vision call.';

-- Rows that already carry a finished extraction have been attempted once;
-- saying 0 would tell the sweep they were never tried. Rows still sitting in
-- 'pendente'/'processando' from before this migration are left at 0 on
-- purpose — they get their full retry budget, which is exactly the recovery
-- this migration is for.
UPDATE social_wiring.cliente_documentos
   SET extracao_tentativas = 1
 WHERE extracao_status IN ('ok', 'sem_dados', 'erro')
   AND extracao_tentativas = 0;

-- The sweep's own lookup: find documents stalled in a non-terminal state.
-- Partial, because the overwhelming majority of rows are terminal or have no
-- extraction at all, and this index must stay small enough to be free.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_extracao_pendente
    ON social_wiring.cliente_documentos (extracao_em NULLS FIRST)
    WHERE deleted_at IS NULL
      AND extracao_status IN ('pendente', 'processando');
