-- ============================================================================
-- Migration 171 · social_wiring: negociação/financiamento document
-- extraction (D1/D2/D3) — S2 slice
--
-- Contract: `project-history/roadmaps/sw-negociacao-extracao-contract.md`
-- §C. Adds the extraction lifecycle to `atendimento_documentos` (the 167
-- empresa_documentos set), widens `atendimento_documento_acessos.acao`,
-- and adds D1 provenance to `atendimento_negociacao.valor_negociado`,
-- `atendimento_negociacao_parcelas` (row-level, plus `valor` becomes
-- nullable so a D2 reject can empty it without deleting the row),
-- `atendimento_financiamento` (fgts / numero_proposta / agente_financeiro),
-- and `atendimento_favorecidos` (H5: a Quadro-Resumo-sourced seller credit
-- account). A new `atendimento_campo_conflitos` table is the fourth
-- `*_campo_conflitos` surface (cliente 138, imóvel 154, empresa 167) — same
-- shape, same shared writer (`app.services.campo_conflitos`).
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead's go-ahead. See
-- `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_documentos — the 167 empresa_documentos extraction set
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_documentos
    ADD COLUMN IF NOT EXISTS extracao_status          TEXT,
    ADD COLUMN IF NOT EXISTS extracao_em               TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extracao_fonte            TEXT,
    ADD COLUMN IF NOT EXISTS extracao_erro             TEXT,
    ADD COLUMN IF NOT EXISTS extracao_tentativas       INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extracao_descartada_em    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extracao_descartada_por   UUID,
    -- The full reading — every parsed field, including per-field
    -- confiança/rótulo, so a human can audit the reasoning without
    -- re-opening the document. Mirrors `empresa_documentos.extracao_dados`
    -- (167).
    ADD COLUMN IF NOT EXISTS extracao_dados             JSONB,
    -- A non-fatal warning surfaced ALONGSIDE `extracao_status='ok'` — e.g.
    -- `documento_de_outro_negocio`, `quadro_resumo_soma_divergente`,
    -- `agente_financeiro_nao_cadastrado`, `varias_parcelas_financiamento`.
    -- Distinct from `extracao_erro`, which is a FAILED read.
    ADD COLUMN IF NOT EXISTS extracao_aviso             TEXT;

ALTER TABLE social_wiring.atendimento_documentos
    DROP CONSTRAINT IF EXISTS atendimento_documentos_extracao_status_check;
ALTER TABLE social_wiring.atendimento_documentos
    ADD CONSTRAINT atendimento_documentos_extracao_status_check
    CHECK (extracao_status IS NULL
           OR extracao_status IN ('pendente', 'processando', 'ok', 'sem_dados', 'erro'));

COMMENT ON COLUMN social_wiring.atendimento_documentos.extracao_status IS
    'NULL for a tipo_documento with no extractor (comprovante_itbi — archive '
    'only). pendente | processando | ok | sem_dados | erro for the four '
    'extractable negociação/financiamento tipos (migration 171, contract '
    '§A/§E2).';
COMMENT ON COLUMN social_wiring.atendimento_documentos.extracao_aviso IS
    'A non-fatal advisory alongside a terminal status — e.g. '
    '''documento_de_outro_negocio'', ''quadro_resumo_soma_divergente'', '
    '''agente_financeiro_nao_cadastrado'', ''varias_parcelas_financiamento''. '
    'Never blocks the apply; every field it touches is simply left untouched.';

-- The background worker's claim path — every negociação/financiamento
-- document not yet read. Same shape as `empresa_documentos` (167).
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_documentos_extracao_pendente
    ON social_wiring.atendimento_documentos (extracao_status)
    WHERE deleted_at IS NULL AND extracao_status IN ('pendente', 'processando');

-- ----------------------------------------------------------------------------
-- 2. atendimento_documento_acessos — widen `acao` with 'extract' (as 109 did
--    for `imovel_documento_acessos`, 068 for `cliente_documento_acessos`)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_documento_acessos
    DROP CONSTRAINT IF EXISTS atendimento_documento_acessos_acao_check;
ALTER TABLE social_wiring.atendimento_documento_acessos
    ADD CONSTRAINT atendimento_documento_acessos_acao_check
    CHECK (acao IN ('view', 'download', 'delete', 'extract'));

-- ----------------------------------------------------------------------------
-- 3. atendimento_negociacao — the valor_negociado D1 quintet
--    (owner H2: no authoritative document; ANY disagreement — between
--    documents, or with an existing value — is a conflict for a human)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_negociacao
    ADD COLUMN IF NOT EXISTS valor_negociado_origem          TEXT,
    ADD COLUMN IF NOT EXISTS valor_negociado_documento_id     UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS valor_negociado_em               TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS valor_negociado_confirmado_por   UUID,
    ADD COLUMN IF NOT EXISTS valor_negociado_confirmado_em    TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.atendimento_negociacao.valor_negociado_origem IS
    'manual | guia_itbi | proposta_financiamento | contrato_financiamento | '
    'derivado — who wrote the CURRENT valor_negociado. Machine-pending iff '
    'origem <> ''manual'' AND valor_negociado_confirmado_em IS NULL '
    '(migration 171, owner H2: no source is authoritative — any disagreement '
    'is a conflict, never an overwrite).';

-- ----------------------------------------------------------------------------
-- 4. atendimento_negociacao_parcelas — row-level D1 provenance, and `valor`
--    becomes nullable (a D2 reject empties the value columns; a machine-
--    created parcela must survive that with a NULL valor rather than being
--    deleted — see the contract's §C.4 rationale)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD COLUMN IF NOT EXISTS origem           TEXT,
    ADD COLUMN IF NOT EXISTS documento_id     UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS extraido_em      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmado_por   UUID,
    ADD COLUMN IF NOT EXISTS confirmado_em    TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.atendimento_negociacao_parcelas.origem IS
    'manual | guia_itbi | proposta_financiamento | contrato_financiamento | '
    'derivado (H4: a suggested ''intermediária = valor − sinal − Σ '
    'financiamento'') — NULL for every parcela created before migration 171. '
    'Machine-pending iff origem NOT IN (NULL, ''manual'') AND confirmado_em '
    'IS NULL.';

ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ALTER COLUMN valor DROP NOT NULL;

ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_parcelas_valor_check;
ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD CONSTRAINT atendimento_negociacao_parcelas_valor_check
    CHECK (valor IS NULL OR valor >= 0);

COMMENT ON COLUMN social_wiring.atendimento_negociacao_parcelas.valor IS
    'Nullable since migration 171: a D2 reject on a machine-sourced parcela '
    'empties this column rather than deleting the row. `derivacao.py` '
    'already treats `valor IS NULL` as falta. The manual create/update API '
    '(negociacao_estruturada_service) keeps REQUIRING a value on write — '
    'only the extraction/D2-reject path leaves it NULL.';

-- ----------------------------------------------------------------------------
-- 5. atendimento_financiamento — situacao / fgts / numero_proposta /
--    agente_financeiro D1 quintets (153 shape)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_financiamento
    -- H6 (owner, binding): a signed contrato_financiamento sets `situacao=
    -- 'aprovado'` — "with a provenance quintet". Only TWO new columns:
    -- `situacao_em`/`situacao_por` already existed (078) and are stamped on
    -- EVERY situacao change (manual or machine); duplicating them as
    -- `situacao_confirmado_em`/`_confirmado_por` would be redundant next to
    -- a column that already means "when this situacao was set". `situacao`
    -- is NOT a member of `atendimento_campo_conflitos.campo`'s vocabulary
    -- (contract §C.6) — it is a one-way `pendente -> aprovado` transition
    -- applied directly, never something a human "disagrees" with a machine
    -- about the way a valor does.
    ADD COLUMN IF NOT EXISTS situacao_origem                 TEXT,
    ADD COLUMN IF NOT EXISTS situacao_documento_id           UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS situacao_confirmado_por         UUID,
    ADD COLUMN IF NOT EXISTS situacao_confirmado_em          TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS fgts_origem                    TEXT,
    ADD COLUMN IF NOT EXISTS fgts_documento_id               UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS fgts_em                         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fgts_confirmado_por             UUID,
    ADD COLUMN IF NOT EXISTS fgts_confirmado_em              TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS numero_proposta_origem          TEXT,
    ADD COLUMN IF NOT EXISTS numero_proposta_documento_id    UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS numero_proposta_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS numero_proposta_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS numero_proposta_confirmado_em   TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS agente_financeiro_origem         TEXT,
    ADD COLUMN IF NOT EXISTS agente_financeiro_documento_id   UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS agente_financeiro_em             TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS agente_financeiro_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS agente_financeiro_confirmado_em  TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.atendimento_financiamento.fgts_origem IS
    'manual | contrato_financiamento — `fgts_origem IS NULL` is what "unset" '
    'means (migration 171): the underlying column is a NOT NULL boolean '
    'whose `false` is otherwise indistinguishable from "never asked". '
    'Machine-pending iff fgts_origem = ''contrato_financiamento'' AND '
    'fgts_confirmado_em IS NULL.';
COMMENT ON COLUMN social_wiring.atendimento_financiamento.agente_financeiro_origem IS
    'manual | contrato_financiamento | proposta_financiamento. Fill-empty '
    'lookup by `codigo_banco` only — see `agentes_financeiros`; H7 auto-'
    'creates the registry row when none matches.';

-- ----------------------------------------------------------------------------
-- 6. atendimento_favorecidos — H5 provenance (the Quadro Resumo's seller
--    credit account, matched to a vendedor by CPF)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_favorecidos
    ADD COLUMN IF NOT EXISTS origem            TEXT,
    ADD COLUMN IF NOT EXISTS documento_id      UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS extraido_em       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmado_por    UUID,
    ADD COLUMN IF NOT EXISTS confirmado_em     TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.atendimento_favorecidos.origem IS
    'manual | contrato_financiamento — NULL for a favorecido typed before '
    'migration 171 or created by hand. H5: the Quadro Resumo''s printed '
    'seller credit account fills (never overwrites) a favorecido matched to '
    'a vendedor by CPF.';

-- ----------------------------------------------------------------------------
-- 7. atendimento_campo_conflitos — the fourth `*_campo_conflitos` surface
--    (cliente 138, imóvel 154, empresa 167) — same shape, shared writer
--    (`app.services.campo_conflitos`, contract §E5.4/§I)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_campo_conflitos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    atendimento_id         UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,

    -- 'valor_negociado' | 'parcela.<id>.valor' | 'financiamento.fgts' |
    -- 'financiamento.numero_proposta' | 'financiamento.agente_financeiro_id'.
    campo                  TEXT NOT NULL,

    -- PERMANENT snapshot at detection — the way back, same contract as
    -- 138/154/167.
    valor_anterior         JSONB,
    origem_anterior        TEXT,

    valor_proposto         JSONB NOT NULL,
    origem_proposto        TEXT NOT NULL,
    documento_id_proposto  UUID
        REFERENCES social_wiring.atendimento_documentos (id) ON DELETE SET NULL,
    confianca_proposta     TEXT,

    -- Polymorphic source pointer — a conflict can be raised by a
    -- `guia_itbi` / `proposta_financiamento` / `contrato_financiamento`
    -- reading (all `atendimento_documentos`), or by a cross-document check
    -- against another already-extracted document of the same deal.
    fonte_tabela           TEXT,
    fonte_id               UUID,

    status                 TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aceito', 'rejeitado')),
    notificado_em          TIMESTAMPTZ,
    decidido_por           UUID,
    decidido_em            TIMESTAMPTZ,

    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.atendimento_campo_conflitos IS
    'One row per atendimento_negociacao/atendimento_negociacao_parcelas/'
    'atendimento_financiamento field where a machine reading disagreed with '
    'a value already there (migration 171, owner H2/D1). Never auto-'
    'resolved. Fourth `*_campo_conflitos` surface — same shape, same shared '
    'writer as cliente_campo_conflitos (138) / imovel_campo_conflitos (154) '
    '/ empresa_campo_conflitos (167).';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_campo_conflitos_atendimento
    ON social_wiring.atendimento_campo_conflitos (org_id, atendimento_id);
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_campo_conflitos_pendentes
    ON social_wiring.atendimento_campo_conflitos (org_id, created_at DESC)
    WHERE status = 'pendente';

-- One open conflict per (atendimento, campo) — same rule as 138/154/167.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimento_campo_conflitos_aberto
    ON social_wiring.atendimento_campo_conflitos (atendimento_id, campo)
    WHERE status = 'pendente';

ALTER TABLE social_wiring.atendimento_campo_conflitos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_campo_conflitos_select_own_org"
    ON social_wiring.atendimento_campo_conflitos;
CREATE POLICY "atendimento_campo_conflitos_select_own_org"
    ON social_wiring.atendimento_campo_conflitos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_campo_conflitos_service_role"
    ON social_wiring.atendimento_campo_conflitos;
CREATE POLICY "atendimento_campo_conflitos_service_role"
    ON social_wiring.atendimento_campo_conflitos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 8. agentes_financeiros — H7 (owner, binding): auto-create is distinct
--    from a person registering a bank by hand, and the FE needs to render
--    that distinction (FE consumer note, 2026-09-25 — S3 done).
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.agentes_financeiros
    ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'manual'
        CHECK (origem IN ('manual', 'auto'));

COMMENT ON COLUMN social_wiring.agentes_financeiros.origem IS
    '''manual'' (the Settings page) | ''auto'' (H7: negociacao_extracao_'
    'service auto-created this row for a bank code no active registry '
    'entry matched). Migration 171.';

-- ----------------------------------------------------------------------------
-- 9. Retention — the four new tipo_documento values on the `atendimento`
--    surface (H9: the 079 precedent — financeiro 730 days; escritura/pacto
--    3650). `guia_itbi`/`proposta_financiamento`/`contrato_financiamento`
--    are read for extraction; `comprovante_itbi` is archive-only (H10) but
--    still needs a retention policy row like every other atendimento
--    document type.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'atendimento', 'guia_itbi', 730,
     'Guia de ITBI — retenção financeira (5 anos seria excessivo; segue o '
     'precedente financeiro da migration 079). Contract §H9.'),
    (NULL, 'atendimento', 'comprovante_itbi', 730,
     'Comprovante de pagamento do ITBI — arquivo apenas, sem extração '
     '(contract §H10). Mesma retenção financeira da guia.'),
    (NULL, 'atendimento', 'proposta_financiamento', 730,
     'Proposta de financiamento — retenção financeira (migration 079 '
     'precedente). Contract §H9.'),
    (NULL, 'atendimento', 'contrato_financiamento', 730,
     'Contrato de financiamento imobiliário — retenção financeira '
     '(migration 079 precedente). Contract §H9.')
ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING;

NOTIFY pgrst, 'reload schema';
