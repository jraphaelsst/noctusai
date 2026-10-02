-- ============================================================================
-- Canonical identifier formats — the plpgsql twin of
--   noctusai_lib.primitives.identificador  (Python)
--   @noctusai/lib/identificador            (TypeScript)
--
-- OWNER RULE (2026-10-01): the canonical form of every document number / id /
-- protocol is its PUNCTUATED form; an unpunctuated value is CHECKED against
-- the punctuated shape of its type. ONE contract in three runtimes, asserted
-- against ONE case table (seed/lib/shared/identificador.cases.json) — the
-- parity block at the bottom RAISEs at apply time if this SQL drifts (same
-- discipline as social-wiring migration 037 step B4 for phones). The block
-- between the BEGIN-CASES / END-CASES markers is GENERATED from the case
-- table (the Python test `test_sql_twin_parity_block_in_sync_with_case_table`
-- fails when it is stale) — never hand-edit it.
--
-- ADOPTION (a product, phase 2): copy this file into the product's migrations
-- under its next number; the functions are created in the first schema of the
-- migration's `SET search_path`. Idempotent (CREATE OR REPLACE). NEVER
-- invents data: unparseable / DV-invalid / unsupported shape => NULL, and the
-- stored value stays untouched (reversible: store the canonical value in its
-- own column, as `contato_norm` does for phones).
--
-- SQL covers: cpf, cin, cnpj, rg (SP), cep, matricula_imovel,
-- inscricao_municipal (Cotia). The remaining Python/TS types (cnh,
-- titulo_eleitor, nis_pis, cns_cartorio, orgao_expedidor,
-- certidao_controle_receita, protocolo_cenprot) are read-time only: asking
-- SQL for them RAISEs instead of silently returning NULL.
-- ============================================================================

CREATE OR REPLACE FUNCTION identificador_cpf_dv_ok(d text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE t int; i int; soma int; resto int; esperado int;
BEGIN
    IF d IS NULL OR d !~ '^[0-9]{11}$' OR d ~ '^([0-9])\1{10}$' THEN RETURN false; END IF;
    FOR t IN 9..10 LOOP
        soma := 0;
        FOR i IN 1..t LOOP
            soma := soma + substr(d, i, 1)::int * (t + 2 - i);
        END LOOP;
        resto := (soma * 10) % 11;
        esperado := CASE WHEN resto = 10 THEN 0 ELSE resto END;
        IF esperado <> substr(d, t + 1, 1)::int THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END $$;

CREATE OR REPLACE FUNCTION identificador_cnpj_dv_ok(a text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    p1 int[] := ARRAY[5,4,3,2,9,8,7,6,5,4,3,2];
    p2 int[] := ARRAY[6,5,4,3,2,9,8,7,6,5,4,3,2];
    i int; soma int; dv1 int; dv2 int;
BEGIN
    IF a IS NULL OR a !~ '^[0-9A-Z]{12}[0-9]{2}$' OR a ~ '^([0-9])\1{13}$' THEN RETURN false; END IF;
    soma := 0;
    FOR i IN 1..12 LOOP soma := soma + (ascii(substr(a, i, 1)) - 48) * p1[i]; END LOOP;
    dv1 := CASE WHEN soma % 11 < 2 THEN 0 ELSE 11 - soma % 11 END;
    soma := 0;
    FOR i IN 1..12 LOOP soma := soma + (ascii(substr(a, i, 1)) - 48) * p2[i]; END LOOP;
    soma := soma + dv1 * p2[13];
    dv2 := CASE WHEN soma % 11 < 2 THEN 0 ELSE 11 - soma % 11 END;
    RETURN substr(a, 13) = dv1::text || dv2::text;
END $$;

CREATE OR REPLACE FUNCTION identificador_rg_sp_dv(d8 text)
RETURNS text LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE i int; soma int := 0; dv int;
BEGIN
    FOR i IN 1..8 LOOP soma := soma + substr(d8, i, 1)::int * (i + 1); END LOOP;
    dv := 11 - soma % 11;
    RETURN CASE WHEN dv = 10 THEN 'X' WHEN dv = 11 THEN '0' ELSE dv::text END;
END $$;

CREATE OR REPLACE FUNCTION canonizar_identificador(
    tipo text, valor text,
    municipio text DEFAULT NULL, ibge text DEFAULT NULL, uf text DEFAULT NULL)
RETURNS text LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
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
        IF d ~ '^[0-9]{8}$' THEN              -- DV absent: arithmetic completion
            RETURN substr(d,1,2) || '.' || substr(d,3,3) || '.' || substr(d,6,3) || '-' || identificador_rg_sp_dv(d);
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

COMMENT ON FUNCTION canonizar_identificador(text, text, text, text, text) IS
    'Punctuated canonical form of a document id (cpf/cin/cnpj/rg-SP/cep/matricula_imovel/inscricao_municipal-Cotia); NULL when it does not fit. Mirrors noctusai_lib.primitives.identificador.canonico.';

-- Search key: canonical alnum when the value parses, RAW alnum otherwise (a
-- fragment the user typed is not a valid value and must still match).
CREATE OR REPLACE FUNCTION identificador_chave_busca(
    tipo text, valor text,
    municipio text DEFAULT NULL, ibge text DEFAULT NULL, uf text DEFAULT NULL)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT NULLIF(regexp_replace(
        upper(coalesce(canonizar_identificador(tipo, valor, municipio, ibge, uf), btrim(coalesce(valor, '')))),
        '[^0-9A-Z]', '', 'g'), '');
$$;

-- ----------------------------------------------------------------------------
-- PARITY: RAISE if this implementation drifts from the shared case table.
-- ----------------------------------------------------------------------------
DO $parity$
DECLARE r record; got text; falhas text := '';
BEGIN
    FOR r IN SELECT * FROM (VALUES
-- BEGIN-CASES
        ('canon', 'cpf', '412.954.238-98', NULL, NULL, NULL, '412.954.238-98'),
        ('canon', 'cpf', '41295423898', NULL, NULL, NULL, '412.954.238-98'),
        ('canon', 'cpf', ' 412 954 238 98 ', NULL, NULL, NULL, '412.954.238-98'),
        ('canon', 'cpf', '412954238-98', NULL, NULL, NULL, '412.954.238-98'),
        ('canon', 'cpf', '412.954.238-99', NULL, NULL, NULL, NULL),
        ('canon', 'cpf', '111.111.111-11', NULL, NULL, NULL, NULL),
        ('canon', 'cpf', '4129542389', NULL, NULL, NULL, NULL),
        ('canon', 'cpf', '', NULL, NULL, NULL, NULL),
        ('canon', 'cin', '297.556.088-50', NULL, NULL, NULL, '297.556.088-50'),
        ('canon', 'cpf', '29755608850', NULL, NULL, NULL, '297.556.088-50'),
        ('canon', 'cnpj', '11.222.333/0001-81', NULL, NULL, NULL, '11.222.333/0001-81'),
        ('canon', 'cnpj', '11222333000181', NULL, NULL, NULL, '11.222.333/0001-81'),
        ('canon', 'cnpj', '11 222 333 0001 81', NULL, NULL, NULL, '11.222.333/0001-81'),
        ('canon', 'cnpj', '11.222.333/0001-82', NULL, NULL, NULL, NULL),
        ('canon', 'cnpj', '1122233300018', NULL, NULL, NULL, NULL),
        ('canon', 'cnpj', '412.954.238-98', NULL, NULL, NULL, NULL),
        ('canon', 'rg', '30.128.742-9', NULL, NULL, NULL, '30.128.742-9'),
        ('canon', 'rg', '301287429', NULL, NULL, NULL, '30.128.742-9'),
        ('canon', 'rg', '30128742-9', NULL, NULL, NULL, '30.128.742-9'),
        ('canon', 'rg', '30128742', NULL, NULL, NULL, '30.128.742-9'),
        ('canon', 'rg', '16.669.554-3', NULL, NULL, NULL, '16.669.554-3'),
        ('canon', 'rg', '15.668.564-3', NULL, NULL, NULL, NULL),
        ('canon', 'rg', '16669554', NULL, NULL, NULL, '16.669.554-3'),
        ('canon', 'rg', '297.556.088-50', NULL, NULL, NULL, NULL),
        ('canon', 'rg', '29755608850', NULL, NULL, NULL, NULL),
        ('canon', 'rg', '3415227369', NULL, NULL, NULL, NULL),
        ('canon', 'rg', 'W-573.678-Z', NULL, NULL, NULL, NULL),
        ('canon', 'rg', '2964316', NULL, NULL, NULL, NULL),
        ('canon', 'cep', '13010-110', NULL, NULL, NULL, '13010-110'),
        ('canon', 'cep', '13010110', NULL, NULL, NULL, '13010-110'),
        ('canon', 'cep', '13010 110', NULL, NULL, NULL, '13010-110'),
        ('canon', 'cep', '1310110', NULL, NULL, NULL, NULL),
        ('canon', 'cep', '13010-11A', NULL, NULL, NULL, NULL),
        ('canon', 'matricula_imovel', '79.826', NULL, NULL, NULL, '79.826'),
        ('canon', 'matricula_imovel', '79826', NULL, NULL, NULL, '79.826'),
        ('canon', 'matricula_imovel', '79 826', NULL, NULL, NULL, '79.826'),
        ('canon', 'matricula_imovel', '0079826', NULL, NULL, NULL, '79.826'),
        ('canon', 'matricula_imovel', '826', NULL, NULL, NULL, '826'),
        ('canon', 'matricula_imovel', '1234567', NULL, NULL, NULL, '1.234.567'),
        ('canon', 'matricula_imovel', '79.82B', NULL, NULL, NULL, NULL),
        ('canon', 'matricula_imovel', '0', NULL, NULL, NULL, NULL),
        ('canon', 'inscricao_municipal', '23231.42.11.0377.00.000', 'Cotia', NULL, NULL, '23231.42.11.0377.00.000'),
        ('canon', 'inscricao_municipal', '232314211037700000', 'Cotia', NULL, NULL, '23231.42.11.0377.00.000'),
        ('canon', 'inscricao_municipal', '23231/42/11/0377/00/000', 'Cotia', NULL, NULL, '23231.42.11.0377.00.000'),
        ('canon', 'inscricao_municipal', '23231.42.11.0377.00.000-1', 'Cotia', NULL, NULL, '23231.42.11.0377.00.000-1'),
        ('canon', 'inscricao_municipal', '2323142110377000001', 'Cotia', NULL, NULL, '23231.42.11.0377.00.000-1'),
        ('canon', 'inscricao_municipal', '23231.42.11.0377.00.000', NULL, '3513009', NULL, '23231.42.11.0377.00.000'),
        ('canon', 'inscricao_municipal', '23231.42.11.0377.00.00', 'Cotia', NULL, NULL, NULL),
        ('canon', 'inscricao_municipal', '23231.42.11.0377.00.000', 'Osasco', NULL, NULL, NULL),
        ('canon', 'inscricao_municipal', '23231.42.11.0377.00.000', NULL, NULL, NULL, NULL),
        ('chave', 'rg', '30.128.742-9', NULL, NULL, NULL, '301287429'),
        ('chave', 'rg', '30128742', NULL, NULL, NULL, '301287429'),
        ('chave', 'rg', '3012', NULL, NULL, NULL, '3012'),
        ('chave', 'rg', '15.668.564-3', NULL, NULL, NULL, '156685643'),
        ('chave', 'cpf', '412.954.238-98', NULL, NULL, NULL, '41295423898'),
        ('chave', 'cpf', '412.954', NULL, NULL, NULL, '412954'),
        ('chave', 'cnpj', '11.222.333/0001-81', NULL, NULL, NULL, '11222333000181'),
        ('chave', 'cep', '13010-110', NULL, NULL, NULL, '13010110'),
        ('chave', 'matricula_imovel', '79.826', NULL, NULL, NULL, '79826'),
        ('chave', 'matricula_imovel', '0079826', NULL, NULL, NULL, '79826'),
        ('chave', 'inscricao_municipal', '23231.42.11.0377.00.000-1', 'Cotia', NULL, NULL, '2323142110377000001'),
        ('chave', 'inscricao_municipal', '23231.42.11', 'Cotia', NULL, NULL, '232314211')
-- END-CASES
    ) AS t(kind, tipo, entrada, municipio, ibge, uf, esperado) LOOP
        IF r.kind = 'canon' THEN
            got := canonizar_identificador(r.tipo, r.entrada, r.municipio, r.ibge, r.uf);
        ELSE
            got := identificador_chave_busca(r.tipo, r.entrada, r.municipio, r.ibge, r.uf);
        END IF;
        IF got IS DISTINCT FROM r.esperado THEN
            falhas := falhas || format(E'\n  %s(%s, %L): got %L want %L', r.kind, r.tipo, r.entrada, got, r.esperado);
        END IF;
    END LOOP;
    IF falhas <> '' THEN
        RAISE EXCEPTION 'identificador SQL twin drifted from the shared case table:%', falhas;
    END IF;
END $parity$;
