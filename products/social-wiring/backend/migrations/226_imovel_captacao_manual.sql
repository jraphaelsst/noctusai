-- 226 — imovel_captacao (manual captação) + deal refs on imovel_dados + the
-- `imoveis_catalogo` read view (sw-lead-to-contract CONTRACT §8, S6).
--
-- WHY A NEW TABLE AND NOT A ROW IN `imoveis`
-- `imoveis` is the Vista MIRROR, a disposable cache (migration 063). A manual
-- row there would (a) have a NULL `sincronizado_em`, which `_last_sync_at`
-- orders NULLS FIRST and so makes the org look overdue for a re-sync forever,
-- (b) be flipped by `sweep_imovel_registry`, and (c) be overwritten by the
-- upsert on (org_id, codigo) if Vista ever lists the same código. A manual
-- imóvel is a first-class thing with its own table; identity stays in
-- `imovel_registry` (origem_descoberta = 'manual', ativo_no_vista = false).
--
-- Column names are IDENTICAL to `imoveis` so one serializer serves both.
-- The address stays on `imovel_dados.endereco_manual_*` (149/159),
-- `empreendimento_manual` (158) and `em_condominio` (202): never duplicated.

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.attach_acting_audit_triggers (core migration 072) -- apply core first';
  END IF;
END
$guard$;

-- ── 1. imovel_captacao ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imovel_captacao (
    org_id            UUID NOT NULL,
    codigo_canonical  TEXT NOT NULL,

    -- Nullable: a registry-only manual imóvel (the picker's typed-código
    -- "cadastrar novo") is completed later by PATCH, which may not carry a
    -- título. POST /manuais requires one at the API boundary.
    titulo            TEXT,
    categoria         TEXT,
    -- finalidade, free text like the mirror: 'Venda' | 'Aluguel' | 'Venda e Aluguel'
    status            TEXT,
    finalidades       TEXT[] NOT NULL DEFAULT '{}',

    valor_venda       NUMERIC(14, 2),
    valor_locacao     NUMERIC(14, 2),
    valor_condominio  NUMERIC(14, 2),
    valor_iptu        NUMERIC(14, 2),

    area_total        NUMERIC(12, 2),
    area_privativa    NUMERIC(12, 2),
    area_construida   NUMERIC(12, 2),

    dormitorios       INTEGER,
    suites            INTEGER,
    vagas             INTEGER,

    descricao_web     TEXT,
    observacoes       TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por       UUID,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_por       UUID,

    PRIMARY KEY (org_id, codigo_canonical),
    CONSTRAINT imovel_captacao_registry_fk
        FOREIGN KEY (org_id, codigo_canonical)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE CASCADE,
    CONSTRAINT imovel_captacao_valores_positivos CHECK (
        (valor_venda      IS NULL OR valor_venda      > 0)
        AND (valor_locacao    IS NULL OR valor_locacao    > 0)
        AND (valor_condominio IS NULL OR valor_condominio > 0)
        AND (valor_iptu       IS NULL OR valor_iptu       > 0)
        AND (area_total       IS NULL OR area_total       > 0)
        AND (area_privativa   IS NULL OR area_privativa   > 0)
        AND (area_construida  IS NULL OR area_construida  > 0)
    ),
    CONSTRAINT imovel_captacao_comodos_nao_negativos CHECK (
        (dormitorios IS NULL OR dormitorios >= 0)
        AND (suites IS NULL OR suites >= 0)
        AND (vagas  IS NULL OR vagas  >= 0)
    )
);

COMMENT ON TABLE social_wiring.imovel_captacao IS
    'Listing data that only a MANUALLY registered imóvel has (CONTRACT §8). '
    'Never a Vista re-listing: the Vista mirror `imoveis` is never written '
    'for a manual imóvel. Address / empreendimento / em_condominio live on '
    'imovel_dados.';

ALTER TABLE social_wiring.imovel_captacao ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_captacao_select_own_org" ON social_wiring.imovel_captacao;
CREATE POLICY "imovel_captacao_select_own_org"
    ON social_wiring.imovel_captacao
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_captacao_write_own_org" ON social_wiring.imovel_captacao;
CREATE POLICY "imovel_captacao_write_own_org"
    ON social_wiring.imovel_captacao
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_captacao_service_role" ON social_wiring.imovel_captacao;
CREATE POLICY "imovel_captacao_service_role"
    ON social_wiring.imovel_captacao
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── 2. Deal refs on imovel_dados (valid for ANY imóvel, Vista or manual) ──
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS processo_atual_numero TEXT,
    ADD COLUMN IF NOT EXISTS drive_folder_url      TEXT,
    ADD COLUMN IF NOT EXISTS drive_folder_id       TEXT;

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_drive_folder_url_drive;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_drive_folder_url_drive
    CHECK (drive_folder_url IS NULL OR drive_folder_url LIKE 'https://drive.google.com/%');

COMMENT ON COLUMN social_wiring.imovel_dados.processo_atual_numero IS
    'The CURRENT deal''s number (convenience pointer, not the deal''s identity): '
    'an imóvel can be sold or rented more than once. Deals live in processos_venda.';
COMMENT ON COLUMN social_wiring.imovel_dados.drive_folder_url IS
    'Google Drive folder of the imóvel''s deal (https://drive.google.com/… only).';
COMMENT ON COLUMN social_wiring.imovel_dados.drive_folder_id IS
    'Derived from drive_folder_url (…/folders/<id>) by the backend, never typed.';

-- ── 3. imoveis_catalogo — what the list reads (Vista ∪ manual, ONE query) ──
-- security_invoker: RLS of the underlying tables applies to the caller.
CREATE OR REPLACE VIEW social_wiring.imoveis_catalogo
WITH (security_invoker = true) AS
SELECT
    i.org_id, i.codigo, i.codigo_imobiliaria, i.titulo, i.categoria, i.status,
    i.finalidades, i.cep, i.logradouro, i.numero, i.complemento, i.bairro,
    i.cidade, i.uf, i.empreendimento, i.latitude, i.longitude,
    i.valor_venda, i.valor_locacao, i.valor_condominio, i.valor_iptu,
    i.area_total, i.area_privativa, i.area_construida,
    i.dormitorios, i.suites, i.vagas, i.banheiro_social,
    i.foto_destaque, i.fotos, i.corretores, i.construtora,
    i.data_cadastro, i.data_atualizacao,
    i.caracteristicas, i.caracteristicas_raw, i.vista_raw,
    i.sincronizado_em, i.created_at, i.updated_at,
    i.descricao_web, i.observacoes,
    i.ano_construcao, i.situacao, i.ocupacao, i.pavimentos, i.posicao,
    i.elevador, i.portaria, i.exclusivo, i.aceita_permuta,
    i.aceita_financiamento, i.destaque_web, i.super_destaque_web,
    i.exibir_no_site, i.chave, i.zona, i.regiao,
    i.area_terreno, i.frente, i.fundos, i.closet,
    i.referencia, i.matricula_vista, i.inscricao_municipal,
    i.video_destaque, i.tour_360,
    i.codigo_norm,
    'vista'::text AS fonte
FROM social_wiring.imoveis i
UNION ALL
SELECT
    r.org_id,
    COALESCE(r.codigo_display, r.codigo_canonical),
    NULL::text,
    c.titulo, c.categoria, c.status,
    COALESCE(c.finalidades, '{}'::text[]),
    d.endereco_manual_cep, d.endereco_manual_logradouro, d.endereco_manual_numero,
    d.endereco_manual_complemento, d.endereco_manual_bairro,
    d.endereco_manual_cidade, d.endereco_manual_uf,
    d.empreendimento_manual,
    NULL::double precision, NULL::double precision,
    c.valor_venda, c.valor_locacao, c.valor_condominio, c.valor_iptu,
    c.area_total, c.area_privativa, c.area_construida,
    c.dormitorios, c.suites, c.vagas, NULL::boolean,
    NULL::text, '{}'::text[], '[]'::jsonb, NULL::text,
    COALESCE(c.created_at, r.created_at)::date,
    COALESCE(c.updated_at, r.updated_at, r.created_at)::date,
    '{}'::text[], '{}'::jsonb, '{}'::jsonb,
    NULL::timestamptz,
    COALESCE(c.created_at, r.created_at),
    COALESCE(c.updated_at, r.updated_at, r.created_at),
    c.descricao_web, c.observacoes,
    NULL::integer, NULL::text, NULL::text, NULL::integer, NULL::text,
    NULL::boolean, NULL::boolean, NULL::boolean, NULL::boolean,
    NULL::boolean, NULL::boolean, NULL::boolean,
    NULL::boolean, NULL::text, NULL::text, NULL::text,
    NULL::numeric(12, 2), NULL::numeric(12, 2), NULL::numeric(12, 2), NULL::integer,
    NULL::text, NULL::text, NULL::text,
    NULL::text, NULL::text,
    r.codigo_canonical,
    'manual'::text AS fonte
FROM social_wiring.imovel_registry r
LEFT JOIN social_wiring.imovel_captacao c
  ON c.org_id = r.org_id AND c.codigo_canonical = r.codigo_canonical
LEFT JOIN social_wiring.imovel_dados d
  ON d.org_id = r.org_id AND d.codigo = r.codigo_canonical
WHERE r.origem_descoberta = 'manual';

COMMENT ON VIEW social_wiring.imoveis_catalogo IS
    'Vista mirror ∪ manual captação, one row per imóvel, `fonte` = vista|manual (manual = every registry row with origem_descoberta = ''manual'', captação or not) '
    '(CONTRACT §8.3). The list route reads this so filters, count=exact, order '
    'and pages stay one exact PostgREST query.';

GRANT SELECT ON social_wiring.imoveis_catalogo TO authenticated, service_role;

SELECT public.attach_acting_audit_triggers('social_wiring');

NOTIFY pgrst, 'reload schema';
