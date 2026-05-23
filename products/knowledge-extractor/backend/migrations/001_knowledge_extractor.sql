-- Migration: 001_knowledge_extractor
-- Schema: knowledge_extractor
-- Applied by: supervisor (not automated — see /CLAUDE.md §6 step 5).
--
-- Creates:
--   - schema knowledge_extractor
--   - extension pgvector (vector)
--   - table kb_document   — one row per source file ingested
--   - table kb_chunk      — chunked text + embedding (1536-dim)
--   - HNSW index on kb_chunk.embedding (cosine ops)
--   - RPC match_kb(query_embedding, match_count) → ranked results
-- ---------------------------------------------------------------------------

-- ── Schema ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS knowledge_extractor;

-- ── pgvector extension (must be enabled by a superuser once per project) ────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── kb_document ─────────────────────────────────────────────────────────────
-- One row per source methodology document.
CREATE TABLE IF NOT EXISTS knowledge_extractor.kb_document (
    id          TEXT        PRIMARY KEY,        -- deterministic: relative path from methodology dir
    module      TEXT        NOT NULL,           -- e.g. "modulo-1", "REFERENCIAS"
    path        TEXT        NOT NULL,           -- original filesystem path (relative to data_dir/methodology/)
    kind        TEXT        NOT NULL DEFAULT 'methodology',  -- 'methodology' | future: 'transcript'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── kb_chunk ─────────────────────────────────────────────────────────────────
-- One row per text chunk; embedding is a 1536-dim vector (text-embedding-3-small).
CREATE TABLE IF NOT EXISTS knowledge_extractor.kb_chunk (
    id          TEXT        PRIMARY KEY,        -- deterministic: "<document_id>-<n>"
    document_id TEXT        NOT NULL REFERENCES knowledge_extractor.kb_document(id) ON DELETE CASCADE,
    content     TEXT        NOT NULL,
    module      TEXT        NOT NULL,
    confidence  FLOAT8      NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    embedding   vector(1536) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── HNSW index (cosine ops) ──────────────────────────────────────────────────
-- HNSW gives sub-linear ANN search; cosine_ops matches the similarity metric
-- used by the match_kb RPC and FakeVectorStore._cosine.
CREATE INDEX IF NOT EXISTS kb_chunk_embedding_hnsw_idx
    ON knowledge_extractor.kb_chunk
    USING hnsw (embedding vector_cosine_ops);

-- ── RPC: match_kb ────────────────────────────────────────────────────────────
-- Called by SupabaseVectorStore.query() and the Edge Function kb-search.
-- Returns chunks ordered by cosine similarity (highest first).
--
-- Parameters:
--   query_embedding  vector(1536)  — the embedded query text
--   match_count      int           — max rows to return (default 5)
--
-- Returns:
--   id, document_id, content, module, confidence, similarity (float8 in [0,1])
CREATE OR REPLACE FUNCTION knowledge_extractor.match_kb(
    query_embedding vector(1536),
    match_count     int DEFAULT 5
)
RETURNS TABLE (
    id          TEXT,
    document_id TEXT,
    content     TEXT,
    module      TEXT,
    confidence  FLOAT8,
    similarity  FLOAT8
)
LANGUAGE sql STABLE
AS $$
    SELECT
        c.id,
        c.document_id,
        c.content,
        c.module,
        c.confidence,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM knowledge_extractor.kb_chunk c
    ORDER BY c.embedding <=> query_embedding   -- <=> = cosine distance (lower = closer)
    LIMIT match_count;
$$;

-- ── Grant (Supabase anon/service roles) ─────────────────────────────────────
-- The Edge Function uses the service-role key (full access).
-- Anon can only call the RPC — never read kb_chunk directly.
GRANT USAGE ON SCHEMA knowledge_extractor TO anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_extractor.kb_document TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_extractor.kb_chunk TO service_role;
GRANT EXECUTE ON FUNCTION knowledge_extractor.match_kb TO anon, authenticated, service_role;
