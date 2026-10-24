-- ============================================================================
-- Migration 306 · social_wiring: imóvel fields typed by hand, never upload-only
-- ============================================================================
-- OWNER DIRECTIVE (2026-10-24): "a field must not be upload-only, we can set
-- them manually." Every imóvel field the system reads off a document must
-- also be typeable by the operator, and a typed value is protected from any
-- later re-read — the same posture as every other `imovel_dados` override
-- (115/139/152): a human's confirmation is never overwritten by a machine.
--
-- 1. `imovel_dados.descricao_imovel_*` — the IMÓVEL: clause override
-- --------------------------------------------------------------------------
-- The contract's OBJETO clause quotes the matrícula abertura's
-- `descricao_imovel` typed block (migration 136). When the transcription
-- has no such block (no `IMÓVEL:` label) or got it wrong, there was no way
-- to type it. Same single-stamp shape as `endereco_registro_texto` (139):
-- the text and its confirmation are set and cleared together. When set it
-- WINS over the derived block in `contrato_gerador.carregador`.
--
-- 2. `imovel_dados.ultima_transferencia_manual_transmitentes`
-- --------------------------------------------------------------------------
-- Migration 152's override answered WHEN (and the nature), never WHO sold.
-- The sellers' names now ride the same override. A list of names alone is a
-- valid override (an act was found but its sellers were not read), so the
-- 152 `_confirmado` stamp CHECK is widened to count a non-empty list as an
-- answer. Names are meaningless next to "não consta transferência
-- registrada" — that combination is refused.
--
-- 3. `imovel_certidoes_manuais` — CND IPTU / CND condomínio / matrícula
--    certidão typed with NO file
-- --------------------------------------------------------------------------
-- Until now these were only editable through `PATCH .../documentos/{id}/
-- extracao`, i.e. after uploading a document. One row per (org, código,
-- tipo); `documentos_service.certidoes` (the read the contract loader uses)
-- takes it when it is NEWER than the newest uploaded document of that tipo,
-- so a later upload naturally supersedes it and a later typing supersedes an
-- upload. A machine read never writes this table. Not a document: nothing
-- here is stored in the bucket, so there is no retention/access-log leg.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead + user consent. See
-- `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. descrição do imóvel override
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS descricao_imovel_texto          TEXT,
    ADD COLUMN IF NOT EXISTS descricao_imovel_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS descricao_imovel_confirmado_em  TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.descricao_imovel_texto IS
    'The IMÓVEL: description (the matrícula abertura''s descricao_imovel '
    'block) as an operator typed/confirmed it (migration 306). When set it '
    'wins over the derived block in the contract''s OBJETO clause; never '
    'written by a machine read.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_descricao_imovel_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_descricao_imovel_confirmado
    CHECK ((descricao_imovel_texto IS NULL) = (descricao_imovel_confirmado_em IS NULL));

-- ----------------------------------------------------------------------------
-- 2. última transferência — the sellers' names
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS ultima_transferencia_manual_transmitentes TEXT[] NOT NULL DEFAULT '{}'::text[];

COMMENT ON COLUMN social_wiring.imovel_dados.ultima_transferencia_manual_transmitentes IS
    'Names of who sold in the last registered transfer, typed by an operator '
    '(migration 306, extends 152''s override). Non-empty wins over the names '
    'read off the matrícula act.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_ult_transf_transmitentes_sem_registro;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_ult_transf_transmitentes_sem_registro
    CHECK (NOT (ultima_transferencia_manual_sem_registro
                AND cardinality(ultima_transferencia_manual_transmitentes) > 0));

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_ultima_transferencia_manual_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_ultima_transferencia_manual_confirmado
    CHECK (
        (ultima_transferencia_manual_data IS NOT NULL
         OR ultima_transferencia_manual_sem_registro
         OR cardinality(ultima_transferencia_manual_transmitentes) > 0)
        = (ultima_transferencia_manual_confirmado_em IS NOT NULL)
    );

-- ----------------------------------------------------------------------------
-- 3. imovel_certidoes_manuais
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.imovel_certidoes_manuais (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    codigo                TEXT NOT NULL,
    tipo                  TEXT NOT NULL,
    numero                TEXT,
    emitida_em            DATE,
    validade_ate          DATE,
    resultado             TEXT,
    inscricao_imobiliaria TEXT,
    confirmado_por        UUID,
    confirmado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT imovel_certidoes_manuais_tipo_valido
        CHECK (tipo IN ('cnd_iptu', 'cnd_condominio', 'matricula')),
    CONSTRAINT imovel_certidoes_manuais_resultado_valido
        CHECK (resultado IS NULL OR resultado IN (
            'negativa', 'positiva', 'positiva_com_efeito_de_negativa')),
    -- Per-tipo field subset — mirrors documentos_service.CAMPOS_ESTRUTURA_POR_TIPO.
    -- Only constrains the tipos it names (tipo validity is `_tipo_valido`'s job).
    CONSTRAINT imovel_certidoes_manuais_campos_por_tipo
        CHECK (
            (tipo <> 'cnd_condominio'
             OR (numero IS NULL AND validade_ate IS NULL AND inscricao_imobiliaria IS NULL))
            AND (tipo <> 'matricula'
             OR (numero IS NULL AND validade_ate IS NULL AND resultado IS NULL
                 AND inscricao_imobiliaria IS NULL))
        ),
    CONSTRAINT imovel_certidoes_manuais_um_por_tipo UNIQUE (org_id, codigo, tipo),
    CONSTRAINT imovel_certidoes_manuais_imovel_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical) ON DELETE CASCADE
);

COMMENT ON TABLE social_wiring.imovel_certidoes_manuais IS
    'Imóvel certidão fields typed with no file (migration 306): one row per '
    '(org, código, tipo). documentos_service.certidoes prefers it over an '
    'uploaded document''s structured read when it is newer. Written only by '
    'documentos_service.gravar_certidao_manual; never by a machine read.';

ALTER TABLE social_wiring.imovel_certidoes_manuais ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_certidoes_manuais_select_own_org"
    ON social_wiring.imovel_certidoes_manuais;
CREATE POLICY "imovel_certidoes_manuais_select_own_org"
    ON social_wiring.imovel_certidoes_manuais
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_certidoes_manuais_service_role"
    ON social_wiring.imovel_certidoes_manuais;
CREATE POLICY "imovel_certidoes_manuais_service_role"
    ON social_wiring.imovel_certidoes_manuais
    FOR ALL TO service_role USING (true) WITH CHECK (true);
