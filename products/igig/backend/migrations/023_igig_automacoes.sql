-- ============================================================================
-- IgIg — Automações v1: one execution per stage ENTRY (roadmap R11, slice E2)
--
-- 018 created `automacao` + `automacao_execucao`. What it could not express is
-- WHICH entry of a card into a stage an execution belongs to. Without that key
-- the engine cannot tell:
--   * a within-column reorder (same stage — must NOT re-fire) from a real entry,
--   * a card that left and came back (a NEW entry — must fire again),
--   * an SLA breach already alerted for this entry (the 15-min sweep must not
--     re-notify every tick).
--
-- The key is the `pipeline_movimentos` row that recorded the entry — the seed
-- `move_card` writes one per real stage change and `registrar_entrada` one per
-- card creation, so every entry has exactly one. `movimento_id` is NULL only
-- for legacy cards that predate 017's history (no entry row to key on).
--
-- `executando` is the CLAIM state: the engine inserts the row BEFORE running
-- the action, and the unique index below makes a concurrent second claim of
-- the same (automação, entry) fail instead of running the action twice (a
-- move racing the SLA sweep, a retried request).
--
-- `acao` shape (contract `cardhub-igig-crm-2026-09.wave-2-contract.md` §E2):
--   {tipo: criar_checklist | definir_responsavel | criar_tarefa | notificar |
--          enviar_email | enviar_whatsapp, params: {...}}
-- (018's column comment predates the contract and named other tipos.)
--
-- SQLite mirror: migrations/sqlite/023_automacoes.sql (index) — the column and
-- the widened CHECK are declared in the 018 mirror, per the mirror convention
-- (SQLite has no ADD COLUMN IF NOT EXISTS / ALTER CONSTRAINT).
-- ============================================================================
SET search_path = igig, public;

ALTER TABLE igig.automacao_execucao ADD COLUMN IF NOT EXISTS movimento_id UUID
    REFERENCES igig.pipeline_movimentos (id) ON DELETE SET NULL;

ALTER TABLE igig.automacao_execucao DROP CONSTRAINT IF EXISTS automacao_execucao_status_check;
ALTER TABLE igig.automacao_execucao ADD CONSTRAINT automacao_execucao_status_check
    CHECK (status IN ('executando', 'sucesso', 'erro', 'ignorada'));

-- One execution per (automação, entry). A second claim raises 23505, which the
-- engine reads as "already handled" — never as a failure.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_automacao_execucao_entrada
    ON igig.automacao_execucao (automacao_id, entidade_id, movimento_id)
    WHERE movimento_id IS NOT NULL;

-- The execuções log reads newest-first per org.
CREATE INDEX IF NOT EXISTS idx_igig_automacao_execucao_org
    ON igig.automacao_execucao (org_id, executado_em DESC);

COMMENT ON COLUMN igig.automacao.acao IS
    '{tipo: criar_checklist|definir_responsavel|criar_tarefa|notificar|enviar_email|enviar_whatsapp, params: {...}}';

NOTIFY pgrst, 'reload schema';
