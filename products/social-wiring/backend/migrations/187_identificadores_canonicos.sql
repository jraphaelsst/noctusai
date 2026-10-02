-- ============================================================================
-- 187 — canonical identifiers: the punctuated form IS the reference
--       (owner rule 2026-10-01; KB § PATTERNS/common/canonical-identifiers.md)
-- ============================================================================
-- Phase 2 of `identificadores` (phase 1 = the seed registry in Python / TS /
-- plpgsql over ONE case table). This migration is the DATABASE half:
--
--   A. the plpgsql twin, VERBATIM from seed/lib/sql/identificador.sql (its
--      `DO $parity$` block RAISEs at apply time if the SQL drifts from the
--      shared case table — and `test_migration_187_*` fails when this copy
--      stops being byte-identical to the seed's);
--   B. `chave_busca_documento` — the search/index key, wrapped so the
--      expression is index-safe under any caller search_path;
--   C. `identificador_canonizacoes` — the RAW reading of every value a
--      trigger or the backfill canonicalised (compare-don't-reconcile: the
--      canonical form is the reference, the raw reading is never lost);
--   D. one generic BEFORE trigger that stores a value in its canonical
--      punctuated form WHEN IT FITS ITS TYPE — never otherwise — on:
--        clientes.cpf · clientes.rg (UF of its own órgão) · clientes.endereco_cep
--        imovel_dados.numero_matricula · .prefeitura_cadastro_imobiliario · .endereco_manual_cep
--        certidao_consultas.documento (type from tipo_documento)
--      A trigger, not a service call: the next write path added would forget
--      the call (same reasoning as the phone trigger, migration 037);
--   E. `documentos_chave` on clientes / imovel_dados — the HAYSTACK half of
--      the search round-trip (`feedback_canonicalizing_a_value_breaks_search`):
--      the typed needle is keyed the same way in the service;
--   F. `clientes_por_cpf` keyed by `chave_busca_documento('cpf', cpf)` + its
--      expression index (replaces / augments 185's `normalizar_documento`
--      key; same signature, same callers — a CPF key is the same digits);
--   G. `vw_identificadores_nao_conformes` — stored values that do not fit
--      their type (or fit but are still raw): visible, never rewritten.
--
-- DECISIONS PER FIELD (storage)
--   * clientes.cpf / rg / endereco_cep, imovel_dados matrícula / inscrição,
--     certidao_consultas.documento → CANONICAL IN PLACE + raw preserved in C.
--     (cpf/cep/matrícula/IM: the canonical form is the raw digits plus
--     punctuation — no information is added; rg: the SP check digit is
--     COMPLETED arithmetically when absent — the one added digit — and the raw
--     reading stays in C and, for an extraction, on the document row.)
--   * empresas.cnpj → UNCHANGED (digits-only, 49/49 on prod): it is the
--     `(org_id, cnpj)` identity KEY and certidões code compares it with a
--     digits-only `documento`; rendering is canonical through the display seam
--     (`formatIdentificador('cnpj')`). Flip together with certidoes/**.
--   * A value that does not fit its type is NEVER rewritten: it stays as
--     typed/read and shows in G.
--
-- FORWARD-ONLY, IDEMPOTENT (CREATE OR REPLACE / IF NOT EXISTS / DROP TRIGGER
-- IF EXISTS). Existing rows are NOT rewritten here — the triggers only fire
-- on write; stored values are canonicalised by the zero-API backfill
-- (`python -m app.services.identificadores_backfill --org <ORG> --dry-run`).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- A. The plpgsql twin of noctusai_lib.primitives.identificador (VERBATIM)
-- ----------------------------------------------------------------------------
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


-- ----------------------------------------------------------------------------
-- B. The search / index key
-- ----------------------------------------------------------------------------
-- `identificador_chave_busca` (A) resolves `canonizar_identificador`
-- unqualified, so an expression index over it would break under any session
-- whose search_path lacks social_wiring (pg_dump, ANALYZE, a different role).
-- This wrapper pins the path, which is what makes the INDEX expression safe.
CREATE OR REPLACE FUNCTION social_wiring.chave_busca_documento(tipo text, valor text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = social_wiring, public
AS $$
    SELECT social_wiring.identificador_chave_busca(tipo, valor);
$$;

COMMENT ON FUNCTION social_wiring.chave_busca_documento(text, text) IS
    'Search key of a document number: canonical alnum when it parses, RAW alnum '
    'otherwise. Apply to needle AND haystack. Migration 187.';

-- UF of an órgão expedidor reading (`SSP/SP`, `SSP-SP`, `IIRGD` -> SP), NULL
-- when the text carries none. Feeds the RG reading so an RG issued outside SP
-- is never forced into the SP mask. Mirrors `identificadores.uf_do_orgao`.
CREATE OR REPLACE FUNCTION social_wiring.identificador_uf_do_orgao(orgao text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN orgao IS NULL OR btrim(orgao) = '' THEN NULL
        WHEN upper(btrim(orgao)) ~ '^IIRGD' THEN 'SP'
        ELSE (
            SELECT m[1]
              FROM (SELECT regexp_match(upper(btrim(orgao)), '[/.\- ]([A-Z]{2})\s*$') AS m) x
             WHERE m[1] = ANY (ARRAY['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG',
                                     'PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'])
        )
    END;
$$;

-- ----------------------------------------------------------------------------
-- C. The raw reading of everything canonicalised
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.identificador_canonizacoes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    tabela          TEXT NOT NULL,
    linha_id        TEXT NOT NULL,
    campo           TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    valor_bruto     TEXT NOT NULL,
    valor_canonico  TEXT NOT NULL,
    -- 'trigger' (a write) | 'backfill' (the zero-API sweep over stored rows)
    origem          TEXT NOT NULL DEFAULT 'trigger'
        CHECK (origem IN ('trigger', 'backfill')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.identificador_canonizacoes IS
    'The value as it arrived, before it was stored in its canonical punctuated '
    'form (owner rule 2026-10-01). Append-only: the way back for every '
    'canonicalisation. Migration 187.';

CREATE INDEX IF NOT EXISTS idx_sw_identificador_canonizacoes_linha
    ON social_wiring.identificador_canonizacoes (tabela, linha_id, campo, created_at DESC);

ALTER TABLE social_wiring.identificador_canonizacoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "identificador_canonizacoes_select_own_org" ON social_wiring.identificador_canonizacoes;
CREATE POLICY "identificador_canonizacoes_select_own_org" ON social_wiring.identificador_canonizacoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "identificador_canonizacoes_service_role" ON social_wiring.identificador_canonizacoes;
CREATE POLICY "identificador_canonizacoes_service_role" ON social_wiring.identificador_canonizacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- D. Canonical on write — one generic trigger
-- ----------------------------------------------------------------------------
-- Arguments: `campo:tipo` pairs. `tipo` may be `@coluna`: the registry type is
-- read from that column of the row (certidao_consultas.tipo_documento).
-- A value is rewritten ONLY when (i) it is new or changed by this statement
-- and (ii) the registry says it FITS its type — a value that does not fit
-- (bad check digit, unknown mask, another type's number) is left exactly as
-- written. The raw reading is appended to identificador_canonizacoes.
CREATE OR REPLACE FUNCTION social_wiring.canonizar_campos_identificadores()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, public
AS $$
DECLARE
    par       text;
    campo     text;
    tipo      text;
    n         jsonb := to_jsonb(NEW);
    o         jsonb := CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) ELSE '{}'::jsonb END;
    novo      jsonb := '{}'::jsonb;
    bruto     text;
    canon     text;
    uf        text;
    municipio text;
    org       uuid;
BEGIN
    org := NULLIF(n ->> 'org_id', '')::uuid;
    FOREACH par IN ARRAY TG_ARGV LOOP
        campo := split_part(par, ':', 1);
        tipo  := split_part(par, ':', 2);
        IF left(tipo, 1) = '@' THEN
            tipo := lower(btrim(coalesce(n ->> substr(tipo, 2), '')));
        END IF;
        bruto := n ->> campo;
        IF bruto IS NULL OR btrim(bruto) = '' THEN CONTINUE; END IF;
        IF TG_OP = 'UPDATE' AND (o ->> campo) IS NOT DISTINCT FROM bruto THEN CONTINUE; END IF;
        IF tipo NOT IN ('cpf','cin','cnpj','rg','cep','matricula_imovel','inscricao_municipal') THEN
            CONTINUE;
        END IF;

        uf := NULL; municipio := NULL;
        IF tipo = 'rg' THEN
            uf := social_wiring.identificador_uf_do_orgao(n ->> 'rg_orgao_expedidor');
        ELSIF tipo = 'inscricao_municipal' THEN
            SELECT i.cidade INTO municipio
              FROM social_wiring.imoveis i
             WHERE i.org_id = org AND i.codigo = n ->> 'codigo'
             LIMIT 1;
            IF municipio IS NULL THEN
                SELECT r.snap_cidade INTO municipio
                  FROM social_wiring.imovel_registry r
                 WHERE r.org_id = org AND r.codigo_canonical = n ->> 'codigo'
                 LIMIT 1;
            END IF;
        END IF;

        canon := social_wiring.canonizar_identificador(tipo, bruto, municipio, NULL, uf);
        IF canon IS NULL OR canon = bruto THEN CONTINUE; END IF;

        novo := novo || jsonb_build_object(campo, canon);
        INSERT INTO social_wiring.identificador_canonizacoes
            (org_id, tabela, linha_id, campo, tipo, valor_bruto, valor_canonico, origem)
        VALUES
            (org, TG_TABLE_NAME, coalesce(n ->> 'id', n ->> 'codigo', ''), campo, tipo, bruto, canon, 'trigger');
    END LOOP;

    IF novo <> '{}'::jsonb THEN
        NEW := jsonb_populate_record(NEW, novo);
    END IF;
    RETURN NEW;
END $$;

COMMENT ON FUNCTION social_wiring.canonizar_campos_identificadores() IS
    'BEFORE trigger: stores each `campo:tipo` argument in its canonical '
    'punctuated form when it fits its type; raw reading kept in '
    'identificador_canonizacoes. SECURITY DEFINER (pinned search_path) so the '
    'log row lands whichever role wrote the row — same shape as the other '
    'trigger functions of this schema. Migration 187.';

REVOKE ALL ON FUNCTION social_wiring.canonizar_campos_identificadores() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_a_identificadores_canonizar ON social_wiring.clientes;
CREATE TRIGGER trg_a_identificadores_canonizar
    BEFORE INSERT OR UPDATE OF cpf, rg, endereco_cep ON social_wiring.clientes
    FOR EACH ROW EXECUTE FUNCTION social_wiring.canonizar_campos_identificadores(
        'cpf:cpf', 'rg:rg', 'endereco_cep:cep');

DROP TRIGGER IF EXISTS trg_a_identificadores_canonizar ON social_wiring.imovel_dados;
CREATE TRIGGER trg_a_identificadores_canonizar
    BEFORE INSERT OR UPDATE OF numero_matricula, prefeitura_cadastro_imobiliario, endereco_manual_cep
    ON social_wiring.imovel_dados
    FOR EACH ROW EXECUTE FUNCTION social_wiring.canonizar_campos_identificadores(
        'numero_matricula:matricula_imovel', 'prefeitura_cadastro_imobiliario:inscricao_municipal',
        'endereco_manual_cep:cep');

DROP TRIGGER IF EXISTS trg_a_identificadores_canonizar ON social_wiring.certidao_consultas;
CREATE TRIGGER trg_a_identificadores_canonizar
    BEFORE INSERT OR UPDATE OF documento ON social_wiring.certidao_consultas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.canonizar_campos_identificadores(
        'documento:@tipo_documento');

-- ----------------------------------------------------------------------------
-- E. The haystack half of search: `documentos_chave`
-- ----------------------------------------------------------------------------
-- A space-joined list of `chave_busca_documento` of the document columns, kept
-- by a second BEFORE trigger that fires AFTER the canonicalising one (triggers
-- fire in name order: `trg_a_…` then `trg_b_…`). The service keys the typed
-- needle the same way (`identificadores.chaves_do_needle`) and ILIKEs this
-- column, so the number a screen RENDERS (`412.954.238-98`), a bare one and a
-- fragment (`412954`) all find the row — strictly additive to the existing
-- name / phone / e-mail / código passes.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS documentos_chave TEXT;
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS documentos_chave TEXT;

COMMENT ON COLUMN social_wiring.clientes.documentos_chave IS
    'Search keys (alnum) of cpf and rg, space-joined. Maintained by trigger; '
    'never written by the app. Migration 187.';
COMMENT ON COLUMN social_wiring.imovel_dados.documentos_chave IS
    'Search keys (alnum) of numero_matricula and prefeitura_cadastro_imobiliario, '
    'space-joined. Maintained by trigger; never written by the app. Migration 187.';

CREATE OR REPLACE FUNCTION social_wiring.manter_documentos_chave()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, public
AS $$
DECLARE
    par       text;
    campo     text;
    tipo      text;
    n         jsonb := to_jsonb(NEW);
    chaves    text[] := ARRAY[]::text[];
    k         text;
    uf        text;
    municipio text;
    org       uuid;
BEGIN
    org := NULLIF(n ->> 'org_id', '')::uuid;
    FOREACH par IN ARRAY TG_ARGV LOOP
        campo := split_part(par, ':', 1);
        tipo  := split_part(par, ':', 2);
        uf := NULL; municipio := NULL;
        IF tipo = 'rg' THEN
            uf := social_wiring.identificador_uf_do_orgao(n ->> 'rg_orgao_expedidor');
        ELSIF tipo = 'inscricao_municipal' THEN
            SELECT i.cidade INTO municipio
              FROM social_wiring.imoveis i
             WHERE i.org_id = org AND i.codigo = n ->> 'codigo'
             LIMIT 1;
            IF municipio IS NULL THEN
                SELECT r.snap_cidade INTO municipio
                  FROM social_wiring.imovel_registry r
                 WHERE r.org_id = org AND r.codigo_canonical = n ->> 'codigo'
                 LIMIT 1;
            END IF;
        END IF;
        k := social_wiring.identificador_chave_busca(tipo, n ->> campo, municipio, NULL, uf);
        IF k IS NOT NULL THEN chaves := chaves || k; END IF;
    END LOOP;
    NEW := jsonb_populate_record(
        NEW, jsonb_build_object('documentos_chave', NULLIF(array_to_string(chaves, ' '), '')));
    RETURN NEW;
END $$;

COMMENT ON FUNCTION social_wiring.manter_documentos_chave() IS
    'BEFORE trigger: documentos_chave = space-joined chave_busca of the `campo:tipo` '
    'arguments. SECURITY DEFINER (pinned search_path): it reads imoveis / '
    'imovel_registry for the município whichever role wrote the row. Migration 187.';

REVOKE ALL ON FUNCTION social_wiring.manter_documentos_chave() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_b_documentos_chave ON social_wiring.clientes;
CREATE TRIGGER trg_b_documentos_chave
    BEFORE INSERT OR UPDATE OF cpf, rg, rg_orgao_expedidor ON social_wiring.clientes
    FOR EACH ROW EXECUTE FUNCTION social_wiring.manter_documentos_chave('cpf:cpf', 'rg:rg');

DROP TRIGGER IF EXISTS trg_b_documentos_chave ON social_wiring.imovel_dados;
CREATE TRIGGER trg_b_documentos_chave
    BEFORE INSERT OR UPDATE OF numero_matricula, prefeitura_cadastro_imobiliario ON social_wiring.imovel_dados
    FOR EACH ROW EXECUTE FUNCTION social_wiring.manter_documentos_chave(
        'numero_matricula:matricula_imovel', 'prefeitura_cadastro_imobiliario:inscricao_municipal');

-- ----------------------------------------------------------------------------
-- F. clientes_por_cpf on the canonical key
-- ----------------------------------------------------------------------------
-- Same signature, same callers, same result for every CPF (a CPF's key is its
-- eleven digits either way); the key now comes from the ONE registry so a value
-- stored raw and one stored punctuated are the same row, and the lookup agrees
-- with the Python / TS runtimes by construction.
CREATE INDEX IF NOT EXISTS idx_sw_clientes_cpf_chave
    ON social_wiring.clientes (org_id, (social_wiring.chave_busca_documento('cpf', cpf)))
    WHERE cpf IS NOT NULL;

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
       AND social_wiring.chave_busca_documento('cpf', c.cpf) IN (
             SELECT social_wiring.chave_busca_documento('cpf', k)
               FROM unnest(p_cpfs) AS k
              WHERE social_wiring.chave_busca_documento('cpf', k) IS NOT NULL
           )
     ORDER BY c.created_at, c.id;
$$;

COMMENT ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) IS
    'Clientes of one org whose chave_busca_documento(cpf) is among the given '
    'keys (any punctuation), oldest first. Backed by idx_sw_clientes_cpf_chave. '
    'service_role only. Migration 185, re-keyed on the canonical registry by 187.';

REVOKE ALL ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.clientes_por_cpf(UUID, TEXT[]) TO service_role;

-- ----------------------------------------------------------------------------
-- G. What does not fit — visible, never rewritten
-- ----------------------------------------------------------------------------
-- `situacao`: 'canonizavel' — fits its type but is stored in another spelling
-- (the backfill / the next write fixes it); 'nao_cabe' — does not fit (bad
-- check digit, unknown mask, another type's number): a human fixes it.
CREATE OR REPLACE VIEW social_wiring.vw_identificadores_nao_conformes
WITH (security_invoker = true) AS
WITH leitura AS (
    SELECT 'clientes'::text AS tabela, c.org_id, c.id::text AS linha_id, 'cpf'::text AS campo,
           c.cpf AS valor, social_wiring.canonizar_identificador('cpf', c.cpf) AS canonico
      FROM social_wiring.clientes c WHERE c.cpf IS NOT NULL AND btrim(c.cpf) <> ''
    UNION ALL
    SELECT 'clientes', c.org_id, c.id::text, 'rg',
           c.rg,
           social_wiring.canonizar_identificador(
               'rg', c.rg, NULL, NULL, social_wiring.identificador_uf_do_orgao(c.rg_orgao_expedidor))
      FROM social_wiring.clientes c WHERE c.rg IS NOT NULL AND btrim(c.rg) <> ''
    UNION ALL
    SELECT 'clientes', c.org_id, c.id::text, 'endereco_cep',
           c.endereco_cep, social_wiring.canonizar_identificador('cep', c.endereco_cep)
      FROM social_wiring.clientes c WHERE c.endereco_cep IS NOT NULL AND btrim(c.endereco_cep) <> ''
    UNION ALL
    SELECT 'imovel_dados', d.org_id, d.codigo, 'numero_matricula',
           d.numero_matricula, social_wiring.canonizar_identificador('matricula_imovel', d.numero_matricula)
      FROM social_wiring.imovel_dados d WHERE d.numero_matricula IS NOT NULL AND btrim(d.numero_matricula) <> ''
    UNION ALL
    SELECT 'certidao_consultas', q.org_id, q.id::text, 'documento',
           q.documento, social_wiring.canonizar_identificador(q.tipo_documento, q.documento)
      FROM social_wiring.certidao_consultas q WHERE q.documento IS NOT NULL AND btrim(q.documento) <> ''
)
SELECT tabela, org_id, linha_id, campo, valor, canonico,
       CASE WHEN canonico IS NULL THEN 'nao_cabe' ELSE 'canonizavel' END AS situacao
  FROM leitura
 WHERE canonico IS NULL OR canonico <> valor;

COMMENT ON VIEW social_wiring.vw_identificadores_nao_conformes IS
    'Stored document numbers that are not in canonical punctuated form: '
    'situacao=canonizavel (fits, other spelling) | nao_cabe (does not fit its '
    'type — visible, never rewritten). Migration 187.';
