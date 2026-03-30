-- =====================================================================
-- 008 — Bilateral Embeddings: separate profile vs interest vectors
--
-- The matching system compares profile↔interest (not profile↔profile):
--   A→B: permuta.embedding (profile) vs imovel.embedding_interesses (wants)
--   B→A: imovel.embedding (profile) vs permuta.embedding_interesses (wants)
-- =====================================================================

-- 1. ADD INTEREST EMBEDDING COLUMN
ALTER TABLE erp.ativos
  ADD COLUMN IF NOT EXISTS embedding_interesses extensions.vector(1536);

-- 2. INDEX FOR INTEREST EMBEDDING SIMILARITY SEARCH
CREATE INDEX IF NOT EXISTS idx_ativos_embedding_interesses
  ON erp.ativos
  USING ivfflat (embedding_interesses extensions.vector_cosine_ops)
  WITH (lists = 100);

-- 3. RPC: match ativo profile against counterpart interest embeddings
-- Given a profile embedding, find ativos whose INTEREST embedding is similar.
-- Used for B→A: "which permutas want something like this imóvel?"
-- and A→B: "which imóveis want something like this permuta?"
CREATE OR REPLACE FUNCTION erp.match_ativos_by_interest(
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
    1 - (a.embedding_interesses OPERATOR(extensions.<=>) query_embedding) AS similarity
  FROM erp.ativos a
  WHERE a.embedding_interesses IS NOT NULL
    AND (exclude_id IS NULL OR a.id != exclude_id)
    AND a.status = 'ativo'
    AND 1 - (a.embedding_interesses OPERATOR(extensions.<=>) query_embedding) > similarity_threshold
  ORDER BY a.embedding_interesses OPERATOR(extensions.<=>) query_embedding
  LIMIT match_count;
$$;
