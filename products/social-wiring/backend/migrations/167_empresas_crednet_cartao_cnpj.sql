-- ============================================================================
-- Migration 167 · social_wiring: empresas (companies a party is linked to),
-- Serasa Crednet, Cartão CNPJ, and the certidão/checklist/nome_mae wiring
-- the P0c contract needs — roadmap `sw-drive-extraction-2026-09.md` §E1-E8,
-- contract `project-history/roadmaps/sw-drive-extraction-P0c-contract.md` §A.
--
-- WHAT THIS IS
-- ------------
-- A vendedor/comprador may be a sócio of one or more empresas (PJs), and the
-- contract's PJ certidões clause needs that graph: who owns which company,
-- what its cadastral situação is (does it still need certidões, or was it
-- baixada more than 5 years ago), and the Cartão CNPJ that situação is read
-- from. Two new machine readers feed it: Serasa Crednet (a PF's credit
-- report, which ALSO lists the CNPJs that person participates in) and
-- Cartão CNPJ (the company's own registry printout).
--
-- 🔴 WHY `empresas` IS ITS OWN TABLE, NOT COLUMNS ON `clientes`
-- ----------------------------------------------------------------------------
-- A company is not a property of one person — the same CNPJ recurs across
-- multiple sócios (spouses co-own the same holding, a comprador and a
-- vendedor may share a CNPJ across different deals) and must resolve to the
-- SAME row every time, not one copy per cliente. `cliente_empresa_
-- participacoes` is the join, same shape `atendimento_partes` already uses
-- to keep a person and a role separate facts.
--
-- 🔴 GROUP-LEVEL PROVENANCE, NOT PER-FIELD (owner decision, accepted — see
-- the contract §H12)
-- ----------------------------------------------------------------------------
-- Unlike `clientes`/`imovel_dados`, `empresas`' machine-read fields
-- (razao_social, nome_fantasia, natureza_juridica, data_abertura,
-- situacao_cadastral, data_situacao_cadastral, motivo_situacao, uf) share
-- ONE `dados_*` provenance quintet rather than one per field. A Cartão CNPJ
-- reads them all off a single document in a single pass; the group is the
-- unit of trust here, same as `imovel_hub.campos_extraidos_service`'s
-- pointer GROUPS (título aquisitivo / ônus fonte). A DISAGREEING field still
-- opens its OWN `empresa_campo_conflitos` row (per field, not per group) —
-- the group only decides what gets STAMPED when a fill lands clean.
--
-- 🔴 THE BACKFILL DOES NOT COPY SITUAÇÃO (owner decision, contract §H4)
-- ----------------------------------------------------------------------------
-- Existing `certidao_consultas` rows with `tipo_documento='cnpj'` prove a
-- company was already being investigated. The backfill below creates an
-- `empresas` row for each of those CNPJs and links the consulta and its
-- participação — but leaves `situacao_cadastral`/`data_situacao_cadastral`
-- NULL. The owner: "the Crednet date is wrong" (case 883) — only a Cartão
-- CNPJ is trustworthy for the closing date, so a backfilled empresa shows
-- `faltando: cartao_cnpj` until one is uploaded. Honest incompleteness, not
-- a silently wrong situação.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change.
-- Apply via `noctus.dev.migrate_product` only after the tech-lead and the
-- user have given an explicit go-ahead. See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. empresas
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.empresas (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   UUID NOT NULL,

    -- Alphanumeric-tolerant: `noctusai_lib.integrations.documents.cnpj`
    -- already accepts the alphanumeric CNPJ format Receita phases in from
    -- 2026. Check-digit validity is verified in the app (`cnpj.is_valid`),
    -- never in SQL — this CHECK is shape-only.
    cnpj                     TEXT NOT NULL
        CHECK (cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$'),
    razao_social             TEXT,
    nome_fantasia            TEXT,
    natureza_juridica        TEXT,
    data_abertura            DATE,
    situacao_cadastral       TEXT
        CHECK (situacao_cadastral IS NULL
               OR situacao_cadastral IN ('ativa', 'baixada', 'inapta', 'suspensa', 'nula')),
    data_situacao_cadastral  DATE,
    motivo_situacao          TEXT,
    -- 🔴 NO `uf` / ADDRESS COLUMNS (owner decision, 2026-09-24, twice-
    -- confirmed): every state certidão this product issues is SP
    -- regardless of the empresa's UF, so it would be reference-only with
    -- no process it feeds — AND Crednet's "Participação Societária UF"
    -- column is not even the EMPRESA's registered UF (it is printed beside
    -- the participation, not the company record), so it is not a
    -- trustworthy source for one either. The raw value still travels —
    -- inside `cliente_documentos.extracao_crednet` JSONB, exactly as
    -- Crednet printed it — just never promoted to a semantic column here.
    --
    -- Group provenance for every field above — see this migration's header
    -- for why this is ONE quintet, not one per field.
    dados_origem             TEXT,
    dados_documento_id       UUID,
    dados_em                 TIMESTAMPTZ,
    dados_confirmado_por     UUID,
    dados_confirmado_em      TIMESTAMPTZ,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ,

    CONSTRAINT uq_sw_empresas_org_cnpj UNIQUE (org_id, cnpj)
);

COMMENT ON TABLE social_wiring.empresas IS
    'A company (PJ) one or more clientes participate in — Serasa Crednet '
    '(automated), Cartão CNPJ (manual/machine) or a manual link (migration '
    '167). One row per (org, cnpj); `cliente_empresa_participacoes` is the '
    'join to the people who own it.';
COMMENT ON COLUMN social_wiring.empresas.dados_origem IS
    'serasa_crednet | cartao_cnpj | manual | certidao_consulta (backfill) — '
    'who wrote the GROUP of cadastral fields. Machine-pending iff origem <> '
    'manual AND dados_confirmado_em IS NULL (migration 167).';

CREATE INDEX IF NOT EXISTS idx_sw_empresas_org
    ON social_wiring.empresas (org_id);

ALTER TABLE social_wiring.empresas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "empresas_select_own_org" ON social_wiring.empresas;
CREATE POLICY "empresas_select_own_org" ON social_wiring.empresas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "empresas_service_role" ON social_wiring.empresas;
CREATE POLICY "empresas_service_role" ON social_wiring.empresas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. cliente_empresa_participacoes — the join: who owns which empresa
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cliente_empresa_participacoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    cliente_id          UUID NOT NULL
        REFERENCES social_wiring.clientes (id) ON DELETE CASCADE,
    empresa_id          UUID NOT NULL
        REFERENCES social_wiring.empresas (id) ON DELETE CASCADE,
    participacao_pct    NUMERIC(5, 2)
        CHECK (participacao_pct IS NULL
               OR (participacao_pct >= 0 AND participacao_pct <= 100)),
    desde               TEXT,
    fonte_documento_id  UUID
        REFERENCES social_wiring.cliente_documentos (id) ON DELETE SET NULL,
    origem              TEXT NOT NULL
        CHECK (origem IN ('serasa_crednet', 'manual', 'certidao_consulta')),
    confirmado_por      UUID,
    confirmado_em       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_sw_cliente_empresa_participacoes UNIQUE (cliente_id, empresa_id)
);

COMMENT ON TABLE social_wiring.cliente_empresa_participacoes IS
    'One row per (cliente, empresa) — this cliente participates in this '
    'company. `origem` names how the link was made; a Crednet-sourced link '
    'with a valid check-digit CNPJ is unconfirmed until a human reviews it '
    '(migration 167, contract §H10).';

CREATE INDEX IF NOT EXISTS idx_sw_cliente_empresa_participacoes_empresa
    ON social_wiring.cliente_empresa_participacoes (org_id, empresa_id);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_empresa_participacoes_cliente
    ON social_wiring.cliente_empresa_participacoes (org_id, cliente_id);

ALTER TABLE social_wiring.cliente_empresa_participacoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_empresa_participacoes_select_own_org"
    ON social_wiring.cliente_empresa_participacoes;
CREATE POLICY "cliente_empresa_participacoes_select_own_org"
    ON social_wiring.cliente_empresa_participacoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_empresa_participacoes_service_role"
    ON social_wiring.cliente_empresa_participacoes;
CREATE POLICY "cliente_empresa_participacoes_service_role"
    ON social_wiring.cliente_empresa_participacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. empresa_documentos — the Cartão CNPJ upload, mirroring `imovel_
--    documentos` (075) plus the D1/D3 extraction lifecycle 068/069/072/111
--    gave `cliente_documentos`.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.empresa_documentos (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   UUID NOT NULL,
    empresa_id               UUID NOT NULL
        REFERENCES social_wiring.empresas (id) ON DELETE CASCADE,
    storage_path             TEXT NOT NULL,
    nome_original            TEXT NOT NULL,
    mime_type                TEXT NOT NULL,
    tamanho_bytes            BIGINT NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_documento           TEXT NOT NULL CHECK (tipo_documento IN ('cartao_cnpj')),
    retencao_ate             DATE,

    -- Extraction lifecycle (068:135-149, 072:31) — a Cartão CNPJ read.
    extracao_status          TEXT
        CHECK (extracao_status IS NULL
               OR extracao_status IN ('pendente', 'processando', 'ok', 'sem_dados', 'erro')),
    extracao_em              TIMESTAMPTZ,
    extracao_fonte           TEXT,
    extracao_erro            TEXT,
    extracao_tentativas      INTEGER NOT NULL DEFAULT 0,

    -- Discard (069:53-55) — the reading is kept, the record is just not
    -- offered as a pending suggestion any more.
    extracao_descartada_em   TIMESTAMPTZ,
    extracao_descartada_por  UUID,

    -- The full reading — every `CartaoCnpjFields` value including per-field
    -- confiança/rótulo, so a human can audit the reasoning without
    -- re-opening the document.
    extracao_dados           JSONB,

    enviado_por              UUID,
    deleted_at                TIMESTAMPTZ,
    delete_motivo            TEXT,
    delete_solicitado_por    UUID,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.empresa_documentos IS
    'An empresa''s uploaded documents — today only cartao_cnpj. Mirrors '
    'imovel_documentos (075); DocumentoStore-backed (migration 167).';

-- The background worker's claim path — every Cartão CNPJ not yet read.
CREATE INDEX IF NOT EXISTS idx_sw_empresa_documentos_extracao_pendente
    ON social_wiring.empresa_documentos (extracao_status)
    WHERE deleted_at IS NULL AND extracao_status IN ('pendente', 'processando');
CREATE INDEX IF NOT EXISTS idx_sw_empresa_documentos_empresa
    ON social_wiring.empresa_documentos (org_id, empresa_id, created_at DESC);
-- The retention sweep's read path — every non-deleted document past its
-- retention date, same shape as `cliente_documentos` (057:127).
CREATE INDEX IF NOT EXISTS idx_sw_empresa_documentos_retencao
    ON social_wiring.empresa_documentos (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;

ALTER TABLE social_wiring.empresa_documentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "empresa_documentos_select_own_org"
    ON social_wiring.empresa_documentos;
CREATE POLICY "empresa_documentos_select_own_org"
    ON social_wiring.empresa_documentos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "empresa_documentos_service_role"
    ON social_wiring.empresa_documentos;
CREATE POLICY "empresa_documentos_service_role"
    ON social_wiring.empresa_documentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- The access log — copying `imovel_documento_acessos` (109:115-141), widened
-- with 'extract' the way `cliente_documento_acessos` was (068:145-165): a
-- background extraction opening the file's bytes is still a content read.
CREATE TABLE IF NOT EXISTS social_wiring.empresa_documento_acessos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    documento_id  UUID NOT NULL
        REFERENCES social_wiring.empresa_documentos (id) ON DELETE CASCADE,
    usuario_id    UUID,
    acao          TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete', 'extract')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_empresa_documento_acessos_doc
    ON social_wiring.empresa_documento_acessos (documento_id, created_at DESC);

ALTER TABLE social_wiring.empresa_documento_acessos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "empresa_documento_acessos_select_own_org"
    ON social_wiring.empresa_documento_acessos;
CREATE POLICY "empresa_documento_acessos_select_own_org"
    ON social_wiring.empresa_documento_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "empresa_documento_acessos_service_role"
    ON social_wiring.empresa_documento_acessos;
CREATE POLICY "empresa_documento_acessos_service_role"
    ON social_wiring.empresa_documento_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Deferred FK: `empresas.dados_documento_id` points at a row of the table
-- just created above.
ALTER TABLE social_wiring.empresas
    DROP CONSTRAINT IF EXISTS empresas_dados_documento_fk;
ALTER TABLE social_wiring.empresas
    ADD CONSTRAINT empresas_dados_documento_fk
    FOREIGN KEY (dados_documento_id)
    REFERENCES social_wiring.empresa_documentos (id) ON DELETE SET NULL;

-- ----------------------------------------------------------------------------
-- 4. empresa_campo_conflitos — copies `imovel_campo_conflitos` (154), keyed
--    by `empresa_id` (contract §H6: shares its OPEN/dedupe/notify mechanics
--    with `cliente_campo_conflitos` (138) and `imovel_campo_conflitos`
--    through a common writer, formalized in this slice).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.empresa_campo_conflitos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    empresa_id             UUID NOT NULL
        REFERENCES social_wiring.empresas (id) ON DELETE CASCADE,

    -- The `empresas` field in conflict — 'razao_social', 'nome_fantasia', ...
    campo                  TEXT NOT NULL,

    -- PERMANENT snapshot at detection — the way back, same contract as 138.
    valor_anterior         JSONB,
    origem_anterior        TEXT,

    valor_proposto         JSONB NOT NULL,
    origem_proposto        TEXT NOT NULL,
    documento_id_proposto  UUID,
    confianca_proposta     TEXT,

    -- Polymorphic source pointer — same reasoning 138/154 gave: a
    -- conflict can be raised by `cliente_documentos` (Crednet) or
    -- `empresa_documentos` (Cartão CNPJ), so a single-target FK cannot
    -- express it.
    fonte_tabela           TEXT,
    fonte_id               UUID,

    status                 TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aceito', 'rejeitado')),
    notificado_em          TIMESTAMPTZ,
    decidido_por           UUID,
    decidido_em            TIMESTAMPTZ,

    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.empresa_campo_conflitos IS
    'One row per empresas field where a machine reading (Serasa Crednet / '
    'Cartão CNPJ) disagreed with a value already there (migration 167, '
    'owner decision D1/§H6). Never auto-resolved. See cliente_campo_'
    'conflitos (138) / imovel_campo_conflitos (154) — same shape, same '
    'shared writer.';

CREATE INDEX IF NOT EXISTS idx_sw_empresa_campo_conflitos_empresa
    ON social_wiring.empresa_campo_conflitos (org_id, empresa_id);
CREATE INDEX IF NOT EXISTS idx_sw_empresa_campo_conflitos_pendentes
    ON social_wiring.empresa_campo_conflitos (org_id, created_at DESC)
    WHERE status = 'pendente';

-- One open conflict per (empresa, campo) — same rule as 138/154.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_empresa_campo_conflitos_aberto
    ON social_wiring.empresa_campo_conflitos (empresa_id, campo)
    WHERE status = 'pendente';

ALTER TABLE social_wiring.empresa_campo_conflitos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "empresa_campo_conflitos_select_own_org"
    ON social_wiring.empresa_campo_conflitos;
CREATE POLICY "empresa_campo_conflitos_select_own_org"
    ON social_wiring.empresa_campo_conflitos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "empresa_campo_conflitos_service_role"
    ON social_wiring.empresa_campo_conflitos;
CREATE POLICY "empresa_campo_conflitos_service_role"
    ON social_wiring.empresa_campo_conflitos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 5. certidao_consultas / certidao_resultados — the empresa link + the
--    Crednet -> certidão 9 provenance (contract §E7)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_consultas
    ADD COLUMN IF NOT EXISTS empresa_id UUID
        REFERENCES social_wiring.empresas (id) ON DELETE SET NULL;

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_empresa_tipo_check;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_empresa_tipo_check
    CHECK (empresa_id IS NULL OR tipo_documento = 'cnpj');

CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_empresa
    ON social_wiring.certidao_consultas (org_id, empresa_id)
    WHERE excluida_em IS NULL;

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS fonte_cliente_documento_id UUID
        REFERENCES social_wiring.cliente_documentos (id) ON DELETE SET NULL;

COMMENT ON COLUMN social_wiring.certidao_resultados.fonte_cliente_documento_id IS
    'The cliente_documentos row (a Serasa Crednet upload) this resultado''s '
    'serasa reading was auto-filled from, when it was — NULL for every '
    'other origin (api/ia/manual). Set to NULL by the FK on an LGPD delete '
    'of that document; NOC-REMEDIATE[crednet-lgpd-delete-cascade] in '
    '`certidoes/service.py` tracks the dangling `arquivo_url` that leaves '
    'behind (migration 167, contract §H5).';

-- ----------------------------------------------------------------------------
-- 6. clientes.nome_mae — the Crednet-read mother's name, D1 quintet
--    (068's data_nascimento shape)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS nome_mae                TEXT,
    ADD COLUMN IF NOT EXISTS nome_mae_origem          TEXT,
    ADD COLUMN IF NOT EXISTS nome_mae_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS nome_mae_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nome_mae_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS nome_mae_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.nome_mae_origem IS
    'manual | serasa_crednet — who wrote nome_mae. Machine-pending iff '
    'origem <> manual AND nome_mae_confirmado_em IS NULL (migration 167, '
    'same D1 contract as data_nascimento — 068).';

-- ----------------------------------------------------------------------------
-- 7. cliente_documentos — the Crednet reading, D1-shaped like every other
--    extracted field, plus the whole reading (extracao_crednet, mirroring
--    extracao_conjuges — 153:120)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_nome_mae            TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nome_mae_confianca  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nome_mae_rotulo     TEXT,
    ADD COLUMN IF NOT EXISTS extracao_crednet             JSONB;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_crednet IS
    'The whole Serasa Crednet reading (CrednetFields, JSON-serialized) — '
    'protocolo, ocorrências, participações (valid AND rejected), the '
    'computed ocorrencias_constam() verdict. Mirrors extracao_conjuges '
    '(153:120) — held on the document because the document IS the '
    'provenance (migration 167).';

-- ----------------------------------------------------------------------------
-- 8. Document types and retention
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('serasa_crednet', 'financeiro', 1825, false, true,
     'Serasa Crednet — relatório de crédito (PF)')
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        retencao_dias  = EXCLUDED.retencao_dias,
        identidade     = EXCLUDED.identidade,
        ativo          = true,
        descricao      = EXCLUDED.descricao;

-- The `documento_retencao_politicas` allow-list (079/111) gains 'empresa' as
-- a surface.
ALTER TABLE social_wiring.documento_retencao_politicas
    DROP CONSTRAINT IF EXISTS documento_retencao_politicas_superficie_check;
ALTER TABLE social_wiring.documento_retencao_politicas
    ADD CONSTRAINT documento_retencao_politicas_superficie_check
    CHECK (superficie IN ('cliente', 'atendimento', 'imovel', 'empresa'));

INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'cliente', 'serasa_crednet', 1825,
     'Relatório de crédito — mesma retenção de identidade/financeiro. LGPD (migration 167).'),
    (NULL, 'empresa', 'cartao_cnpj', 1825,
     'Cartão CNPJ — retenção de 5 anos, mesma política de identidade (migration 167).')
ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 9. Backfill — every non-deleted CNPJ consulta gets an empresa row
--    (idempotent, no deletes; situação is NOT copied — see this migration's
--    header and contract §H4)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.empresas (org_id, cnpj, razao_social, dados_origem)
SELECT DISTINCT ON (c.org_id, norm.cnpj_norm)
    c.org_id,
    norm.cnpj_norm,
    c.nome,
    'certidao_consulta'
FROM social_wiring.certidao_consultas c
CROSS JOIN LATERAL (
    SELECT upper(regexp_replace(c.documento, '[.\-/\s]', '', 'g')) AS cnpj_norm
) norm
WHERE c.tipo_documento = 'cnpj'
  AND c.excluida_em IS NULL
  AND norm.cnpj_norm ~ '^[0-9A-Z]{14}$'
ORDER BY c.org_id, norm.cnpj_norm, c.created_at
ON CONFLICT (org_id, cnpj) DO NOTHING;

-- Malformed CNPJs (documento does not normalize to 14 chars) are skipped
-- above and reported here, once, as a NOTICE with a count — never a silent
-- drop.
DO $$
DECLARE
    v_count INT;
BEGIN
    SELECT count(*) INTO v_count
    FROM social_wiring.certidao_consultas c
    WHERE c.tipo_documento = 'cnpj'
      AND c.excluida_em IS NULL
      AND upper(regexp_replace(c.documento, '[.\-/\s]', '', 'g')) !~ '^[0-9A-Z]{14}$';
    IF v_count > 0 THEN
        RAISE NOTICE
            'migration 167 backfill: % cnpj consulta(s) had a malformed '
            'documento and were skipped (no empresas row, no link)', v_count;
    END IF;
END $$;

UPDATE social_wiring.certidao_consultas c
SET empresa_id = e.id
FROM social_wiring.empresas e
WHERE c.tipo_documento = 'cnpj'
  AND c.excluida_em IS NULL
  AND c.empresa_id IS NULL
  AND e.org_id = c.org_id
  AND e.cnpj = upper(regexp_replace(c.documento, '[.\-/\s]', '', 'g'));

INSERT INTO social_wiring.cliente_empresa_participacoes
    (org_id, cliente_id, empresa_id, origem)
SELECT DISTINCT c.org_id, c.cliente_id, c.empresa_id, 'certidao_consulta'
FROM social_wiring.certidao_consultas c
WHERE c.tipo_documento = 'cnpj'
  AND c.excluida_em IS NULL
  AND c.empresa_id IS NOT NULL
  AND c.cliente_id IS NOT NULL
ON CONFLICT (cliente_id, empresa_id) DO NOTHING;

NOTIFY pgrst, 'reload schema';
