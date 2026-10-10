-- ============================================================================
-- 232 — never invent a check digit: an 8-digit RG is stored AS PRINTED
--       (owner rule 2026-10-10: "don't invent the check digit — on a real
--       contract the bank would send it back with invalid data")
-- ============================================================================
-- BUG: `canonizar_identificador('rg', ...)` (187) COMPLETED the SP check digit
-- of an 8-digit RG — which is how a CNH prints "4c DOC. IDENTIDADE". The
-- BEFORE trigger `trg_a_identificadores_canonizar` then stored the computed
-- DV in `clientes.rg` (live: CNH printed 18568536 SSP/SP -> stored
-- 18.568.536-5; the signed contract says 18.568.536).
--
--   A. replace `canonizar_identificador` with the seed's current twin
--      (VERBATIM from seed/lib/sql/identificador.sql): 8 digits -> NN.NNN.NNN,
--      no DV. 9 chars keep the printed DV (validated; a wrong one -> NULL).
--      `identificador_rg_sp_dv` stays: it VALIDATES a printed DV only.
--   B. data repair, decided purely from columns: a `clientes.rg` that carries a
--      DV, whose `rg_origem` is 'cnh', that NO human confirmed
--      (`rg_confirmado_por IS NULL`), and whose own live document reading
--      (`cliente_documentos.extracao_rg`) is the SAME 8 digits WITHOUT a DV, is
--      stripped back to what the document printed. The overwritten value stays
--      in `identificador_canonizacoes` (origem 'backfill'). Idempotent: a
--      repaired row no longer matches; a human-confirmed or RG-card-sourced
--      value is never touched.
-- Forward-only; the trigger re-canonicalising the repaired value is a no-op.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- A. The canonical twin: an 8-digit RG keeps its printed form
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION canonizar_identificador(
    tipo text, valor text,
    municipio text DEFAULT NULL, ibge text DEFAULT NULL, uf text DEFAULT NULL)
RETURNS text LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
DECLARE
    s text := btrim(coalesce(valor, ''));
    d text; nome text; ibge_r text; n bigint;
BEGIN
    IF tipo NOT IN ('cpf','cin','cnpj','rg','cep','matricula_imovel','inscricao_municipal') THEN
        RAISE EXCEPTION 'canonizar_identificador: tipo % sem implementacao SQL', tipo;
    END IF;
    IF s = '' THEN RETURN NULL; END IF;

    IF tipo IN ('cpf', 'cin') THEN
        d := regexp_replace(s, '[-./[:space:]]', '', 'g');
        IF d !~ '^[0-9]{11}$' OR NOT identificador_cpf_dv_ok(d) THEN RETURN NULL; END IF;
        RETURN substr(d,1,3) || '.' || substr(d,4,3) || '.' || substr(d,7,3) || '-' || substr(d,10,2);

    ELSIF tipo = 'cnpj' THEN
        d := regexp_replace(upper(s), '[-./[:space:]]', '', 'g');
        IF d !~ '^[0-9A-Z]{12}[0-9]{2}$' OR NOT identificador_cnpj_dv_ok(d) THEN RETURN NULL; END IF;
        RETURN substr(d,1,2) || '.' || substr(d,3,3) || '.' || substr(d,6,3) || '/' || substr(d,9,4) || '-' || substr(d,13,2);

    ELSIF tipo = 'rg' THEN
        IF uf IS NOT NULL AND upper(uf) <> 'SP' THEN RETURN NULL; END IF;  -- no mask evidenced: never invent
        d := regexp_replace(upper(s), '[-./[:space:]]', '', 'g');
        IF d ~ '^[0-9]{8}$' THEN              -- DV absent: kept AS PRINTED, never computed (owner rule 2026-10-10)
            RETURN substr(d,1,2) || '.' || substr(d,3,3) || '.' || substr(d,6,3);
        ELSIF d ~ '^[0-9]{8}[0-9X]$' THEN
            IF identificador_rg_sp_dv(substr(d,1,8)) <> substr(d,9,1) THEN RETURN NULL; END IF;
            RETURN substr(d,1,2) || '.' || substr(d,3,3) || '.' || substr(d,6,3) || '-' || substr(d,9,1);
        END IF;
        RETURN NULL;

    ELSIF tipo = 'cep' THEN
        d := regexp_replace(s, '[-./[:space:]]', '', 'g');
        IF d !~ '^[0-9]{8}$' THEN RETURN NULL; END IF;   -- 7 digits lost a zero: never guessed
        RETURN substr(d,1,5) || '-' || substr(d,6,3);

    ELSIF tipo = 'matricula_imovel' THEN
        d := regexp_replace(s, '[.[:space:]]', '', 'g');
        IF d !~ '^[0-9]+$' OR length(d) > 9 THEN RETURN NULL; END IF;
        n := d::bigint;
        IF n = 0 THEN RETURN NULL; END IF;
        RETURN regexp_replace(n::text, '([0-9])(?=([0-9]{3})+$)', '\1.', 'g');

    ELSE  -- inscricao_municipal: per-municipio profile (Cotia only)
        ibge_r := ibge;
        IF ibge_r IS NULL AND municipio IS NOT NULL THEN
            nome := regexp_replace(upper(btrim(municipio)), '\s*[-/,]\s*[A-Z]{2}$', '');
            IF btrim(nome) = 'COTIA' THEN ibge_r := '3513009'; END IF;
        END IF;
        IF ibge_r IS DISTINCT FROM '3513009' THEN RETURN NULL; END IF;
        d := regexp_replace(s, '[-./[:space:]]', '', 'g');
        IF d !~ '^[0-9]+$' OR length(d) NOT IN (18, 19) THEN RETURN NULL; END IF;
        RETURN substr(d,1,5) || '.' || substr(d,6,2) || '.' || substr(d,8,2) || '.'
            || substr(d,10,4) || '.' || substr(d,14,2) || '.' || substr(d,16,3)
            || CASE WHEN length(d) = 19 THEN '-' || substr(d,19,1) ELSE '' END;
    END IF;
END $$;


-- ----------------------------------------------------------------------------
-- B. Strip computed DVs from CNH-sourced, unconfirmed RGs
-- ----------------------------------------------------------------------------
WITH alvo AS (
    SELECT c.id, c.org_id, c.rg AS rg_antigo,
           substr(c.rg, 1, 10) AS rg_impresso
      FROM social_wiring.clientes c
     WHERE c.rg ~ '^[0-9]{2}\.[0-9]{3}\.[0-9]{3}-[0-9X]$'
       AND c.rg_origem = 'cnh'
       AND c.rg_confirmado_por IS NULL
       AND EXISTS (
            SELECT 1
              FROM social_wiring.cliente_documentos d
             WHERE d.cliente_id = c.id
               AND d.deleted_at IS NULL
               AND regexp_replace(coalesce(d.extracao_rg, ''), '[-./[:space:]]', '', 'g') ~ '^[0-9]{8}$'
               AND regexp_replace(d.extracao_rg, '[-./[:space:]]', '', 'g')
                   = regexp_replace(substr(c.rg, 1, 10), '[-./[:space:]]', '', 'g')
       )
), log AS (
    INSERT INTO social_wiring.identificador_canonizacoes
        (org_id, tabela, linha_id, campo, tipo, valor_bruto, valor_canonico, origem)
    SELECT org_id, 'clientes', id::text, 'rg', 'rg', rg_antigo, rg_impresso, 'backfill'
      FROM alvo
    RETURNING linha_id
)
UPDATE social_wiring.clientes c
   SET rg = a.rg_impresso
  FROM alvo a
 WHERE c.id = a.id;
