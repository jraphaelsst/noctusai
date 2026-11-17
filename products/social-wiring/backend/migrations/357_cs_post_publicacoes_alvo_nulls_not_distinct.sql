-- ============================================================================
-- 357_cs_post_publicacoes_alvo_nulls_not_distinct.sql -- close the conta-less double-publish hole
-- ============================================================================
-- Migration 342 declared `cs_post_publicacoes_alvo_uq` as "the same post is never queued twice for the same
-- rede x formato x conta while it is live". `conta_id` is nullable (no account picked yet, or ON DELETE SET NULL),
-- and a plain unique index treats NULLs as distinct, so two live rows with conta_id NULL were accepted -- a double
-- publish. Found by the predeploy db_guards probe `sw342_publicacao_alvo_unico` (2026-11-17). The table held 0 rows
-- at authoring time, so the rebuild cannot fail on existing duplicates.
--
-- FORWARD-ONLY, IDEMPOTENT. No SECURITY DEFINER. RLS untouched.
-- ============================================================================

SET search_path = social_wiring, public;

DROP INDEX IF EXISTS social_wiring.cs_post_publicacoes_alvo_uq;
CREATE UNIQUE INDEX cs_post_publicacoes_alvo_uq
    ON social_wiring.cs_post_publicacoes (post_id, rede, formato, conta_id) NULLS NOT DISTINCT
    WHERE status IN ('agendado', 'publicado');

COMMENT ON INDEX social_wiring.cs_post_publicacoes_alvo_uq IS
    'Migration 357: one live publication per post x rede x formato x conta; a NULL conta counts as one target (NULLS NOT DISTINCT).';
