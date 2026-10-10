-- 228 -- possível duplicado (detect / surface / dismiss) + "É o mesmo imóvel" (link)
-- (sw-lead-to-contract CONTRACT §8.6 + §8.7, S6 dup-A).
--
-- A manual imóvel (SW-####, 226) and a Vista listing may be the same property.
-- NOTHING here merges anything:
--   1. imovel_duplicata_candidatos -- the detected pairs (pendente / descartado /
--      confirmado), one row per (manual, vista) pair, never resurrected once
--      descartado.
--   2. imovel_registry.vinculado_a -- the LINK. The manual registry row points at
--      the Vista registry row; no FK in the 12+ referencing tables is rewritten,
--      so unlinking is exact. One manual per Vista row (partial UNIQUE); a row
--      never links to itself (CHECK).
--   3. imovel_vinculo_eventos -- the audit trail of link / unlink (no house
--      timeline for imóvel events exists; imovel_registry has no history table).
--      Written only by the backend (service role); authenticated may only read.
--   4. imoveis_catalogo gains possivel_duplicado (EXISTS a pendente pair) on BOTH
--      arms, appended after `fonte` (CREATE OR REPLACE VIEW only allows new
--      columns at the end).
--
-- Cross-org links are refused by the service (it resolves both rows by org_id);
-- the registry FK is by id.

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.attach_acting_audit_triggers (core migration 072) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.imovel_captacao') IS NULL THEN
    RAISE EXCEPTION 'this migration requires 226 (imovel_captacao / imoveis_catalogo) -- apply it first';
  END IF;
END
$guard$;

-- ── 1. imovel_duplicata_candidatos ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imovel_duplicata_candidatos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    codigo_manual  TEXT NOT NULL,
    codigo_vista   TEXT NOT NULL,
    score          NUMERIC(4, 3) NOT NULL,
    sinais         JSONB NOT NULL DEFAULT '[]'::jsonb,
    status         TEXT NOT NULL DEFAULT 'pendente',
    detectado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolvido_por  UUID,
    resolvido_em   TIMESTAMPTZ,

    CONSTRAINT imovel_duplicata_manual_fk FOREIGN KEY (org_id, codigo_manual)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical),
    CONSTRAINT imovel_duplicata_vista_fk FOREIGN KEY (org_id, codigo_vista)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical),
    CONSTRAINT uq_imovel_duplicata_par UNIQUE (org_id, codigo_manual, codigo_vista),
    CONSTRAINT imovel_duplicata_score_faixa CHECK (score >= 0 AND score <= 1),
    CONSTRAINT imovel_duplicata_status_valido
        CHECK (status IN ('pendente', 'descartado', 'confirmado')),
    CONSTRAINT imovel_duplicata_lados_distintos CHECK (codigo_manual <> codigo_vista)
);

CREATE INDEX IF NOT EXISTS idx_imovel_duplicata_org_status
    ON social_wiring.imovel_duplicata_candidatos (org_id, status, score DESC);
CREATE INDEX IF NOT EXISTS idx_imovel_duplicata_vista
    ON social_wiring.imovel_duplicata_candidatos (org_id, codigo_vista);

COMMENT ON TABLE social_wiring.imovel_duplicata_candidatos IS
    'Possible manual-vs-Vista duplicate pairs (CONTRACT §8.6). Detected, shown, '
    'dismissed or linked by a human; never merged automatically. A `descartado` '
    'pair is never re-suggested.';

ALTER TABLE social_wiring.imovel_duplicata_candidatos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_duplicata_candidatos_select_own_org" ON social_wiring.imovel_duplicata_candidatos;
CREATE POLICY "imovel_duplicata_candidatos_select_own_org"
    ON social_wiring.imovel_duplicata_candidatos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_duplicata_candidatos_write_own_org" ON social_wiring.imovel_duplicata_candidatos;
CREATE POLICY "imovel_duplicata_candidatos_write_own_org"
    ON social_wiring.imovel_duplicata_candidatos
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_duplicata_candidatos_service_role" ON social_wiring.imovel_duplicata_candidatos;
CREATE POLICY "imovel_duplicata_candidatos_service_role"
    ON social_wiring.imovel_duplicata_candidatos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── 2. imovel_registry.vinculado_a (§8.7 the LINK) ─────────────────────────
ALTER TABLE social_wiring.imovel_registry
    ADD COLUMN IF NOT EXISTS vinculado_a UUID REFERENCES social_wiring.imovel_registry (id);

ALTER TABLE social_wiring.imovel_registry
    DROP CONSTRAINT IF EXISTS imovel_registry_vinculo_nao_a_si_mesmo;
ALTER TABLE social_wiring.imovel_registry
    ADD CONSTRAINT imovel_registry_vinculo_nao_a_si_mesmo
    CHECK (vinculado_a IS NULL OR vinculado_a <> id);

-- One manual imóvel per Vista row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_imovel_registry_vinculado_a
    ON social_wiring.imovel_registry (vinculado_a)
    WHERE vinculado_a IS NOT NULL;

COMMENT ON COLUMN social_wiring.imovel_registry.vinculado_a IS
    'On a MANUAL registry row: the id of the Vista registry row it is the same '
    'property as (CONTRACT §8.7). Nothing referencing the manual código is '
    're-pointed; clearing this column undoes the link exactly.';

-- ── 3. imovel_vinculo_eventos (audit of link / unlink) ─────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imovel_vinculo_eventos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    codigo_manual  TEXT NOT NULL,
    codigo_vista   TEXT NOT NULL,
    acao           TEXT NOT NULL,
    duplicata_id   UUID,
    ator           UUID,
    legal          JSONB,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT imovel_vinculo_eventos_acao_valida
        CHECK (acao IN ('vincular', 'desvincular'))
);

CREATE INDEX IF NOT EXISTS idx_imovel_vinculo_eventos_manual
    ON social_wiring.imovel_vinculo_eventos (org_id, codigo_manual, criado_em DESC);

COMMENT ON TABLE social_wiring.imovel_vinculo_eventos IS
    'Append-only trail of "É o mesmo imóvel" link / unlink actions (CONTRACT '
    '§8.7): who, when, which pair, and the outcome of the legal-data '
    'reconciliation. Written by the backend only (service role).';

ALTER TABLE social_wiring.imovel_vinculo_eventos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_vinculo_eventos_select_own_org" ON social_wiring.imovel_vinculo_eventos;
CREATE POLICY "imovel_vinculo_eventos_select_own_org"
    ON social_wiring.imovel_vinculo_eventos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_vinculo_eventos_service_role" ON social_wiring.imovel_vinculo_eventos;
CREATE POLICY "imovel_vinculo_eventos_service_role"
    ON social_wiring.imovel_vinculo_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── 4. imoveis_catalogo + possivel_duplicado (both arms, after `fonte`) ────
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
    'vista'::text AS fonte,
    EXISTS (
        SELECT 1 FROM social_wiring.imovel_duplicata_candidatos dup
        WHERE dup.org_id = i.org_id AND dup.status = 'pendente'
          AND (dup.codigo_vista = i.codigo_norm OR dup.codigo_manual = i.codigo_norm)
    ) AS possivel_duplicado
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
    'manual'::text AS fonte,
    EXISTS (
        SELECT 1 FROM social_wiring.imovel_duplicata_candidatos dup
        WHERE dup.org_id = r.org_id AND dup.status = 'pendente'
          AND (dup.codigo_vista = r.codigo_canonical OR dup.codigo_manual = r.codigo_canonical)
    ) AS possivel_duplicado
FROM social_wiring.imovel_registry r
LEFT JOIN social_wiring.imovel_captacao c
  ON c.org_id = r.org_id AND c.codigo_canonical = r.codigo_canonical
LEFT JOIN social_wiring.imovel_dados d
  ON d.org_id = r.org_id AND d.codigo = r.codigo_canonical
WHERE r.origem_descoberta = 'manual';

COMMENT ON VIEW social_wiring.imoveis_catalogo IS
    'Vista mirror ∪ manual captação, one row per imóvel, `fonte` = vista|manual, '
    '`possivel_duplicado` = a pendente duplicate pair involves the código '
    '(CONTRACT §8.3 / §8.6). The list route reads this so filters, count=exact, '
    'order and pages stay one exact PostgREST query.';

GRANT SELECT ON social_wiring.imoveis_catalogo TO authenticated, service_role;

SELECT public.attach_acting_audit_triggers('social_wiring');

NOTIFY pgrst, 'reload schema';
