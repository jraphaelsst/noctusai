-- ============================================================================
-- Migration · social_wiring: `atendimento_propostas` — a proposta is an
-- OFFER SNAPSHOT (project sw-lead-to-contract, CONTRACT.md §4.1)
-- ============================================================================
-- WHY
-- ---
-- An atendimento can hold several propostas at once (competing imóveis,
-- counter-offers) and each keeps its own terms even after another is accepted.
-- The contract generator, however, reads ONE live negotiation set keyed by
-- `atendimento_id` (atendimento_negociacao + _termos + _parcelas + _favorecidos
-- + _intermediarios). Duplicating those five tables per proposta would fork
-- the negotiation model, so a proposta stores its terms as validated JSON
-- snapshots (the SAME Pydantic shapes negociacao_estruturada_service validates)
-- and ACCEPTING materializes the chosen snapshot into the live set through the
-- existing writers. The generator stays single-source and unchanged.
--
-- `parcelas[].favorecido_ref` ("fav:0") and `termos.posse_marco_parcela_ref`
-- are client-side keys into the snapshot, resolved to real ids on materialize.
--
-- FORWARD-ONLY, IDEMPOTENT. Touches no existing row.
-- ============================================================================

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

CREATE TABLE IF NOT EXISTS social_wiring.atendimento_propostas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL
        REFERENCES public.organizations (id) ON DELETE CASCADE,
    atendimento_id   UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,
    cliente_id       UUID NOT NULL,
    visita_id        UUID NULL
        REFERENCES social_wiring.visitas (id) ON DELETE SET NULL,
    imovel_codigo    TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'rascunho',
    valor_proposto   NUMERIC(14, 2) NULL,
    pct_comissao     NUMERIC NULL,
    financiamento    BOOLEAN NULL,
    fgts             BOOLEAN NULL,
    validade_ate     DATE NULL,
    observacoes      TEXT NULL,
    parcelas         JSONB NOT NULL DEFAULT '[]'::jsonb,
    favorecidos      JSONB NOT NULL DEFAULT '[]'::jsonb,
    intermediarios   JSONB NOT NULL DEFAULT '[]'::jsonb,
    termos           JSONB NOT NULL DEFAULT '{}'::jsonb,
    imobiliaria_id   UUID NULL
        REFERENCES social_wiring.org_imobiliarias (id) ON DELETE RESTRICT,
    testemunha_ids   UUID[] NOT NULL DEFAULT '{}',
    enviada_em       TIMESTAMPTZ NULL,
    aceita_em        TIMESTAMPTZ NULL,
    aceita_por       UUID NULL,
    recusada_em      TIMESTAMPTZ NULL,
    recusada_por     UUID NULL,
    motivo_recusa    TEXT NULL,
    contrato_id      UUID NULL
        REFERENCES social_wiring.atendimento_contratos (id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por      UUID NULL,
    updated_at       TIMESTAMPTZ NULL,
    updated_por      UUID NULL,

    CONSTRAINT atendimento_propostas_status_valido
        CHECK (status IN ('rascunho', 'enviada', 'aceita', 'recusada', 'cancelada')),
    CONSTRAINT atendimento_propostas_valor_positivo
        CHECK (valor_proposto IS NULL OR valor_proposto > 0)
);

COMMENT ON TABLE social_wiring.atendimento_propostas IS
    'Migration atendimento_propostas — an offer SNAPSHOT of an atendimento (sw-lead-to-contract '
    'CONTRACT §4.1). Terms live as validated JSON; Aceitar materializes them '
    'into the live negotiation set the contract generator reads.';

-- One ACCEPTED proposta per atendimento (the live negotiation set holds one
-- imóvel and one set of terms).
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimento_propostas_uma_aceita
    ON social_wiring.atendimento_propostas (atendimento_id)
    WHERE status = 'aceita';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_propostas_atendimento
    ON social_wiring.atendimento_propostas (atendimento_id);

-- RLS — org-picker shape (migration 211)
ALTER TABLE social_wiring.atendimento_propostas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_propostas_select_own_org" ON social_wiring.atendimento_propostas;
CREATE POLICY "atendimento_propostas_select_own_org"
    ON social_wiring.atendimento_propostas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "atendimento_propostas_write_own_org" ON social_wiring.atendimento_propostas;
CREATE POLICY "atendimento_propostas_write_own_org"
    ON social_wiring.atendimento_propostas
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "atendimento_propostas_service_role" ON social_wiring.atendimento_propostas;
CREATE POLICY "atendimento_propostas_service_role"
    ON social_wiring.atendimento_propostas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Acting-audit trigger for the new table (migration 214, idempotent).
SELECT public.attach_acting_audit_triggers('social_wiring');

NOTIFY pgrst, 'reload schema';
