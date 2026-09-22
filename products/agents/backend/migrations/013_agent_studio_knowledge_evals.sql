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
-- ANON + AUTHENTICATED WRITE LOCKDOWN (wave-1 security review M5, mirrors
-- 009/010 and 012): `011_anon_grant_lockdown.sql`'s schema DEFAULT
-- PRIVILEGES already withhold `anon`, but a default is only as good as the
-- role the migration runs as — so every table below restates
-- `REVOKE ALL ... FROM anon` explicitly, and REVOKEs `authenticated`'s
-- INSERT/UPDATE/DELETE/TRUNCATE grant (inherited from 001's schema-wide
-- ALL). `authenticated` keeps SELECT for the org-scoped read policy. RLS
-- having no write policy is one layer; the missing grant is the second.
--
-- SECURITY DEFINER EXECUTE LOCKDOWN (mirrors 006's H1 finding): every
-- SECURITY DEFINER function this file declares (`search_knowledge`,
-- `list_knowledge_documents`, `create_eval_run`) is immediately followed by
-- a `REVOKE ALL ... FROM PUBLIC, anon, authenticated` + `GRANT EXECUTE ...
-- TO service_role` pair — `tests/studio/ke/test_migration_013_shape.py`'s
-- `TestSecurityDefinerExecuteGrants` enforces this generically.
--
-- SIZE CAPS (M3): collection metadata (nome/tag/descricao) is compiled into
-- EVERY prompt of the agent — a LIVE, ungated prompt input — so it is capped
-- tight; document bodies are capped at 2 000 000 chars. Same numbers as
-- `app.studio.models.LIMITS` (the HTTP schemas and the stores enforce them
-- first; these CHECKs are the backstop).
-- ============================================================================

SET search_path = agents, public;

-- No trigram index (2026-09-21, found by a BEGIN…ROLLBACK dry run against the
-- live schema): on this project pg_trgm is installed in the `social_wiring`
-- schema, so an `IF NOT EXISTS … WITH SCHEMA extensions` install is a no-op
-- and its operator class is not reachable under `extensions`. Nothing queries
-- trigrams — titles are already searchable at weight A of `busca` — so the
-- index is dropped rather than coupling this schema to another product's.


-- ────────────────────────────────────────────────────────────────────────
-- knowledge_collections
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.knowledge_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    nome TEXT NOT NULL CHECK (length(nome) <= 120),
    tag TEXT NULL CHECK (length(tag) <= 12),
    descricao TEXT NOT NULL DEFAULT '' CHECK (length(descricao) <= 600),
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

REVOKE ALL ON agents.knowledge_collections FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.knowledge_collections FROM authenticated;


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
    conteudo TEXT NOT NULL CHECK (length(conteudo) <= 2000000),
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

CREATE OR REPLACE TRIGGER set_updated_at_knowledge_documents
    BEFORE UPDATE ON agents.knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION agents.set_updated_at();

REVOKE ALL ON agents.knowledge_documents FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.knowledge_documents FROM authenticated;


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

REVOKE ALL ON agents.knowledge_revisions FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.knowledge_revisions FROM authenticated;


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

REVOKE ALL ON agents.eval_cases FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.eval_cases FROM authenticated;


-- ────────────────────────────────────────────────────────────────────────
-- eval_runs — at most one `pendente`/`executando` run per version
-- (contract §B2 "one pendente|executando run per version").
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE agents.eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    agent_id UUID NOT NULL REFERENCES agents.agents(id),
    -- L8: a discarded draft takes its runs (and, via eval_results' own
    -- cascade, their results) with it.
    version_id UUID NOT NULL REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    compiled_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pendente', 'executando', 'concluida', 'falhou', 'cancelada')),
    total INT NOT NULL DEFAULT 0,
    aprovados INT NOT NULL DEFAULT 0,
    score NUMERIC(4, 3) NULL,
    limiar NUMERIC(4, 3) NOT NULL,
    -- H1: true ONLY when the run covered every active case at run time
    -- (`case_ids` omitted). The publish gate requires it; subset runs stay
    -- allowed for iteration but never satisfy the gate.
    completa BOOLEAN NOT NULL DEFAULT false,
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

REVOKE ALL ON agents.eval_runs FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.eval_runs FROM authenticated;


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

REVOKE ALL ON agents.eval_results FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.eval_results FROM authenticated;


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
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = agents, public
AS $$
BEGIN
    -- L5: bounded query (the router caps it at the same 512).
    IF p_query IS NULL OR length(p_query) > 512 THEN
        RAISE EXCEPTION 'query_too_long' USING ERRCODE = 'P0001';
    END IF;
    RETURN QUERY
    SELECT
        d.id AS doc_id,
        d.slug,
        d.titulo,
        c.slug AS colecao,
        c.tag,
        d.tipo,
        -- L5: ts_headline re-parses its whole input — bound it, a 2 MB
        -- document must not cost a 2 MB headline pass per hit.
        ts_headline(
            'portuguese',
            coalesce(d.resumo, '') || E'\n\n' || left(d.conteudo, 50000),
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
END;
$$;

REVOKE ALL ON FUNCTION agents.search_knowledge(UUID, UUID, TEXT, TEXT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.search_knowledge(UUID, UUID, TEXT, TEXT, INT) TO service_role;


-- ────────────────────────────────────────────────────────────────────────
-- agents.list_knowledge_documents — the admin document list (L4). The free
-- text filter is matched HERE, as a bound parameter with its LIKE
-- metacharacters (`\`, `%`, `_`) escaped — never interpolated into a
-- PostgREST `or=(...)` filter string, where a `,` or `)` in the user's text
-- rewrites the filter itself. Returns `{"total": n, "items": [...]}` so the
-- total survives an empty page. `p_q` capped at 200 (the router caps it too).
-- Archived documents are listed (the admin UI shows the `ativo` flag).
-- ────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION agents.list_knowledge_documents(
    p_org_id UUID,
    p_agent_id UUID,
    p_collection_id UUID,
    p_q TEXT DEFAULT NULL,
    p_tipo TEXT DEFAULT NULL,
    p_limit INT DEFAULT 20,
    p_offset INT DEFAULT 0
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_pat TEXT;
    v_total BIGINT;
    v_items JSONB;
BEGIN
    IF p_q IS NOT NULL AND length(p_q) > 200 THEN
        RAISE EXCEPTION 'query_too_long' USING ERRCODE = 'P0001';
    END IF;
    IF p_q IS NOT NULL AND p_q <> '' THEN
        v_pat := '%' || replace(replace(replace(p_q, '\', '\\'), '%', '\%'), '_', '\_') || '%';
    END IF;

    SELECT count(*) INTO v_total
    FROM agents.knowledge_documents d
    WHERE d.org_id = p_org_id AND d.agent_id = p_agent_id AND d.collection_id = p_collection_id
      AND (p_tipo IS NULL OR d.tipo = p_tipo)
      AND (v_pat IS NULL
           OR d.titulo ILIKE v_pat ESCAPE '\'
           OR d.resumo ILIKE v_pat ESCAPE '\'
           OR d.conteudo ILIKE v_pat ESCAPE '\');

    SELECT COALESCE(jsonb_agg(to_jsonb(r) ORDER BY r.updated_at DESC, r.id), '[]'::JSONB) INTO v_items
    FROM (
        SELECT d.id, d.org_id, d.collection_id, d.agent_id, d.slug, d.titulo, d.tipo,
               d.proveniencia, d.resumo, d.conteudo, d.source_sha, d.ativo, d.created_at, d.updated_at
        FROM agents.knowledge_documents d
        WHERE d.org_id = p_org_id AND d.agent_id = p_agent_id AND d.collection_id = p_collection_id
          AND (p_tipo IS NULL OR d.tipo = p_tipo)
          AND (v_pat IS NULL
               OR d.titulo ILIKE v_pat ESCAPE '\'
               OR d.resumo ILIKE v_pat ESCAPE '\'
               OR d.conteudo ILIKE v_pat ESCAPE '\')
        ORDER BY d.updated_at DESC, d.id
        LIMIT LEAST(GREATEST(p_limit, 1), 100)
        OFFSET GREATEST(p_offset, 0)
    ) r;

    RETURN jsonb_build_object('total', v_total, 'items', v_items);
END;
$$;

REVOKE ALL ON FUNCTION agents.list_knowledge_documents(UUID, UUID, UUID, TEXT, TEXT, INT, INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.list_knowledge_documents(UUID, UUID, UUID, TEXT, TEXT, INT, INT) TO service_role;


-- ────────────────────────────────────────────────────────────────────────
-- agents.create_eval_run — run + its pending results in ONE transaction
-- (L6): a failure after the run insert can never leave an orphan
-- `pendente` run occupying the one-active-run-per-version slot.
--
-- `p_case_ids` NULL ⇒ every ACTIVE case of the agent, `completa = true`
-- (H1). An explicit list ⇒ deduped, capped at 200, every id must be a case
-- of THIS agent, `completa = false`. A second in-flight run of the same
-- version trips `eval_runs_one_active_per_version_idx` (SQLSTATE 23505 —
-- the store maps it to `run_in_progress`). Raises `version_not_found`,
-- `eval_case_not_found`, `too_many_cases`, `no_eval_cases`.
-- ────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION agents.create_eval_run(
    p_org_id UUID,
    p_agent_id UUID,
    p_version_id UUID,
    p_compiled_hash TEXT,
    p_limiar NUMERIC,
    p_case_ids UUID[],
    p_started_by UUID
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_cases UUID[];
    v_found INT;
    v_run_id UUID;
    v_completa BOOLEAN := p_case_ids IS NULL;
BEGIN
    PERFORM 1 FROM agents.agent_versions
    WHERE id = p_version_id AND org_id = p_org_id AND agent_id = p_agent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'version_not_found' USING ERRCODE = 'P0001';
    END IF;

    IF v_completa THEN
        SELECT COALESCE(array_agg(c.id ORDER BY c.created_at, c.id), '{}') INTO v_cases
        FROM agents.eval_cases c
        WHERE c.org_id = p_org_id AND c.agent_id = p_agent_id AND c.ativo;
    ELSE
        SELECT COALESCE(array_agg(DISTINCT x), '{}') INTO v_cases FROM unnest(p_case_ids) AS x;
        IF cardinality(v_cases) > 200 THEN
            RAISE EXCEPTION 'too_many_cases' USING ERRCODE = 'P0001';
        END IF;
        SELECT count(*) INTO v_found FROM agents.eval_cases c
        WHERE c.id = ANY(v_cases) AND c.org_id = p_org_id AND c.agent_id = p_agent_id;
        IF v_found <> cardinality(v_cases) THEN
            RAISE EXCEPTION 'eval_case_not_found' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF cardinality(v_cases) = 0 THEN
        RAISE EXCEPTION 'no_eval_cases' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO agents.eval_runs (
        org_id, agent_id, version_id, compiled_hash, status, total, aprovados,
        limiar, completa, started_by, started_at
    ) VALUES (
        p_org_id, p_agent_id, p_version_id, p_compiled_hash, 'pendente', cardinality(v_cases), 0,
        p_limiar, v_completa, p_started_by, now()
    )
    RETURNING id INTO v_run_id;

    INSERT INTO agents.eval_results (org_id, run_id, case_id, status)
    SELECT p_org_id, v_run_id, x, 'pendente' FROM unnest(v_cases) AS x;

    RETURN v_run_id;
END;
$$;

REVOKE ALL ON FUNCTION agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.create_eval_run(UUID, UUID, UUID, TEXT, NUMERIC, UUID[], UUID) TO service_role;
