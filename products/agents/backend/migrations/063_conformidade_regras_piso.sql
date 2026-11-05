-- ============================================================================
-- 063_conformidade_regras_piso.sql -- Julia go-live hardening (H4): every agent INSTANCE has its security-rule rows.
--
-- Migration 044 seeded `padroes_proibidos` / `alegacao_identidade` ONCE, for the instances that existed then. An
-- instance created later (`ensure_instancia`, the grant flow) got none -- prod's `conformidade_regras` was EMPTY -- so the
-- detectors ran with zero patterns.
--
-- The patterns themselves are now a CODE-SIDE FLOOR (`app.stores.conformidade.PADROES_PROIBIDOS_PISO` /
-- `PADROES_ALEGACAO_PISO`, merged UNDER whatever a row holds: the DB can add, never remove). So this migration seeds only
-- the ROW (`parametros.padroes` = the instance's OWN additions, empty to start) -- no pattern text is duplicated here, so
-- the two cannot drift. Readiness (`regras_seguranca_sem_parametros`) is blocking while an instance lacks the rows.
--
-- 1. backfill: every instance missing a row gets it (existing rows are never touched);
-- 2. trigger: a NEW instance gets them in the same transaction as its INSERT.
-- Idempotent (ON CONFLICT DO NOTHING / CREATE OR REPLACE / DROP TRIGGER IF EXISTS); runs twice.
-- ============================================================================

SET search_path = agents, public;

INSERT INTO agents.conformidade_regras (org_id, agent_id, regra, ativo, politica, parametros)
SELECT a.org_id, a.id, r.regra, true, r.politica, '{"padroes": []}'::jsonb
FROM agents.agents a
CROSS JOIN (VALUES
    ('padroes_proibidos',   'bloquear'),
    ('alegacao_identidade', 'registrar')
) AS r(regra, politica)
WHERE a.definition_scope = 'instancia'
ON CONFLICT (agent_id, regra) DO NOTHING;

CREATE OR REPLACE FUNCTION agents.seed_conformidade_regras_instancia()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO agents.conformidade_regras (org_id, agent_id, regra, ativo, politica, parametros)
    VALUES
        (NEW.org_id, NEW.id, 'padroes_proibidos',   true, 'bloquear',  '{"padroes": []}'::jsonb),
        (NEW.org_id, NEW.id, 'alegacao_identidade', true, 'registrar', '{"padroes": []}'::jsonb)
    ON CONFLICT (agent_id, regra) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS seed_conformidade_regras_instancia ON agents.agents;
CREATE TRIGGER seed_conformidade_regras_instancia
    AFTER INSERT ON agents.agents
    FOR EACH ROW
    WHEN (NEW.definition_scope = 'instancia')
    EXECUTE FUNCTION agents.seed_conformidade_regras_instancia();
