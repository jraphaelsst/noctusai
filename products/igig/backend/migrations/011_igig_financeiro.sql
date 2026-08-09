-- ============================================================================
-- IgIg — Financeiro e Gestão de Contratos (Módulo 6)
--
--   fatura      — one monthly invoice per contract. `competencia` is the month
--                 being billed ('2026-08'), NOT the due date: a September
--                 invoice for August work must reconcile against August's
--                 delivery count, and conflating the two makes excedentes
--                 impossible to audit.
--   fatura_item — the invoice's lines. Excedentes land here as their own line
--                 so a client can see WHY the amount differs from the retainer.
--
-- SQLite mirror: migrations/sqlite/011_financeiro.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE IF NOT EXISTS igig.fatura (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    cliente_id     UUID NOT NULL REFERENCES igig.cliente (id) ON DELETE CASCADE,
    contrato_id    UUID REFERENCES igig.contrato (id) ON DELETE SET NULL,
    -- 'YYYY-MM' — the month being billed.
    competencia    TEXT NOT NULL,
    valor_total    NUMERIC(12, 2) NOT NULL DEFAULT 0,
    vencimento     DATE,
    status         TEXT NOT NULL DEFAULT 'aberta'
                   CHECK (status IN ('aberta', 'enviada', 'paga', 'vencida', 'cancelada')),
    pago_em        TIMESTAMPTZ,
    -- Gateway/NFS-e handles. Nullable until each integration is homologated.
    gateway_id     TEXT,
    nfse_id        TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_fatura_org ON igig.fatura (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_fatura_cliente ON igig.fatura (org_id, cliente_id);
-- One invoice per contract per month. Re-running the monthly close must be
-- idempotent, not a way to double-bill a client.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_fatura_competencia
    ON igig.fatura (org_id, contrato_id, competencia)
    WHERE contrato_id IS NOT NULL AND status <> 'cancelada';

CREATE TABLE IF NOT EXISTS igig.fatura_item (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    fatura_id   UUID NOT NULL REFERENCES igig.fatura (id) ON DELETE CASCADE,
    descricao   TEXT NOT NULL,
    tipo        TEXT NOT NULL DEFAULT 'mensalidade'
                CHECK (tipo IN ('mensalidade', 'excedente', 'desconto', 'avulso')),
    quantidade  INTEGER NOT NULL DEFAULT 1,
    valor_unit  NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_fatura_item_org ON igig.fatura_item (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_fatura_item_fatura ON igig.fatura_item (org_id, fatura_id);

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['fatura', 'fatura_item']
    LOOP
        EXECUTE format('ALTER TABLE igig.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', t || '_org_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON igig.%I FOR ALL TO authenticated '
            'USING (org_id = public.current_org_id()) '
            'WITH CHECK (org_id = public.current_org_id())',
            t || '_org_isolation', t
        );
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON igig.%I', 'trg_' || t || '_updated_at', t);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON igig.%I '
            'FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at()',
            'trg_' || t || '_updated_at', t
        );
    END LOOP;
END $$;
