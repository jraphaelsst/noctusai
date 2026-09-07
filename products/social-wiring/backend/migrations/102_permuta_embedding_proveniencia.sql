-- 102_permuta_embedding_proveniencia.sql
--
-- WHICH VECTOR SPACE EACH STORED VECTOR IS IN.
--
-- 🔴 WHY THIS IS A NEW FILE AND NOT AN EDIT TO 101.
-- ------------------------------------------------
-- These two columns were first written INTO `101_permutas_matching.sql`
-- (commit 7f21a0b4) on the belief that 101 was still unapplied. It was not:
-- `permuta_ativos` has been live since 2026-09-06 17:53, applied in two
-- chunks through the Supabase MCP — a path that records into
-- `supabase_migrations.schema_migrations` and writes NOTHING to
-- `social_wiring.schema_migrations`, which is why the product ledger stops
-- at 093 and the file looked unapplied to every check that trusted it.
--
-- Editing an applied migration is a no-op against the database that already
-- ran it, so `7f21a0b4` shipped code selecting two columns that do not
-- exist. This file is the correction, and 101 is restored to the form that
-- actually ran. A migration is append-only once applied; that rule is what
-- keeps a fresh environment and a live one converging instead of drifting.
--
-- WHAT THE COLUMNS ARE FOR
-- ------------------------
-- `embedding` and `embedding_interesses` are `vector(1536)` for EVERY
-- provider, so an OpenAI vector and a Gemini vector fit the same column
-- while being mutually meaningless — a cosine across two embedding spaces
-- is noise, not a weaker signal. Without a per-row record of which space a
-- vector belongs to, the ordinary operator path produces a silently mixed
-- corpus: embed under OpenAI, run out of credit, switch provider (which is
-- exactly what the settings UI advises), embed the remainder under Gemini.
--
-- The consumer makes that worse than "weaker matches":
-- `noctusai_lib.domain.real_estate.matching` takes the COMPOSITE branch
-- whenever similarity > 0, and a cross-space cosine is near-zero but not
-- exactly zero — so the pair keeps 40% of its weight collapsed instead of
-- falling back to the rule score. Ranking quietly becomes "were these two
-- embedded by the same vendor".
--
-- `embeddings.embutir_ativos` reads these columns and treats a row whose
-- provider differs from the current pick as PENDING, so a switch re-embeds
-- and the corpus converges on one space by itself.
--
-- NULL on every existing row is correct and deliberate: a vector with no
-- recorded provenance is unidentifiable, and `_ja_embutido` treats that as
-- stale — cheaper to re-embed than to leave an unattributable vector in the
-- corpus forever. There is no backfill because there is no honest value to
-- backfill with.
--
-- Idempotent: safe to re-run.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.permuta_ativos
    ADD COLUMN IF NOT EXISTS embedding_provider TEXT,
    ADD COLUMN IF NOT EXISTS embedding_modelo   TEXT;

COMMENT ON COLUMN social_wiring.permuta_ativos.embedding_provider IS
    'Vendor that produced the vectors in this row (openai | gemini). NULL = pre-provenance, treated as stale and re-embedded.';
COMMENT ON COLUMN social_wiring.permuta_ativos.embedding_modelo IS
    'Exact model that produced the vectors (e.g. text-embedding-3-small, gemini-embedding-001).';

-- Lets the pending sweep find rows from another space without a seq scan
-- once the registry grows past a few hundred rows.
CREATE INDEX IF NOT EXISTS idx_sw_permuta_ativos_embedding_provider
    ON social_wiring.permuta_ativos (org_id, embedding_provider)
    WHERE embedding IS NOT NULL;
