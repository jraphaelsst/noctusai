-- ============================================================================
-- 193 — contract generator: party qualification + non-payment clauses
--       (anuente, PJ party, pacto antenupcial, RNE/RNM, ônus já quitado,
--        free-text obligations reviewed by the legal review)
-- ============================================================================
--
-- WHY
-- ---
-- The office's signed contracts (redacted corpus catalog, 34 CCV texts) carry
-- party shapes and clauses the generator could not express. Each column below
-- is the storage one of them needs; the wording lives in
-- `card_hub/contrato_gerador/frases.py`, the gate in `derivacao.py`.
--
-- clientes
-- --------
-- `identidade_tipo` — which identity document `rg`/`rg_orgao_expedidor` hold:
--     NULL/'rg' (the cédula de identidade every Brazilian party has), 'rne' or
--     'rnm' (a FOREIGN party's Registro Nacional de Estrangeiro / Migratório —
--     3 signed deals). The qualification prints "cédula de identidade RNE
--     <n> <órgão>" instead of "RG <n>-<órgão>". NULL reads as 'rg' — every row
--     written before this column existed IS an RG.
-- `pacto_antenupcial_data` / `_tabelionato` / `_livro` / `_folha` — the
--     escritura de pacto antenupcial a married couple's qualification cites
--     (corpus deal 858: "conforme escritura de pacto antenupcial, lavrada aos
--     <data>, pelo <tabelionato>, no Livro nº <livro>, Página nº <folha>").
--     Stored on EACH spouse's row (the extraction of a pacto document writes
--     both); the generator refuses two spouses whose pacto data disagree.
--     Required by the gate when the regime needs a pacto (separação
--     convencional, comunhão universal on/after Lei 6.515/77, participação
--     final nos aquestos). The pacto's own REGISTRO is not cited in any signed
--     contract, so it has no column here. Filled by the pacto reader
--     (`pacto_antenupcial_service`) through the D1 path, each column with its
--     own provenance quintet (`_origem/_documento_id/_em/_confirmado_por/
--     _confirmado_em`).
--
-- atendimento_partes
-- ------------------
-- `pj_nire`, `pj_sede_*` — a COMPANY party's qualification (corpus deal 866:
--     "<razão social>, pessoa jurídica de direito privado, devidamente
--     inscrita sob CNPJ nº <cnpj> e NIRE <nire>, com sede na <endereço>").
--     DEAL-scoped on the party row, not on `empresas`: migration 167 keeps
--     `empresas` free of address columns by owner decision (twice confirmed),
--     and the contract is the one process that needs a sede. Only meaningful
--     on a PJ party (CHECK).
-- `representa_parte_id` — a PERSON party (papel 'representante') who signs
--     for a PJ party of the SAME atendimento ("representada neste ato por sua
--     sócia e administradora <qualificação>"). Points at the PJ party's row
--     (whose `empresa_id` names the company). Only on a PF party (CHECK);
--     ON DELETE SET NULL — removing the company party leaves a representante
--     with nobody to represent, which the gate names.
--
-- atendimento_negociacao_termos
-- -----------------------------
-- `onus_baixa_protocolo_em` — `onus_quitacao = 'ja_quitado'`: the date the
--     seller filed the baixa request at the Registro de Imóveis (corpus deal
--     867: "protocolou, em <data>, junto ao Registro de Imóveis de <cidade>,
--     o requerimento de baixa da Alienação Fiduciária registrada sob o
--     R-<n>"). Required by the gate for that quitação, ignored otherwise.
--
-- atendimento_contrato_versoes
-- ----------------------------
-- `revisao_juridica_itens` JSONB NOT NULL DEFAULT '[]' — wording the legal
--     review must read with particular care, recorded on the version it was
--     printed in: operator-typed free paragraphs printed verbatim
--     (`obrigacoes_vendedor`, `permuta_obrigacoes_entrega`) and wording
--     derived from a single signed contract (PJ party). One object per item
--     `{codigo, titulo, texto}`. Separate from `revisao_juridica_campos`
--     (177): those are machine-extracted VALUES the approval confirms on their
--     own rows; these are TEXT with no row to confirm.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — apply via `noctus.dev.migrate_product` after the
-- tech-lead's go-ahead; record it in `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- clientes -------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS identidade_tipo TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_data DATE,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_tabelionato TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_livro TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_folha TEXT;

-- The house provenance quintet per pacto column (068 → 153): the pacto
-- reader (`pacto_antenupcial_service`, migration 191's document type) writes
-- these through the SAME D1 path as every identity field (fill empty
-- machine-pending; a different value is a conflict, never an overwrite), a
-- hand edit stamps `_origem='manual'`, and the contract's legal review
-- confirms them like any other extracted value.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_data_origem TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_data_documento_id UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_data_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_data_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_data_confirmado_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_tabelionato_origem TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_tabelionato_documento_id UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_tabelionato_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_tabelionato_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_tabelionato_confirmado_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_livro_origem TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_livro_documento_id UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_livro_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_livro_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_livro_confirmado_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_folha_origem TEXT,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_folha_documento_id UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_folha_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_folha_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS pacto_antenupcial_folha_confirmado_em TIMESTAMPTZ;

DO $chk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'clientes_identidade_tipo_valido'
    ) THEN
        ALTER TABLE social_wiring.clientes
            ADD CONSTRAINT clientes_identidade_tipo_valido
            CHECK (identidade_tipo IS NULL OR identidade_tipo IN ('rg', 'rne', 'rnm'));
    END IF;
END
$chk$;

COMMENT ON COLUMN social_wiring.clientes.identidade_tipo IS
    'Which identity document rg/rg_orgao_expedidor hold: NULL/rg (cédula de '
    'identidade), rne/rnm (foreign party). Migration 193.';
COMMENT ON COLUMN social_wiring.clientes.pacto_antenupcial_data IS
    'Escritura de pacto antenupcial cited in the contract qualification '
    '(with _tabelionato/_livro/_folha). Migration 193.';

-- atendimento_partes ---------------------------------------------------------
ALTER TABLE social_wiring.atendimento_partes
    ADD COLUMN IF NOT EXISTS pj_nire TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_logradouro TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_numero TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_complemento TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_bairro TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_cidade TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_uf TEXT,
    ADD COLUMN IF NOT EXISTS pj_sede_cep TEXT,
    ADD COLUMN IF NOT EXISTS representa_parte_id UUID
        REFERENCES social_wiring.atendimento_partes (id) ON DELETE SET NULL;

DO $chk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'atendimento_partes_pj_campos_so_em_pj'
    ) THEN
        ALTER TABLE social_wiring.atendimento_partes
            ADD CONSTRAINT atendimento_partes_pj_campos_so_em_pj
            CHECK (
                empresa_id IS NOT NULL
                OR num_nonnulls(
                    pj_nire, pj_sede_logradouro, pj_sede_numero, pj_sede_complemento,
                    pj_sede_bairro, pj_sede_cidade, pj_sede_uf, pj_sede_cep
                ) = 0
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'atendimento_partes_representa_so_pf'
    ) THEN
        ALTER TABLE social_wiring.atendimento_partes
            ADD CONSTRAINT atendimento_partes_representa_so_pf
            CHECK (representa_parte_id IS NULL OR cliente_id IS NOT NULL);
    END IF;
END
$chk$;

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_partes_representa
    ON social_wiring.atendimento_partes (representa_parte_id)
    WHERE representa_parte_id IS NOT NULL;

COMMENT ON COLUMN social_wiring.atendimento_partes.representa_parte_id IS
    'The PJ party (same atendimento) this person signs for, as representante. '
    'Migration 193.';
COMMENT ON COLUMN social_wiring.atendimento_partes.pj_nire IS
    'NIRE of a PJ party, printed in its contract qualification (with '
    'pj_sede_*). Migration 193.';

-- atendimento_negociacao_termos ---------------------------------------------
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD COLUMN IF NOT EXISTS onus_baixa_protocolo_em DATE;

COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.onus_baixa_protocolo_em IS
    'onus_quitacao = ja_quitado: date the baixa request was filed at the '
    'Registro de Imóveis. Migration 193.';

-- atendimento_contrato_versoes ----------------------------------------------
ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD COLUMN IF NOT EXISTS revisao_juridica_itens JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.revisao_juridica_itens IS
    'Wording the final legal review must read with care ({codigo, titulo, '
    'texto}): verbatim operator paragraphs, single-contract-derived wording. '
    'Migration 193.';

NOTIFY pgrst, 'reload schema';
