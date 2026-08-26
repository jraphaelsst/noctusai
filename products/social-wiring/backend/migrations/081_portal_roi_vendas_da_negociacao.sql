-- ============================================================================
-- Migration 081 · social_wiring: the ROI screen learns to read the funnel
--
-- 🔴 THE PROBLEM, MEASURED IN PRODUCTION ON 2026-08-25
-- -----------------------------------------------------
-- `ROI por Portal` showed 13.379 leads, 0 vendas, no investimento, no ROI.
-- Not a rendering bug — `lead_vendas` and `lead_campanhas` were BOTH literally
-- empty (0 rows each). The agency's most repeated money question — which
-- portal pays for itself — had no answer anywhere in the platform.
--
-- The reason nobody filled `lead_vendas` is that it is a second place to type
-- a sale that has already been recorded once, in the funnel, by the person who
-- closed it. A data-entry surface that duplicates work nobody asked for stays
-- empty; that is not a discipline problem, it is a design one.
--
-- Migration 077 fixed the missing half without knowing it: `atendimento_
-- negociacao.valor_negociado` is the sale's value, captured where the deal
-- actually happens. This view now reads it.
--
-- ATTRIBUTION PATH
-- ----------------
--   atendimento_negociacao → atendimentos.lead_id → leads.origem_id
--
-- An atendimento with no `lead_id`, or a lead with no `origem_id`, contributes
-- NOTHING rather than landing in a catch-all bucket. A sale attributed to the
-- wrong portal is worse than a sale attributed to none: the first corrupts the
-- comparison the screen exists to make, the second only understates a row.
--
-- WHAT COUNTS AS A SALE
-- ---------------------
-- `status = 'aceita' AND closed_at IS NOT NULL`. That pair is set in exactly
-- one place in the codebase (`pipeline/routers/boards.py`, on accepting the
-- deal), and migration 034's CHECK refuses a closed status without a
-- `closed_at` — so this is the system's own definition of a won deal, not a
-- new one invented here. An open negociação with a value typed into it is a
-- forecast, not a sale, and is deliberately excluded.
--
-- 🔴 THE TWO SOURCES MUST STAY DISJOINT
-- --------------------------------------
-- Vendas is now `lead_vendas` + funnel sales, summed. There is no shared key
-- between them, so a deal entered in BOTH would be counted twice and nothing
-- here can detect it. That is safe today (`lead_vendas` is empty) and stays
-- safe as long as `lead_vendas` keeps its documented purpose from 043: sales
-- with no funnel record. It is kept rather than dropped precisely because that
-- case is real — a walk-in with no lead row still counts toward a channel.
-- If a manual-entry UI for `lead_vendas` is ever built, it has to refuse an
-- atendimento that already has a negociação, and this comment is the reason.
--
-- FORWARD-ONLY, IDEMPOTENT. CREATE OR REPLACE VIEW only — no table touched,
-- no column added, no row migrated.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE OR REPLACE VIEW social_wiring.vw_portal_roi AS
SELECT
    s.org_id,
    s.id                                   AS origem_id,
    s.slug,
    s.label,
    s.categoria,
    -- 047: bare, no COALESCE. NULL = no lead_campanhas row covers this portal
    -- in ANY period ("unrecorded"). 0.00 = a row exists and says the spend was
    -- zero ("recorded zero"). Different facts; the API needs both.
    c.investimento                         AS investimento,
    COALESCE(l.total_leads, 0)             AS total_leads,
    COALESCE(v.total_vendas, 0)            AS total_vendas,
    COALESCE(v.valor_vendas, 0)            AS valor_vendas,
    c.investimento / NULLIF(COALESCE(l.total_leads, 0), 0)               AS cpl,
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
    -- The two disjoint sources, summed. See the header before adding a third.
    SELECT org_id, origem_id,
           SUM(total_vendas)::BIGINT AS total_vendas,
           SUM(valor_vendas)         AS valor_vendas
    FROM (
        -- (a) manually recorded sales — 043's off-funnel path.
        SELECT org_id, origem_id,
               COUNT(*)::BIGINT AS total_vendas,
               SUM(valor)       AS valor_vendas
        FROM social_wiring.lead_vendas
        GROUP BY org_id, origem_id

        UNION ALL

        -- (b) won deals, straight out of the funnel (081).
        SELECT a.org_id,
               ld.origem_id,
               COUNT(*)::BIGINT           AS total_vendas,
               SUM(n.valor_negociado)     AS valor_vendas
        FROM social_wiring.atendimento_negociacao n
        JOIN social_wiring.atendimentos a
          ON a.id = n.atendimento_id
        JOIN social_wiring.leads ld
          ON ld.id = a.lead_id AND ld.org_id = a.org_id
        WHERE a.status = 'aceita'
          AND a.closed_at IS NOT NULL
          AND n.valor_negociado IS NOT NULL
          AND ld.origem_id IS NOT NULL
        GROUP BY a.org_id, ld.origem_id
    ) fontes
    GROUP BY org_id, origem_id
) v ON v.org_id = s.org_id AND v.origem_id = s.id;

COMMENT ON VIEW social_wiring.vw_portal_roi IS
    'ROI per lead source. Vendas = manually recorded lead_vendas (043) PLUS '
    'won atendimentos carrying an atendimento_negociacao value (081), '
    'attributed through atendimentos.lead_id → leads.origem_id. The two '
    'sources must stay disjoint — see migration 081''s header.';
