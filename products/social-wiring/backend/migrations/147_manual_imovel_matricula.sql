-- ============================================================================
-- Migration 147 · social_wiring: manual paths for the contract gate's inputs
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- `contrato_gerador.derivacao.avaliar` (the contract readiness gate) refuses
-- to generate a contract unless the imóvel's address, matrícula acts, título
-- aquisitivo and última transferência all resolve. Every one of those, until
-- now, could ONLY come from the Vista mirror (address) or an AI-transcribed
-- matrícula PDF (everything else) — there was no way to type the data in and
-- test the gate end to end. This migration adds the schema for both manual
-- paths; the code changes (dados_service, estrutura_service, titulo_service,
-- carregador, the routers) ship alongside it in the same change.
--
-- 1. `imovel_dados` GAINS A MANUAL OVERRIDE FOR THE 4 ADDRESS FIELDS THE GATE
--    READS (logradouro/número/cidade/UF)
-- -----------------------------------------------------------------------
-- `derivacao._imovel` reads `im.endereco.{logradouro,numero,cidade,uf}`,
-- which `carregador._imovel` fills straight from `busca_service.enriquecer`
-- — the Vista/registry mirror. This product has no write-back to that mirror
-- (`EditPlaceholderButton` in the FE header is the honest admission of that —
-- Vista rejects every write route). The override lives on `imovel_dados`
-- (data we author) instead, wins PER-FIELD over the mirror when set
-- (`dados_service.gravar_endereco_manual` / `carregador._endereco_imovel`),
-- and is logged: the mirror is external, synced data, not an official
-- document, so a human overriding it needs no admin approval — but the
-- override DOES need a trail, so `imovel_endereco_historico` records the
-- previous effective value + who + when on every change (table #2 below).
--
-- Mirrors `endereco_registro_texto`'s (139) confirmation-stamp shape:
-- `endereco_manual_confirmado_por` / `_em` name who set the CURRENT set of
-- override values, not a per-field stamp — same posture 139 already takes
-- for the single confirmed-address-phrase column.
--
-- 2. `imovel_endereco_historico` — one row per FIELD-LEVEL address override
-- -----------------------------------------------------------------------
-- Append-only, mirroring the platform's other audit-log tables
-- (`matricula_documento_acessos`'s `detalhes_view`/`text_view` actions):
-- readers never write it directly, `dados_service.gravar_endereco_manual` is
-- the only writer. `campo` is the mirror-facing name (`logradouro`, not
-- `endereco_manual_logradouro`) so the log reads the same vocabulary the FE
-- and `Endereco` dataclass already use.
--
-- 3. `matricula_extracoes.origem` — 'upload' | 'manual'
-- -----------------------------------------------------------------------
-- Until now every row came from a PDF (upload or the standalone-arquivo
-- shape, migration 135). A manual transcription — an operator typing or
-- pasting the matrícula's own text — is a THIRD source, and it needs a
-- column for the same reason `numero_matricula_origem` (075) and
-- `titulo_aquisitivo_fonte.origem` (109) exist: a reader must be able to
-- tell a human's typed text apart from a machine's read of a PDF, visibly,
-- not by inferring it from the absence of `imovel_documento_id`/
-- `arquivo_origem_id` (which a pre-135 row could ALSO lack, for an unrelated
-- reason). DEFAULT 'upload' backfills every existing row correctly — every
-- row that exists today came from a PDF.
--
-- 🔴 A manual row runs through the EXACT SAME finalisation
-- (`estrutura_service.persistir_atos`, migration 109/115/136/137's act
-- segmentation, detail suggestion, and qualification suggestion pipelines)
-- an AI transcription's text goes through — see `service.
-- registrar_transcricao_manual`. Nothing downstream (`titulo_service`,
-- `contrato_gerador`) needs to know or care which source populated
-- `texto_extraido`; `origem` exists for the OPERATOR's transparency, not to
-- branch behaviour.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_dados — manual address override (logradouro/número/cidade/UF)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS endereco_manual_logradouro      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_manual_numero          TEXT,
    ADD COLUMN IF NOT EXISTS endereco_manual_cidade          TEXT,
    ADD COLUMN IF NOT EXISTS endereco_manual_uf              TEXT,
    ADD COLUMN IF NOT EXISTS endereco_manual_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS endereco_manual_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.endereco_manual_logradouro IS
    'Manual override for the CRM/Vista mirror''s logradouro (migration 147) '
    '-- this product has no write-back to Vista, so this is the only way to '
    'correct/supply it. Wins over the mirror per-field when set '
    '(carregador._endereco_imovel). NULL falls back to the mirror.';
COMMENT ON COLUMN social_wiring.imovel_dados.endereco_manual_confirmado_por IS
    'Who set the CURRENT override values (any of the 4 fields) -- a single '
    'stamp for the whole override, mirroring endereco_registro_texto''s '
    '(139) shape, not one stamp per field.';

-- ----------------------------------------------------------------------------
-- 2. imovel_endereco_historico -- one row per field-level override
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.imovel_endereco_historico (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    codigo         TEXT NOT NULL,

    -- The mirror-facing field name ('logradouro' | 'numero' | 'cidade' |
    -- 'uf'), not the imovel_dados column name.
    campo          TEXT NOT NULL CHECK (campo IN ('logradouro', 'numero', 'cidade', 'uf')),

    -- The value in effect immediately BEFORE this change (the previous
    -- override, or -- the first time a field is overridden -- the mirror's
    -- own value at that moment, supplied by the caller). NULL is a real
    -- value here (there was nothing before), not "unknown".
    valor_anterior TEXT,
    valor_novo     TEXT,

    alterado_por   UUID,
    alterado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.imovel_endereco_historico IS
    'Append-only log of every manual address-field override (migration 147) '
    '-- the mirror is external/synced data so an override needs no admin '
    'approval, but does need a trail: previous value + who + when. Written '
    'ONLY by dados_service.gravar_endereco_manual.';

CREATE INDEX IF NOT EXISTS idx_sw_imovel_endereco_historico_imovel
    ON social_wiring.imovel_endereco_historico (org_id, codigo, alterado_em DESC);

ALTER TABLE social_wiring.imovel_endereco_historico ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_endereco_historico_select_own_org"
    ON social_wiring.imovel_endereco_historico;
CREATE POLICY "imovel_endereco_historico_select_own_org"
    ON social_wiring.imovel_endereco_historico
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_endereco_historico_write_own_org"
    ON social_wiring.imovel_endereco_historico;
CREATE POLICY "imovel_endereco_historico_write_own_org"
    ON social_wiring.imovel_endereco_historico
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_endereco_historico_service_role"
    ON social_wiring.imovel_endereco_historico;
CREATE POLICY "imovel_endereco_historico_service_role"
    ON social_wiring.imovel_endereco_historico
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. matricula_extracoes.origem -- 'upload' | 'manual'
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'upload';

ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_origem_valida;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_origem_valida
    CHECK (origem IN ('upload', 'manual'));

COMMENT ON COLUMN social_wiring.matricula_extracoes.origem IS
    '''upload'' (a PDF, linked or standalone -- every row before migration '
    '147) | ''manual'' (an operator typed/pasted the matrícula text -- no '
    'PDF, no vision AI). Both run through the SAME act-segmentation pipeline '
    '(estrutura_service.persistir_atos) once texto_extraido exists -- see '
    'service.registrar_transcricao_manual.';
