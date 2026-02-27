-- =====================================================================
-- 002 — AI-Based Matching: pgvector embeddings for semantic similarity
-- Run this AFTER 001_erp_imobiliario.sql on your Supabase project.
-- All ERP objects live in the `erp` schema.
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- 1. ENABLE pgvector EXTENSION
-- ─────────────────────────────────────────────────────────────────────
-- pgvector is pre-installed on Supabase — just enable it.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- ─────────────────────────────────────────────────────────────────────
-- 2. ADD EMBEDDING COLUMN TO ativos
-- ─────────────────────────────────────────────────────────────────────
-- 1536 dimensions = OpenAI text-embedding-3-small output size.
ALTER TABLE erp.ativos
  ADD COLUMN IF NOT EXISTS embedding extensions.vector(1536);

-- Free-text field describing what the owner wants in exchange.
-- This gets embedded alongside the property description for richer
-- semantic matching (e.g., "aceita casa com quintal na zona sul").
ALTER TABLE erp.ativos
  ADD COLUMN IF NOT EXISTS interesses_descricao TEXT;

-- ─────────────────────────────────────────────────────────────────────
-- 3. INDEX FOR FAST SIMILARITY SEARCH
-- ─────────────────────────────────────────────────────────────────────
-- IVFFlat index: fast approximate nearest-neighbor search.
-- lists = 100 is good for up to ~100k rows. Increase if you grow past that.
-- We use cosine distance (<=> operator) since embeddings are normalized.
CREATE INDEX IF NOT EXISTS idx_ativos_embedding
  ON erp.ativos
  USING ivfflat (embedding extensions.vector_cosine_ops)
  WITH (lists = 100);

-- ─────────────────────────────────────────────────────────────────────
-- 4. SIMILARITY SEARCH FUNCTION
-- ─────────────────────────────────────────────────────────────────────
-- Returns the top N most similar ativos to a given embedding vector.
-- Called from the backend: db.rpc("match_ativos", { ... })
CREATE OR REPLACE FUNCTION erp.match_ativos(
  query_embedding extensions.vector(1536),
  match_count INT DEFAULT 50,
  similarity_threshold FLOAT DEFAULT 0.3,
  exclude_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  similarity FLOAT
)
LANGUAGE sql STABLE
SET search_path = erp, public, extensions
AS $$
  SELECT
    a.id,
    1 - (a.embedding OPERATOR(extensions.<=>) query_embedding) AS similarity
  FROM erp.ativos a
  WHERE a.embedding IS NOT NULL
    AND (exclude_id IS NULL OR a.id != exclude_id)
    AND a.status = 'ativo'
    AND 1 - (a.embedding OPERATOR(extensions.<=>) query_embedding) > similarity_threshold
  ORDER BY a.embedding OPERATOR(extensions.<=>) query_embedding
  LIMIT match_count;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 5. UPDATE matches TABLE — expand score to NUMERIC for decimal scores
-- ─────────────────────────────────────────────────────────────────────
-- The current score is INTEGER 0-100. AI matching produces decimal scores
-- (e.g., 73.4). Change to NUMERIC(5,1) to preserve precision.
ALTER TABLE erp.matches
  ALTER COLUMN score TYPE NUMERIC(5,1) USING score::NUMERIC(5,1);

-- Drop the old integer check constraint and add a new one for numeric range.
ALTER TABLE erp.matches
  DROP CONSTRAINT IF EXISTS matches_score_check;
ALTER TABLE erp.matches
  ADD CONSTRAINT matches_score_check CHECK (score >= 0 AND score <= 100);

-- Add a breakdown column for the score components (if detalhes is already
-- used for other data, we keep it separate).
ALTER TABLE erp.matches
  ADD COLUMN IF NOT EXISTS score_breakdown JSONB DEFAULT '{}'::JSONB;

-- ─────────────────────────────────────────────────────────────────────
-- 6. DONE
-- ─────────────────────────────────────────────────────────────────────
-- After running this migration:
-- 1. Backend can call OpenAI to generate embeddings on ativo create/update
-- 2. Backend can call match_ativos() RPC for fast similarity search
-- 3. Structured scoring (price, specs, interests) runs in Python
-- 4. Final composite score = 40% embedding + 25% price + 20% specs + 15% interests
