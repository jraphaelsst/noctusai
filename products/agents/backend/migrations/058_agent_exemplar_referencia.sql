-- ============================================================================
-- 058_agent_exemplar_referencia.sql -- the complete-agent recipe (agent-creation guide):
--
-- 1. agents.agents.exemplar -- a platform definition the AI generator may imitate. Until now the flag was the
--    `papel='exemplar'` role, which made "exemplar" and "generator" mutually exclusive roles of ONE column and
--    forced every exemplar to be set by hand at creation. It is its own boolean now (platform admin toggles it:
--    `PUT /api/studio/plataforma/agentes/{key}/exemplar`); `papel` keeps ONE value, 'gerador'. Existing exemplar
--    rows are backfilled (exemplar = true, papel = NULL) so no definition loses its role.
--
-- 2. agents.geracoes.referencia -- the exemplar a generation run imitates (`referencia` on the create request);
--    NULL = every exemplar, as before. A key, not an id: the run resolves it when it executes and fails visibly
--    (`referencia_indisponivel`) if it stopped being an exemplar in between.
--
-- 3. agents.geracao_areas.area admits 'evals' (the generator now drafts behaviour eval cases).
--
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. exemplar ──────────────────────────────────────────────────────────────────

ALTER TABLE agents.agents
    ADD COLUMN IF NOT EXISTS exemplar BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE agents.agents
   SET exemplar = TRUE, papel = NULL
 WHERE papel = 'exemplar';

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_definicao_atributos_check;
ALTER TABLE agents.agents ADD CONSTRAINT agents_definicao_atributos_check
    CHECK (
        (escopo_qualificacao IS NULL OR escopo_qualificacao ~ '^[a-z0-9][a-z0-9_-]{0,62}$')
        AND (padrao_qualificacao IS NULL OR padrao_qualificacao ~ '^[a-z0-9][a-z0-9_-]{0,62}$')
        AND (rascunho_padrao IS NULL OR jsonb_typeof(rascunho_padrao) = 'object')
        AND (papel IS NULL OR papel = 'gerador')
        AND (definition_scope = 'plataforma'
             OR (escopo_qualificacao IS NULL AND padrao_qualificacao IS NULL AND rascunho_padrao IS NULL
                 AND papel IS NULL AND NOT exemplar))
    );

-- ── 2. the reference of a run ─────────────────────────────────────────────────────

ALTER TABLE agents.geracoes
    ADD COLUMN IF NOT EXISTS referencia TEXT NULL;

ALTER TABLE agents.geracoes DROP CONSTRAINT IF EXISTS geracoes_referencia_check;
ALTER TABLE agents.geracoes ADD CONSTRAINT geracoes_referencia_check
    CHECK (referencia IS NULL OR referencia ~ '^[a-z0-9][a-z0-9-]{1,62}$');

-- ── 3. the evals area ─────────────────────────────────────────────────────────────

DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.geracao_areas'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%secoes%'
    LOOP
        EXECUTE format('ALTER TABLE agents.geracao_areas DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.geracao_areas
    ADD CONSTRAINT geracao_areas_area_check
        CHECK (area IN ('secoes', 'textos', 'ferramentas', 'decisoes', 'specs', 'skills', 'configuracoes', 'evals'));
