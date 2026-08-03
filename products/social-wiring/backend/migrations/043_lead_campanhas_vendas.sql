-- 043_lead_campanhas_vendas.sql — portal ROI: spend, and what it produced
--
-- ⚠️ NUMBERED 043, NOT 041. `041_leads_meta_lead_id.sql` already occupied 041
-- on `dev`, and this file briefly shipped as a duplicate 041 before being
-- renumbered. 042 is claimed by `feat/meta-leadgen-webhook`
-- (`044_meta_webhook_events.sql`, unpushed at the time of writing).
--
-- Reserving a migration number requires checking UNPUSHED sibling branches —
-- `ls migrations/` and `git log origin/dev` both miss them:
--
--     for b in $(git branch --format='%(refname:short)'); do
--       f=$(git diff --name-only origin/dev...$b | grep 'backend/migrations/')
--       [ -n "$f" ] && echo "$b -> $f"
--     done
--
-- Fires trigger T5 of project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md.
-- The user named the requirement directly on 2026-08-03: "*the origem is for
-- me to create statistics based on my marketing portals to evaluate their
-- performances against investments x results*".
--
-- These two tables were DESIGNED, not invented here. `025_leads.sql:269-276`
-- carries them as an explicit deferral:
--
--     -- DEFERRED: vendas / fechamento
--     --   lead_vendas(id, org_id, lead_id?, origem_id, empreendimento,
--     --               unidade, data_venda, valor, corretor_id)
--     -- DEFERRED: campanhas / METRICAS
--     --   lead_campanhas(id, org_id, origem_id, periodo_inicio, periodo_fim,
--     --                  investimento, impressoes, cliques, cpc, leads, cpl,
--     --                  visitas_perfil, custo_visita, engajamento)
--
-- This migration implements that shape. The column list is honoured as
-- written except where noted below.
--
-- ── The analysis this enables ──────────────────────────────────────────
-- Three facts keyed on the SAME dimension (`lead_sources.id`):
--     lead_campanhas  → what a portal COST over a period
--     leads           → how many leads it PRODUCED (leads.origem_id)
--     lead_vendas     → what those leads CLOSED
-- Joined, that is cost-per-lead and return-on-investment per portal, which
-- is the whole point.
--
-- ── Derived metrics are NOT stored ────────────────────────────────────
-- The deferred sketch listed `cpc`, `cpl` and `custo_visita` as columns.
-- They are computed here as GENERATED columns instead: all three are pure
-- functions of other columns in the same row, and a stored copy is a copy
-- that can disagree with its inputs. A partial update that sets
-- `investimento` without recomputing `cpl` is silent, and the number that
-- drives a spend decision is exactly the wrong number to let drift.
--
-- ── `leads` is the fact table; `lead_vendas.lead_id` is NULLABLE ───────
-- Deliberate, and it matches the sketch's `lead_id?`. A sale can close
-- without an attributable lead row (walk-in, an old relationship, a lead
-- that predates the import). Forcing the FK would make those sales
-- unrecordable, which biases every ROI number downward precisely where the
-- portal did NOT help. `origem_id` stays required so the sale is always
-- attributable to SOME channel, including an explicit "indicacao"/"direto".
--
-- RLS mirrors 025_leads.sql: authenticated read via public.current_org_id()
-- (SECURITY DEFINER — never auth.jwt() top-level or user_metadata),
-- service_role ALL for backend writes.
--
-- PREREQUISITE: 025_leads.sql (lead_sources, lead_corretores, leads).
-- Forward-only + idempotent.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ── lead_campanhas — spend + delivery per portal per period ────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_campanhas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    origem_id       UUID NOT NULL
                    REFERENCES social_wiring.lead_sources(id) ON DELETE CASCADE,

    periodo_inicio  DATE NOT NULL,
    periodo_fim     DATE NOT NULL,

    -- What it cost.
    investimento    NUMERIC(14, 2) NOT NULL DEFAULT 0,

    -- What it delivered. Nullable because portals expose different metrics:
    -- a listing portal reports impressions and clicks, Instagram reports
    -- profile visits and engagement, and a 0 would claim "measured zero"
    -- where the truth is "not reported by this channel".
    impressoes      BIGINT,
    cliques         BIGINT,
    leads           INTEGER,
    visitas_perfil  BIGINT,
    engajamento     BIGINT,

    observacoes     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Derived — never stored, so they cannot disagree with their inputs.
    -- NULLIF guards the division: a period with no clicks has no CPC, which
    -- is not the same as a CPC of zero.
    cpc             NUMERIC(14, 2)
                    GENERATED ALWAYS AS (investimento / NULLIF(cliques, 0)) STORED,
    cpl             NUMERIC(14, 2)
                    GENERATED ALWAYS AS (investimento / NULLIF(leads, 0)) STORED,
    custo_visita    NUMERIC(14, 2)
                    GENERATED ALWAYS AS (investimento / NULLIF(visitas_perfil, 0)) STORED,

    CONSTRAINT lead_campanhas_periodo_ordered CHECK (periodo_fim >= periodo_inicio),
    CONSTRAINT lead_campanhas_investimento_non_negative CHECK (investimento >= 0),
    -- One row per portal per period — re-importing a month must UPDATE, not
    -- duplicate, or spend silently doubles and every ROI number halves.
    UNIQUE (org_id, origem_id, periodo_inicio, periodo_fim)
);

ALTER TABLE social_wiring.lead_campanhas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_campanhas_select_own_org" ON social_wiring.lead_campanhas;
CREATE POLICY "lead_campanhas_select_own_org" ON social_wiring.lead_campanhas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_campanhas_service_role" ON social_wiring.lead_campanhas;
CREATE POLICY "lead_campanhas_service_role" ON social_wiring.lead_campanhas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_lead_campanhas_origem_periodo
    ON social_wiring.lead_campanhas (org_id, origem_id, periodo_inicio DESC);

-- ── lead_vendas — what actually closed ─────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_vendas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,

    -- NULLABLE by design — see the header. A sale with no attributable lead
    -- row still counts toward the channel's result.
    lead_id         UUID REFERENCES social_wiring.leads(id) ON DELETE SET NULL,
    origem_id       UUID NOT NULL
                    REFERENCES social_wiring.lead_sources(id) ON DELETE RESTRICT,
    corretor_id     UUID REFERENCES social_wiring.lead_corretores(id) ON DELETE SET NULL,

    -- Free text, matching the deferred sketch. NOT an FK to
    -- social_wiring.imoveis: that table is a mirror of the Vista catalog and
    -- an imóvel can be delisted there after a sale closes, which would
    -- either block the delete or orphan the sale. `codigo_imovel` below is
    -- the soft link for the cases where an ONE-code IS known.
    empreendimento  TEXT,
    unidade         TEXT,
    codigo_imovel   TEXT,

    data_venda      DATE NOT NULL,
    valor           NUMERIC(14, 2) NOT NULL,

    observacoes     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT lead_vendas_valor_positive CHECK (valor > 0)
);

ALTER TABLE social_wiring.lead_vendas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_vendas_select_own_org" ON social_wiring.lead_vendas;
CREATE POLICY "lead_vendas_select_own_org" ON social_wiring.lead_vendas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_vendas_service_role" ON social_wiring.lead_vendas;
CREATE POLICY "lead_vendas_service_role" ON social_wiring.lead_vendas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_lead_vendas_origem_data
    ON social_wiring.lead_vendas (org_id, origem_id, data_venda DESC);
CREATE INDEX IF NOT EXISTS idx_sw_lead_vendas_lead
    ON social_wiring.lead_vendas (org_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_sw_lead_vendas_codigo_imovel
    ON social_wiring.lead_vendas (org_id, codigo_imovel);

-- ── updated_at triggers ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.touch_lead_roi_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lead_campanhas_updated_at ON social_wiring.lead_campanhas;
CREATE TRIGGER trg_lead_campanhas_updated_at
    BEFORE UPDATE ON social_wiring.lead_campanhas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.touch_lead_roi_updated_at();

DROP TRIGGER IF EXISTS trg_lead_vendas_updated_at ON social_wiring.lead_vendas;
CREATE TRIGGER trg_lead_vendas_updated_at
    BEFORE UPDATE ON social_wiring.lead_vendas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.touch_lead_roi_updated_at();

-- ── The ROI view — the actual answer to "investimento x resultado" ─────
-- A view, not a table: every number in it is derived, and a materialized
-- copy would need invalidation on three different write paths.
--
-- LEFT JOINs from lead_sources so a portal with spend but no leads, or
-- leads but no recorded spend, still appears. Dropping to an INNER JOIN
-- would silently hide exactly the portals worth investigating — the ones
-- that cost money and produced nothing.
CREATE OR REPLACE VIEW social_wiring.vw_portal_roi AS
SELECT
    s.org_id,
    s.id                                   AS origem_id,
    s.slug,
    s.label,
    s.categoria,
    COALESCE(c.investimento, 0)            AS investimento,
    COALESCE(l.total_leads, 0)             AS total_leads,
    COALESCE(v.total_vendas, 0)            AS total_vendas,
    COALESCE(v.valor_vendas, 0)            AS valor_vendas,
    -- NULLIF everywhere: "no leads yet" must read as unknown, not as a
    -- cost-per-lead of zero.
    COALESCE(c.investimento, 0) / NULLIF(COALESCE(l.total_leads, 0), 0)  AS cpl,
    COALESCE(v.valor_vendas, 0) / NULLIF(COALESCE(c.investimento, 0), 0) AS roi,
    COALESCE(v.total_vendas, 0)::NUMERIC
        / NULLIF(COALESCE(l.total_leads, 0), 0)                          AS taxa_conversao
FROM social_wiring.lead_sources s
LEFT JOIN (
    SELECT org_id, origem_id, SUM(investimento) AS investimento
    FROM social_wiring.lead_campanhas GROUP BY org_id, origem_id
) c ON c.org_id = s.org_id AND c.origem_id = s.id
LEFT JOIN (
    SELECT org_id, origem_id, COUNT(*) AS total_leads
    FROM social_wiring.leads WHERE origem_id IS NOT NULL
    GROUP BY org_id, origem_id
) l ON l.org_id = s.org_id AND l.origem_id = s.id
LEFT JOIN (
    SELECT org_id, origem_id, COUNT(*) AS total_vendas, SUM(valor) AS valor_vendas
    FROM social_wiring.lead_vendas GROUP BY org_id, origem_id
) v ON v.org_id = s.org_id AND v.origem_id = s.id;

-- ── status_pagina — or the nav link is invisible ───────────────────────
-- Seeded 'desenvolvimento'; the page itself is not built yet (T5 backend +
-- UI are handed off). Flip to 'producao' once it is proven end-to-end.
-- → KB § PATTERNS/frontend/status-pagina-dev-visibility.md
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('portal_roi', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
