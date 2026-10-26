-- ============================================================================
-- 050 · Org/app configuration is reachable only by orgs EXPLICITLY granted it.
--
-- The leak (2026-10-26): a platform definition with instanciavel=TRUE (the 049 DEFAULT, and the
-- store default) is instantiated in EVERY org (plataforma.ensure_instancias), so one org's / one
-- app's agent (julia -> social-wiring; monica-leads -> monica) reached every other org. "Default
-- open" is the root; this makes the default CLOSED and the exception an explicit, audited row.
--
--   1. instanciavel DEFAULT FALSE.
--   2. agents.definition_org_grants(definition_id, org_id, ...) -- the allow-list of orgs that may
--      hold an INSTANCE of a non-instanciavel definition. Service-role only (RLS on, no policy).
--   3. Backfill, KEYING-AGNOSTIC: an instance row points at its definition by definition_agent_id
--      (not by key), so every org that ALREADY holds an instance of a definition that is (or is
--      about to become) closed gets a grant BEFORE anything is flipped -- nothing breaks.
--   4. Every product-owned definition (owner_product IS NOT NULL) becomes instanciavel=false, and a
--      CHECK keeps it so (product-owned config is never fleet-wide).
--   5. guard_agent_definition_scope refuses an INSTANCE of a non-instanciavel definition for an org
--      without a grant: definition_not_granted (the DB is the backstop; app code consults grants).
--
-- Forward-only + idempotent. NOT applied by the repo -- tech-lead applies via noctus.dev.migrate_product.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. closed by default ────────────────────────────────────────────────────

ALTER TABLE agents.agents ALTER COLUMN instanciavel SET DEFAULT FALSE;

-- ── 2. the allow-list ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.definition_org_grants (
    definition_id UUID NOT NULL REFERENCES agents.agents (id) ON DELETE CASCADE,
    org_id        UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    granted_by    UUID NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (definition_id, org_id)
);
CREATE INDEX IF NOT EXISTS idx_definition_org_grants_org ON agents.definition_org_grants (org_id);

ALTER TABLE agents.definition_org_grants ENABLE ROW LEVEL SECURITY;
-- Service-role only (the 036 posture): no policy for anon/authenticated, and no table privilege either.
REVOKE ALL ON agents.definition_org_grants FROM PUBLIC, anon, authenticated;
GRANT ALL ON agents.definition_org_grants TO service_role;

-- ── 3. backfill grants (before any flip) ────────────────────────────────────

INSERT INTO agents.definition_org_grants (definition_id, org_id)
SELECT DISTINCT i.definition_agent_id, i.org_id
FROM agents.agents i
JOIN agents.agents d ON d.id = i.definition_agent_id AND d.definition_scope = 'plataforma'
WHERE i.definition_scope = 'instancia'
  AND (d.owner_product IS NOT NULL OR NOT d.instanciavel)
ON CONFLICT DO NOTHING;

-- ── 4. product-owned definitions are never fleet-wide ───────────────────────

UPDATE agents.agents
   SET instanciavel = FALSE
 WHERE definition_scope = 'plataforma' AND owner_product IS NOT NULL AND instanciavel;

ALTER TABLE agents.agents DROP CONSTRAINT IF EXISTS agents_product_owned_not_instanciavel;
ALTER TABLE agents.agents ADD CONSTRAINT agents_product_owned_not_instanciavel
    CHECK (definition_scope <> 'plataforma' OR NOT (instanciavel AND owner_product IS NOT NULL));

-- ── 5. the guard learns grants ──────────────────────────────────────────────

CREATE OR REPLACE FUNCTION agents.guard_agent_definition_scope()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = agents, public
AS $$
DECLARE
    v_def agents.agents;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.definition_scope IS DISTINCT FROM OLD.definition_scope
           OR NEW.definition_agent_id IS DISTINCT FROM OLD.definition_agent_id
           OR (OLD.conteudo_modo = 'linhas' AND NEW.conteudo_modo <> 'linhas') THEN
            RAISE EXCEPTION 'scope_immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.definition_scope = 'plataforma' THEN
        PERFORM 1 FROM public.organizations o WHERE o.id = NEW.org_id AND o.is_platform;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'definition_not_platform' USING ERRCODE = 'P0001';
        END IF;
    ELSIF NEW.definition_scope = 'instancia' THEN
        SELECT * INTO v_def FROM agents.agents WHERE id = NEW.definition_agent_id;
        IF NOT FOUND OR v_def.definition_scope <> 'plataforma' OR v_def.key <> NEW.key THEN
            RAISE EXCEPTION 'definition_invalid' USING ERRCODE = 'P0001';
        END IF;
        -- A closed definition is held only by orgs it was explicitly granted to.
        IF NOT v_def.instanciavel THEN
            PERFORM 1 FROM agents.definition_org_grants g
             WHERE g.definition_id = v_def.id AND g.org_id = NEW.org_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'definition_not_granted' USING ERRCODE = 'P0001';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION agents.guard_agent_definition_scope() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.guard_agent_definition_scope() TO service_role;
