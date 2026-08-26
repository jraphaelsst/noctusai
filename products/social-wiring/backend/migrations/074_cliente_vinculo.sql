-- ============================================================================
-- Migration 074 · social_wiring: who introduced this person
--
-- WHY
-- ---
-- Migration 073 made a comprador a real `clientes` row, which is what lets the
-- checklist, the uploads and the extraction cover them with no new code. It
-- has one consequence nobody wants: a spouse created through "Adicionar
-- Comprador" is, as far as `clientes` is concerned, indistinguishable from a
-- lead who walked in off the street. She has no channel, no key, no touches
-- and no campaign — she is a person the database cannot explain.
--
-- `atendimento_partes` does explain her, but only for as long as the
-- atendimento exists: that table cascades on atendimento delete, and when it
-- goes she is left with no relationship to anything at all.
--
-- So the fact is recorded on the PERSON, where it survives the deal.
--
-- 🔴 ON DELETE SET NULL, NEVER CASCADE
-- ------------------------------------
-- Deleting Luciano must not delete his wife. She is a data subject in her own
-- right, with her own uploaded documents under their own retention clock
-- (`cliente_documento_tipos.retencao_dias`), and "the buyer's record was
-- removed" is not consent to erase hers. Losing the link is the correct
-- degradation; losing the person is not.
--
-- 🔴 THIS IS NOT A MERGE KEY, AND MUST NOT BECOME ONE
-- ---------------------------------------------------
-- `identidade_service`'s review groups already decide when two rows are the
-- SAME person. This column says two DIFFERENT people are related. Feeding it
-- into dedup would merge a married couple into one record — the exact opposite
-- of what the contract needs, which is both of them, separately, in full.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — apply via the documented path after the tech-lead
-- has stated the row counts and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS vinculado_a_cliente_id UUID
        REFERENCES social_wiring.clientes(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS vinculo_origem         TEXT,
    ADD COLUMN IF NOT EXISTS vinculado_em           TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.vinculado_a_cliente_id IS
    'The cliente who brought this person into the system — the titular of the '
    'atendimento they were first added to. FIRST-WRITER-WINS: never '
    'overwritten, so a person keeps their original introducer even if they '
    'later join other deals. NOT a dedup/merge key: it asserts two DIFFERENT '
    'people are related, never that they are the same one.';

COMMENT ON COLUMN social_wiring.clientes.vinculo_origem IS
    'How the link was made — ''comprador_atendimento'' today. TEXT rather than '
    'a CHECK so a new relationship path needs no migration.';

-- Answers "who did this person bring in?" — the direction the card reads when
-- it renders a titular's parties, and the one a data-subject request needs
-- when asked what else is attached to someone.
CREATE INDEX IF NOT EXISTS idx_sw_clientes_vinculado_a
    ON social_wiring.clientes (org_id, vinculado_a_cliente_id)
    WHERE vinculado_a_cliente_id IS NOT NULL;

-- A person cannot introduce themselves. Cheap to state, and it forecloses the
-- self-referential row that would make any recursive walk of this column hang.
ALTER TABLE social_wiring.clientes
    DROP CONSTRAINT IF EXISTS clientes_vinculo_nao_e_proprio;
ALTER TABLE social_wiring.clientes
    ADD CONSTRAINT clientes_vinculo_nao_e_proprio
    CHECK (vinculado_a_cliente_id IS NULL OR vinculado_a_cliente_id <> id);
