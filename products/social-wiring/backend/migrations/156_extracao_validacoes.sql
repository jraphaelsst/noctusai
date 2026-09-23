-- ============================================================================
-- 156 — extracao_validacoes: the human validation ledger for machine-extracted
--       contract data (roadmap sw-extraction-contract-gate-2026-09, owner
--       decision D2)
-- ============================================================================
--
-- WHY
-- ---
-- Owner decision D2 (2026-09-22): clicking "Gerar contrato" opens a modal that
-- lists every contract-feeding value that came from a MACHINE (a document
-- extraction, the certidões API, the matrícula reader) and that no human has
-- vouched for yet. Each value is accepted (✓) or rejected (✗). The backend
-- refuses to generate while any such value is pending — the modal is the UI,
-- `contrato_gerador.service.gerar` is the gate.
--
-- The value's own row carries the CURRENT state (its `<campo>_confirmado_por/
-- _em` after an accept; NULL value + NULL provenance after a reject). What the
-- entity row cannot carry is the HISTORY: which reading a human threw away, off
-- which document, at what confidence. That is exactly the signal the extractor
-- needs to be refined, and it is gone the moment a reject nulls the value.
-- This table is that history — one append-only row per decision.
--
-- SHAPE (the roadmap's "Shared field-state contract", verbatim)
-- ------------------------------------------------------------
-- `entidade`  — which kind of row the value lives on: 'cliente' | 'imovel' |
--               'imovel_documento' | 'certidao' | 'ato_detalhe'. TEXT, not a
--               CHECK: the registry that decides this lives in code
--               (`contrato_gerador.validacao_extracao.REGISTRO`) and a new
--               contract-feeding source must not need a migration to log.
-- `entidade_id` — TEXT, because `imovel_dados` is keyed by `(org_id, codigo)`
--               and has no uuid of its own.
-- `campo`     — the registry field (a column, or a group name such as
--               'endereco' / 'certidao' when several columns are ONE reading).
-- `valor_extraido` — the machine's value AS IT WAS when the human decided,
--               rendered to text (a group renders as JSON). Kept even on an
--               accept: "what did we accept" is part of the refinement signal.
-- `origem` / `fonte_documento_id` / `confianca` — copied off the value's own
--               provenance at decision time (a reject erases them there).
-- `contrato_id` — the contract whose generation prompted the decision. SET
--               NULL on the contract's hard delete: the extraction signal
--               outlives the contract.
--
-- Append-only by convention (no UPDATE path in code). RLS: own-org SELECT for
-- `authenticated`, full access for `service_role` — same pair as 138.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — apply via `noctus.dev.migrate_product` after the
-- tech-lead's go-ahead; record it in `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.extracao_validacoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    contrato_id         UUID
        REFERENCES social_wiring.atendimento_contratos(id) ON DELETE SET NULL,

    entidade            TEXT NOT NULL,
    entidade_id         TEXT NOT NULL,
    campo               TEXT NOT NULL,

    valor_extraido      TEXT,
    origem              TEXT,
    fonte_documento_id  UUID,
    confianca           TEXT,

    decisao             TEXT NOT NULL
        CHECK (decisao IN ('aceito', 'rejeitado')),
    decidido_por        UUID,
    decidido_em         TIMESTAMPTZ NOT NULL DEFAULT now(),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.extracao_validacoes IS
    'Append-only ledger of human accept/reject decisions on machine-extracted '
    'contract-feeding values (migration 156, owner decision D2). The entity '
    'row keeps the current state; this keeps what was decided about which '
    'reading — the extractor-refinement signal a reject would otherwise erase.';
COMMENT ON COLUMN social_wiring.extracao_validacoes.entidade IS
    'cliente | imovel | imovel_documento | certidao | ato_detalhe — see '
    'contrato_gerador.validacao_extracao.REGISTRO.';
COMMENT ON COLUMN social_wiring.extracao_validacoes.entidade_id IS
    'The row id (uuid as text) — or the imóvel codigo for entidade=imovel, '
    'whose imovel_dados row is keyed by (org_id, codigo).';
COMMENT ON COLUMN social_wiring.extracao_validacoes.valor_extraido IS
    'The machine value at decision time, as text (a multi-column group as '
    'JSON). Kept on accept too.';

CREATE INDEX IF NOT EXISTS idx_sw_extracao_validacoes_org_created
    ON social_wiring.extracao_validacoes (org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sw_extracao_validacoes_contrato
    ON social_wiring.extracao_validacoes (contrato_id)
    WHERE contrato_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_extracao_validacoes_campo
    ON social_wiring.extracao_validacoes (org_id, entidade, campo, decisao);

ALTER TABLE social_wiring.extracao_validacoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "extracao_validacoes_select_own_org"
    ON social_wiring.extracao_validacoes;
CREATE POLICY "extracao_validacoes_select_own_org"
    ON social_wiring.extracao_validacoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "extracao_validacoes_service_role"
    ON social_wiring.extracao_validacoes;
CREATE POLICY "extracao_validacoes_service_role"
    ON social_wiring.extracao_validacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
