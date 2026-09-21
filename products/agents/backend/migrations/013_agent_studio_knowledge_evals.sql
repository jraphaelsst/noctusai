-- ============================================================================
-- 013_agent_studio_knowledge_evals.sql — Agent Studio: knowledge library +
-- eval gate (CONTRACT §B2, slice BE-KE).
--
-- Tables: knowledge_collections, knowledge_documents, knowledge_revisions,
-- eval_cases, eval_runs, eval_results. Every table carries the common
-- columns (id, org_id, created_at, updated_at), RLS enabled with an
-- org-scoped SELECT policy via `current_org_id()` plus the literal
-- "service_role_bypass" policy (`check_admin_endpoint_service_role_bypass`
-- keeper — KB § PATTERNS/backend/database-rls.md), `idx_agents_<table>_org`,
-- and the `agents.set_updated_at()` trigger declared in 006_agents.sql —
-- same conventions as every other table in this schema (contract §B intro).
--
-- Knowledge + evals are AGENT-scoped, not version-scoped (contract §B2):
-- the corpus evolves on its own clock independent of prompt/skill versions,
-- and `knowledge_revisions` is its own append-only history — never frozen
-- by the `agent_versions` immutability triggers 012 declares.
--
-- ORDERING: this migration assumes 012_agent_studio_definitions.sql already
-- ran — `eval_runs.version_id` FKs to `agents.agent_versions(id)` (created
-- by 012) and the trailing ALTER on `agents.agent_versions` adds the
-- `agent_versions_eval_run_fk` FK 012 reserved (`eval_run_id uuid null`,
-- FK added here per contract §B2). Numbered order enforces this — 013 can
-- never run before 012 against a real database.
--
-- ANON LOCKDOWN: `011_anon_grant_lockdown.sql` set
-- `ALTER DEFAULT PRIVILEGES IN SCHEMA agents REVOKE ALL ON TABLES FROM anon`
-- — a schema-level default that already covers every table created after
-- it, including the six below. No additional REVOKE/GRANT needed for
-- `anon` here; `authenticated` keeps its schema-default ALL grant from
-- 001_agents.sql but RLS (SELECT-only policy, no INSERT/UPDATE/DELETE
-- policy for `authenticated`) blocks writes by omission — identical shape
-- to every table in 006_agents.sql.
--
-- SECURITY DEFINER EXECUTE LOCKDOWN (mirrors 006's H1 finding): the one
-- SECURITY DEFINER function this file declares (`agents.search_knowledge`)
-- is immediately followed by a `REVOKE ALL ... FROM PUBLIC, anon,
-- authenticated` + `GRANT EXECUTE ... TO service_role` pair —
-- `tests/stores/test_migration_013_shape.py`'s
-- `TestSecurityDefinerExecuteGrants` enforces this generically.
-- ============================================================================

SET search_path = agents, public;

-- pg_trgm powers the trigram GIN index on `knowledge_documents.titulo`
-- (fuzzy/substring title search, contract §B2 "pg_trgm GIN on titulo").
-- Pre-installed on Supabase-managed Postgres; installed into the
-- `extensions` schema per platform convention (see
-- `products/erp-imobiliario/backend/migrations/002_ai_matching.sql`'s
-- `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;`).
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;


-- ────────────────────────────────────────────────────────────────────────
-- knowledge_collections
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.knowledge_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    nome TEXT NOT NULL,
    tag TEXT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    ordem INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, slug)
);

ALTER TABLE agents.knowledge_collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "knowledge_collections_select_own_org" ON agents.knowledge_collections
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.knowledge_collections
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_knowledge_collections_org ON agents.knowledge_collections(org_id);
CREATE INDEX idx_agents_knowledge_collections_agent ON agents.knowledge_collections(agent_id);

CREATE OR REPLACE TRIGGER set_updated_at_knowledge_collections
    BEFORE UPDATE ON agents.knowledge_collections
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- knowledge_documents — Postgres FTS v1 (contract §A9): `portuguese`
-- config, weighted title(A)/resumo(B)/conteudo(C) tsvector + trigram on
-- titulo. `source_sha` is the import-idempotency key (§F): unchanged
-- content on re-import upserts nothing and writes no revision.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    collection_id UUID NOT NULL REFERENCES agents.knowledge_collections(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    titulo TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('fonte', 'sintese', 'card', 'template', 'indice', 'outro')),
    proveniencia JSONB NOT NULL DEFAULT '{}',
    resumo TEXT NULL,
    conteudo TEXT NOT NULL,
    source_sha TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT true,
    busca tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('portuguese', coalesce(titulo, '')), 'A') ||
        setweight(to_tsvector('portuguese', coalesce(resumo, '')), 'B') ||
        setweight(to_tsvector('portuguese', left(coalesce(conteudo, ''), 900000)), 'C')
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, slug)
);

ALTER TABLE agents.knowledge_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "knowledge_documents_select_own_org" ON agents.knowledge_documents
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.knowledge_documents
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_knowledge_documents_org ON agents.knowledge_documents(org_id);
CREATE INDEX idx_agents_knowledge_documents_collection ON agents.knowledge_documents(collection_id);
CREATE INDEX idx_agents_knowledge_documents_busca ON agents.knowledge_documents USING GIN (busca);
CREATE INDEX idx_agents_knowledge_documents_titulo_trgm
    ON agents.knowledge_documents USING GIN (titulo extensions.gin_trgm_ops);

CREATE OR REPLACE TRIGGER set_updated_at_knowledge_documents
    BEFORE UPDATE ON agents.knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- knowledge_revisions — append-only audit log (contract §B2). Never
-- exposed for UPDATE/DELETE by the app layer; the `updated_at` column +
-- trigger are kept only for shape-convention parity with every other
-- table in this schema (a revision row's `updated_at` never moves in
-- practice, since the store only ever `.insert()`s here).
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.knowledge_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES agents.knowledge_documents(id) ON DELETE CASCADE,
    op TEXT NOT NULL CHECK (op IN ('create', 'update', 'archive', 'import')),
    snapshot JSONB NOT NULL,
    author_id UUID NULL,
    motivo TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.knowledge_revisions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "knowledge_revisions_select_own_org" ON agents.knowledge_revisions
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.knowledge_revisions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_knowledge_revisions_org ON agents.knowledge_revisions(org_id);
CREATE INDEX idx_agents_knowledge_revisions_document ON agents.knowledge_revisions(document_id, created_at);

CREATE OR REPLACE TRIGGER set_updated_at_knowledge_revisions
    BEFORE UPDATE ON agents.knowledge_revisions
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- eval_cases
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.eval_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    titulo TEXT NOT NULL,
    entrada TEXT NOT NULL,
    contexto TEXT NULL,
    -- {"deve": [str,...], "nao_deve": [str,...]} — at least one criterion
    -- total across both arrays (contract §B2).
    criterios JSONB NOT NULL CHECK (
        coalesce(jsonb_array_length(criterios -> 'deve'), 0) +
        coalesce(jsonb_array_length(criterios -> 'nao_deve'), 0) >= 1
    ),
    rubrica TEXT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, slug)
);

ALTER TABLE agents.eval_cases ENABLE ROW LEVEL SECURITY;

CREATE POLICY "eval_cases_select_own_org" ON agents.eval_cases
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.eval_cases
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_eval_cases_org ON agents.eval_cases(org_id);
CREATE INDEX idx_agents_eval_cases_agent ON agents.eval_cases(agent_id);

CREATE OR REPLACE TRIGGER set_updated_at_eval_cases
    BEFORE UPDATE ON agents.eval_cases
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- eval_runs — at most one `pendente`/`executando` run per version
-- (contract §B2 "one pendente|executando run per version").
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id),
    compiled_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pendente', 'executando', 'concluida', 'falhou', 'cancelada')),
    total INT NOT NULL DEFAULT 0,
    aprovados INT NOT NULL DEFAULT 0,
    score NUMERIC(4, 3) NULL,
    limiar NUMERIC(4, 3) NOT NULL,
    started_by UUID NOT NULL,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    erro TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.eval_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "eval_runs_select_own_org" ON agents.eval_runs
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.eval_runs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_eval_runs_org ON agents.eval_runs(org_id);
CREATE INDEX idx_agents_eval_runs_version ON agents.eval_runs(version_id, created_at);

-- Partial unique: a version can have at most one run in flight. The
-- store maps the resulting uniqueness-violation into a 409
-- `run_in_progress` at the router (contract §D4).
CREATE UNIQUE INDEX eval_runs_one_active_per_version_idx
    ON agents.eval_runs (version_id) WHERE status IN ('pendente', 'executando');

CREATE OR REPLACE TRIGGER set_updated_at_eval_runs
    BEFORE UPDATE ON agents.eval_runs
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- eval_results — one row per (run, case)
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    run_id UUID NOT NULL REFERENCES agents.eval_runs(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES agents.eval_cases(id),
    status TEXT NOT NULL CHECK (status IN ('pendente', 'aprovado', 'reprovado', 'erro')),
    saida TEXT NULL,
    score NUMERIC(4, 3) NULL,
    -- [{"criterio": str, "tipo": "deve"|"nao_deve", "ok": bool, "motivo": str}]
    veredito JSONB NULL,
    notas_juiz TEXT NULL,
    duracao_ms INT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, case_id)
);

ALTER TABLE agents.eval_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "eval_results_select_own_org" ON agents.eval_results
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON agents.eval_results
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_agents_eval_results_org ON agents.eval_results(org_id);
CREATE INDEX idx_agents_eval_results_run ON agents.eval_results(run_id);

CREATE OR REPLACE TRIGGER set_updated_at_eval_results
    BEFORE UPDATE ON agents.eval_results
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();


-- ────────────────────────────────────────────────────────────────────────
-- 012 reserved `agent_versions.eval_run_id` (the run that satisfied the
-- publish gate) without a FK, since `eval_runs` didn't exist yet at that
-- point in migration order. Add it now (contract §B2, closing line).
-- ────────────────────────────────────────────────────────────────────────

ALTER TABLE agents.agent_versions
    ADD CONSTRAINT agent_versions_eval_run_fk FOREIGN KEY (eval_run_id) REFERENCES agents.eval_runs(id);


-- ────────────────────────────────────────────────────────────────────────
-- agents.search_knowledge — the ONE ranked-search function; both the
-- `GET .../knowledge/search` route and (later, BE-RT) the `kb_buscar`
-- MCP tool call this — never two independent ranking implementations
-- (contract §D3 "the SAME function the `kb_buscar` tool calls").
--
-- `websearch_to_tsquery` (not `plainto_tsquery`) accepts the free-text
-- query shape a search box naturally produces (quoted phrases, `-word`
-- exclusion) without the caller pre-parsing it. `ts_headline` produces
-- the `trecho` (excerpt) directly from `resumo`/`conteudo` — cheap at
-- query time since it only runs over the LIMIT-ed row set, never over the
-- full corpus.
--
-- SECURITY DEFINER + locked search_path (queries `agents.knowledge_*`
-- regardless of caller role) — routes call it through the admin client
-- (defence in depth, same as every table in this schema; contract §B
-- intro "Routes use the admin client"). EXECUTE is locked to
-- service_role immediately below — see this file's header.
-- ────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION agents.search_knowledge(
    p_org_id UUID,
    p_agent_id UUID,
    p_query TEXT,
    p_colecao TEXT DEFAULT NULL,
    p_limite INT DEFAULT 8
) RETURNS TABLE (
    doc_id UUID,
    slug TEXT,
    titulo TEXT,
    colecao TEXT,
    tag TEXT,
    tipo TEXT,
    trecho TEXT,
    rank REAL
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = agents, public
AS $$
    SELECT
        d.id AS doc_id,
        d.slug,
        d.titulo,
        c.slug AS colecao,
        c.tag,
        d.tipo,
        ts_headline(
            'portuguese',
            coalesce(d.resumo, '') || E'\n\n' || d.conteudo,
            websearch_to_tsquery('portuguese', p_query),
            'MaxFragments=2, MinWords=15, MaxWords=40'
        ) AS trecho,
        ts_rank(d.busca, websearch_to_tsquery('portuguese', p_query))::REAL AS rank
    FROM agents.knowledge_documents d
    JOIN agents.knowledge_collections c ON c.id = d.collection_id
    WHERE d.org_id = p_org_id
      AND d.agent_id = p_agent_id
      AND d.ativo = true
      AND (p_colecao IS NULL OR c.slug = p_colecao)
      AND d.busca @@ websearch_to_tsquery('portuguese', p_query)
    ORDER BY rank DESC, d.updated_at DESC
    LIMIT LEAST(GREATEST(p_limite, 1), 20);
$$;

REVOKE ALL ON FUNCTION agents.search_knowledge(UUID, UUID, TEXT, TEXT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.search_knowledge(UUID, UUID, TEXT, TEXT, INT) TO service_role;
