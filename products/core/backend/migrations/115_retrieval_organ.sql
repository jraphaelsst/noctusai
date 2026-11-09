-- Migration: 115_retrieval_organ
-- Schema: public (core)
-- WHAT: storage + RPCs of the seed retrieval organ (noctusai_lib/integrations/retrieval): a shared RAG layer so
--   products stop hand-rolling pgvector copies (DRY N>=3). Lives in core `public`, next to help_chat_* and
--   spend_reservations: every product reaches it through the service-role core client, so no per-product tables.
--   public.retrieval_chunks   - chunked corpus + embedding, one corpus per (namespace, org_id). org_id NULL = platform
--                               scope (e.g. a product's own help knowledge); a org-scoped corpus is NEVER visible to
--                               another org nor to the platform scope: every function filters the EXACT scope.
--   public.retrieval_cache    - semantic cache (similar question -> stored answer), same exact scope + prompt_version
--                               + expiry. Stores a hash of the question, never its text (LGPD).
--   public.retrieval_*()      - match_chunks / replace_corpus / corpus_hash / cache_lookup / cache_put / purge_org.
-- Seed side: noctusai_lib/integrations/retrieval (Protocol + Fake + Real + factory).
-- Vectors are vector(1536) = OpenAI text-embedding-3-small; a different width is a migration + full re-index.
-- Access tier: service (no browser grant; PostgREST exposure counts). Backward-compatible (new objects only).
-- Re-runnable: IF NOT EXISTS / OR REPLACE.
SET search_path = public, extensions;

CREATE TABLE IF NOT EXISTS public.retrieval_chunks (
    id              BIGSERIAL PRIMARY KEY,
    namespace       TEXT NOT NULL,
    org_id          UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    source_hash     TEXT NOT NULL,
    chunk_position  INTEGER NOT NULL,
    heading         TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    embedding       extensions.vector(1536) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS retrieval_chunks_scope_idx ON public.retrieval_chunks (namespace, org_id);
CREATE INDEX IF NOT EXISTS retrieval_chunks_org_idx ON public.retrieval_chunks (org_id) WHERE org_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS retrieval_chunks_embedding_idx
    ON public.retrieval_chunks USING hnsw (embedding extensions.vector_cosine_ops);
-- Chunked knowledge corpora + embeddings of the retrieval organ (exact-scope per namespace/org).
COMMENT ON TABLE public.retrieval_chunks IS 'tier:service';

CREATE TABLE IF NOT EXISTS public.retrieval_cache (
    id              BIGSERIAL PRIMARY KEY,
    namespace       TEXT NOT NULL,
    org_id          UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    prompt_version  TEXT NOT NULL,
    question_hash   TEXT NOT NULL,
    embedding       extensions.vector(1536) NOT NULL,
    answer          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS retrieval_cache_scope_idx
    ON public.retrieval_cache (namespace, org_id, prompt_version, created_at DESC);
CREATE INDEX IF NOT EXISTS retrieval_cache_org_idx ON public.retrieval_cache (org_id) WHERE org_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS retrieval_cache_embedding_idx
    ON public.retrieval_cache USING hnsw (embedding extensions.vector_cosine_ops);
-- Semantic answer cache of the retrieval organ (question hash + embedding + answer, per exact scope, expiring).
COMMENT ON TABLE public.retrieval_cache IS 'tier:service';

ALTER TABLE public.retrieval_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.retrieval_cache ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.retrieval_chunks FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.retrieval_cache FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.retrieval_chunks_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.retrieval_cache_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.retrieval_chunks TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.retrieval_cache TO service_role;
GRANT USAGE ON SEQUENCE public.retrieval_chunks_id_seq TO service_role;
GRANT USAGE ON SEQUENCE public.retrieval_cache_id_seq TO service_role;
DROP POLICY IF EXISTS "service_role_bypass" ON public.retrieval_chunks;
CREATE POLICY "service_role_bypass" ON public.retrieval_chunks FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON public.retrieval_cache;
CREATE POLICY "service_role_bypass" ON public.retrieval_cache FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Corpus identity: the source hash the stored corpus was indexed from (NULL = nothing indexed).
CREATE OR REPLACE FUNCTION public.retrieval_corpus_hash(p_namespace TEXT, p_org_id UUID)
RETURNS TEXT
LANGUAGE sql STABLE
SET search_path = public, extensions, pg_temp
AS $$
    SELECT c.source_hash FROM public.retrieval_chunks c
     WHERE c.namespace = p_namespace AND c.org_id IS NOT DISTINCT FROM p_org_id
     LIMIT 1;
$$;

-- Top-k by cosine similarity inside ONE exact (namespace, org) scope, best first.
CREATE OR REPLACE FUNCTION public.retrieval_match_chunks(
    p_namespace TEXT, p_org_id UUID, p_query extensions.vector, p_k INTEGER, p_min_score DOUBLE PRECISION
) RETURNS TABLE (chunk_position INTEGER, heading TEXT, content TEXT, score DOUBLE PRECISION)
LANGUAGE sql STABLE
SET search_path = public, extensions, pg_temp
AS $$
    SELECT c.chunk_position, c.heading, c.content, (1 - (c.embedding <=> p_query))::double precision AS score
      FROM public.retrieval_chunks c
     WHERE c.namespace = p_namespace AND c.org_id IS NOT DISTINCT FROM p_org_id
       AND (1 - (c.embedding <=> p_query)) >= p_min_score
     ORDER BY c.embedding <=> p_query
     LIMIT least(greatest(p_k, 1), 50);
$$;

-- Atomic corpus swap (one RPC = one transaction): readers see the old or the new corpus, never half.
CREATE OR REPLACE FUNCTION public.retrieval_replace_corpus(
    p_namespace TEXT, p_org_id UUID, p_source_hash TEXT, p_chunks JSONB
) RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_n INTEGER;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('retrieval:' || p_namespace || ':' || coalesce(p_org_id::text, ''), 0));
    DELETE FROM public.retrieval_chunks WHERE namespace = p_namespace AND org_id IS NOT DISTINCT FROM p_org_id;
    INSERT INTO public.retrieval_chunks
        (namespace, org_id, source_hash, chunk_position, heading, content, content_hash, embedding)
    SELECT p_namespace, p_org_id, p_source_hash,
           (e->>'chunk_position')::integer, coalesce(e->>'heading', ''), e->>'content', e->>'content_hash',
           (e->>'embedding')::extensions.vector(1536)
      FROM jsonb_array_elements(p_chunks) AS e;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$;

-- Semantic cache read: same exact scope + prompt_version, unexpired, cosine >= floor; best first.
CREATE OR REPLACE FUNCTION public.retrieval_cache_lookup(
    p_namespace TEXT, p_org_id UUID, p_prompt_version TEXT, p_query extensions.vector, p_min_score DOUBLE PRECISION
) RETURNS TABLE (answer TEXT, score DOUBLE PRECISION)
LANGUAGE sql STABLE
SET search_path = public, extensions, pg_temp
AS $$
    SELECT c.answer, (1 - (c.embedding <=> p_query))::double precision AS score
      FROM public.retrieval_cache c
     WHERE c.namespace = p_namespace AND c.org_id IS NOT DISTINCT FROM p_org_id
       AND c.prompt_version = p_prompt_version AND c.expires_at > now()
       AND (1 - (c.embedding <=> p_query)) >= p_min_score
     ORDER BY c.embedding <=> p_query
     LIMIT 1;
$$;

-- Semantic cache write: replaces the same question under the same version, drops the scope's expired rows and
-- keeps at most 2000 rows per scope (oldest go first).
CREATE OR REPLACE FUNCTION public.retrieval_cache_put(
    p_namespace TEXT, p_org_id UUID, p_prompt_version TEXT, p_question_hash TEXT,
    p_embedding extensions.vector, p_answer TEXT, p_ttl_seconds INTEGER
) RETURNS VOID
LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('retrieval_cache:' || p_namespace || ':' || coalesce(p_org_id::text, ''), 0));
    DELETE FROM public.retrieval_cache
     WHERE namespace = p_namespace AND org_id IS NOT DISTINCT FROM p_org_id
       AND (expires_at <= now() OR (prompt_version = p_prompt_version AND question_hash = p_question_hash));
    INSERT INTO public.retrieval_cache
        (namespace, org_id, prompt_version, question_hash, embedding, answer, expires_at)
    VALUES (p_namespace, p_org_id, p_prompt_version, p_question_hash, p_embedding, p_answer,
            now() + make_interval(secs => p_ttl_seconds));
    DELETE FROM public.retrieval_cache
     WHERE id IN (SELECT id FROM public.retrieval_cache
                   WHERE namespace = p_namespace AND org_id IS NOT DISTINCT FROM p_org_id
                   ORDER BY created_at DESC OFFSET 2000);
END;
$$;

-- LGPD erasure: every chunk and cache row of one org. Returns the rows deleted.
CREATE OR REPLACE FUNCTION public.retrieval_purge_org(p_org_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_a INTEGER;
    v_b INTEGER;
BEGIN
    IF p_org_id IS NULL THEN
        RAISE EXCEPTION 'retrieval_purge_org needs an org_id (the platform scope is never purged by this function)';
    END IF;
    DELETE FROM public.retrieval_chunks WHERE org_id = p_org_id;
    GET DIAGNOSTICS v_a = ROW_COUNT;
    DELETE FROM public.retrieval_cache WHERE org_id = p_org_id;
    GET DIAGNOSTICS v_b = ROW_COUNT;
    RETURN v_a + v_b;
END;
$$;

REVOKE ALL ON FUNCTION public.retrieval_corpus_hash(TEXT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.retrieval_match_chunks(TEXT, UUID, extensions.vector, INTEGER, DOUBLE PRECISION) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.retrieval_replace_corpus(TEXT, UUID, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.retrieval_cache_lookup(TEXT, UUID, TEXT, extensions.vector, DOUBLE PRECISION) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.retrieval_cache_put(TEXT, UUID, TEXT, TEXT, extensions.vector, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.retrieval_purge_org(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.retrieval_corpus_hash(TEXT, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.retrieval_match_chunks(TEXT, UUID, extensions.vector, INTEGER, DOUBLE PRECISION) TO service_role;
GRANT EXECUTE ON FUNCTION public.retrieval_replace_corpus(TEXT, UUID, TEXT, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.retrieval_cache_lookup(TEXT, UUID, TEXT, extensions.vector, DOUBLE PRECISION) TO service_role;
GRANT EXECUTE ON FUNCTION public.retrieval_cache_put(TEXT, UUID, TEXT, TEXT, extensions.vector, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.retrieval_purge_org(UUID) TO service_role;
