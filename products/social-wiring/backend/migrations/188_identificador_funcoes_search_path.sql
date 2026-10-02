-- ============================================================================
-- 188 — pin the search_path of the identificador SQL helpers (HOTFIX for 187)
--
-- BUG: 187 created `canonizar_identificador`, `identificador_chave_busca`,
-- `identificador_cpf_dv_ok`, `identificador_cnpj_dv_ok`, `identificador_rg_sp_dv`
-- and `identificador_uf_do_orgao` WITHOUT a pinned search_path, and
-- `canonizar_identificador` calls its helpers unqualified. A caller whose
-- search_path lacks `social_wiring` (the Management API, a plain `postgres`
-- session — anything that is not this product's own PostgREST role path) got
--   ERROR 42883: function identificador_cpf_dv_ok(text) does not exist
-- e.g. `SELECT ... FROM social_wiring.vw_identificadores_nao_conformes`.
--
-- FIX: ALTER FUNCTION ... SET search_path = social_wiring, public on each.
-- The trigger functions, `chave_busca_documento` and `clientes_por_cpf`
-- already pin it. Forward-only, idempotent (re-running re-sets the same
-- value); no data touched. The self-check RAISEs unless every function carries
-- the pin in `pg_proc.proconfig`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER FUNCTION social_wiring.identificador_cpf_dv_ok(text)
    SET search_path = social_wiring, public;
ALTER FUNCTION social_wiring.identificador_cnpj_dv_ok(text)
    SET search_path = social_wiring, public;
ALTER FUNCTION social_wiring.identificador_rg_sp_dv(text)
    SET search_path = social_wiring, public;
ALTER FUNCTION social_wiring.canonizar_identificador(text, text, text, text, text)
    SET search_path = social_wiring, public;
ALTER FUNCTION social_wiring.identificador_chave_busca(text, text, text, text, text)
    SET search_path = social_wiring, public;
ALTER FUNCTION social_wiring.identificador_uf_do_orgao(text)
    SET search_path = social_wiring, public;

DO $selfcheck$
DECLARE
    f text;
    faltando text := '';
BEGIN
    FOREACH f IN ARRAY ARRAY[
        'identificador_cpf_dv_ok(text)',
        'identificador_cnpj_dv_ok(text)',
        'identificador_rg_sp_dv(text)',
        'canonizar_identificador(text,text,text,text,text)',
        'identificador_chave_busca(text,text,text,text,text)',
        'identificador_uf_do_orgao(text)'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM pg_proc p
            WHERE p.oid = to_regprocedure('social_wiring.' || f)
              AND EXISTS (
                  SELECT 1 FROM unnest(coalesce(p.proconfig, ARRAY[]::text[])) c
                  WHERE c LIKE 'search_path=%social_wiring%'
              )
        ) THEN
            faltando := faltando || ' ' || f;
        END IF;
    END LOOP;
    IF faltando <> '' THEN
        RAISE EXCEPTION 'migration 188: search_path not pinned on:%', faltando;
    END IF;
END
$selfcheck$;
