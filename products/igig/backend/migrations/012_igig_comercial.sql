-- ============================================================================
-- IgIg — CRM, Orçamentos e Onboarding (Módulo 1)
--
--   lead      — the public pré-qualificação form's landing table. Deliberately
--               NOT `cliente`: a lead is unqualified, arrives from an
--               unauthenticated form, and most never become clients. Mixing
--               them would pollute every client-scoped report in the product.
--   orcamento — a proposal. Stores BOTH the calculator's suggested minimum and
--               the price actually sent, because the spec explicitly allows a
--               director to override, and the gap between the two is the
--               discount the agency granted — a number worth keeping.
--
-- `contrato` gains the document/signature columns here rather than in 006:
-- forward migration, never an edit to one already applied.
--
-- SQLite mirror: migrations/sqlite/012_comercial.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE IF NOT EXISTS igig.lead (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    nome           TEXT NOT NULL,
    email          TEXT,
    telefone       TEXT,
    empresa        TEXT,
    nicho          TEXT,
    canais_atuais  TEXT,
    dores          TEXT,
    orcamento_disponivel NUMERIC(12, 2),
    origem         TEXT,
    status         TEXT NOT NULL DEFAULT 'novo'
                   CHECK (status IN ('novo', 'qualificado', 'descartado', 'convertido')),
    -- Set when the lead becomes a cliente, so the funnel is auditable.
    cliente_id     UUID REFERENCES igig.cliente (id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_lead_org ON igig.lead (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_lead_status ON igig.lead (org_id, status);

CREATE TABLE IF NOT EXISTS igig.orcamento (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    lead_id           UUID REFERENCES igig.lead (id) ON DELETE SET NULL,
    cliente_id        UUID REFERENCES igig.cliente (id) ON DELETE CASCADE,
    titulo            TEXT NOT NULL,
    -- The escopo the calculator priced: [{formato, quantidade, horas_estimadas}]
    escopo            JSONB NOT NULL DEFAULT '[]'::jsonb,
    horas_estimadas   NUMERIC(10, 2) NOT NULL DEFAULT 0,
    custo_estimado    NUMERIC(12, 2) NOT NULL DEFAULT 0,
    -- What the calculator says is the floor, given cost + margin.
    preco_sugerido    NUMERIC(12, 2) NOT NULL DEFAULT 0,
    -- What a director actually decided to charge. The spec allows overriding
    -- the suggestion; keeping both makes the concession visible.
    preco_final       NUMERIC(12, 2),
    margem_alvo       NUMERIC(5, 2) NOT NULL DEFAULT 50,
    status            TEXT NOT NULL DEFAULT 'rascunho'
                      CHECK (status IN ('rascunho', 'enviado', 'aceito', 'recusado')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_orcamento_org ON igig.orcamento (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_orcamento_lead ON igig.orcamento (org_id, lead_id);

-- ── contrato: documento + assinatura ────────────────────────────────
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS orcamento_id UUID
    REFERENCES igig.orcamento (id) ON DELETE SET NULL;
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS documento_key TEXT;
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS provedor_assinatura TEXT;
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS assinatura_external_id TEXT;
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS link_assinatura TEXT;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['lead', 'orcamento']
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
