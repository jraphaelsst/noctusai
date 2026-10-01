-- ============================================================================
-- 185 — social_wiring.clientes_por_cpf(): exact CPF lookup on the normalised index
-- ============================================================================
-- `clientes.cpf` keeps whatever punctuation it arrived with (097), so the only
-- exact comparison is `normalizar_documento(cpf)` — the expression behind
-- `idx_sw_clientes_cpf_norm`. PostgREST cannot filter on an expression, which
-- left two callers working around it, each differently wrong:
--   * `card_hub.partes_service._clientes_por_cpf` matched only the two spellings
--     the app itself writes (bare digits, `ddd.ddd.ddd-dd`);
--   * `matriculas.qualificacao_service._clientes_por_cpf` full-scanned the org.
-- This function is the one exact, index-backed answer both now call
-- (NOC-REMEDIATE[cpf-lookup-normalized-rpc], closed).
--
-- Takes the keys to look for (any punctuation — they are normalised here too)
-- and returns the matching `clientes` rows, oldest first. Org-scoped by an
-- explicit parameter like every sibling RPC (027/133); SECURITY INVOKER, so a
-- caller without the table's grants gets nothing the table would not give it.
-- service_role only — the backend is the sole caller.
--
-- Forward-only, idempotent (CREATE OR REPLACE).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE OR REPLACE FUNCTION social_wiring.clientes_por_cpf(
    p_org_id UUID,
    p_cpfs   TEXT[]
)
RETURNS SETOF social_wiring.clientes
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = social_wiring, public
AS $$
    SELECT c.*
      FROM social_wiring.clientes c
     WHERE c.org_id = p_org_id
       AND c.cpf IS NOT NULL
       AND social_wiring.normalizar_documento(c.cpf) IN (
             SELECT social_wiring.normalizar_documento(k)
               FROM unnest(p_cpfs) AS k
              WHERE social_wiring.normalizar_documento(k) IS NOT NULL
           )
     ORDER BY c.created_at, c.id;
$$;

COMMENT ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) IS
    'Clientes of one org whose normalizar_documento(cpf) is among the given '
    'keys (any punctuation), oldest first. Backed by idx_sw_clientes_cpf_norm. '
    'service_role only. Migration 185.';

REVOKE ALL ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) TO service_role;
