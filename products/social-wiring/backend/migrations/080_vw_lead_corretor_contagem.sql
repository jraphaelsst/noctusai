-- ============================================================================
-- Migration 080 · social_wiring: one query for the broker lead counts
--
-- 🔴 MEASURED, NOT SUSPECTED. `GET /api/leads/corretores` was the slowest
-- endpoint in production on 2026-08-25 — 3343ms, 2083ms and 1828ms in a single
-- 25-minute window, three of the twenty slowest requests the container served.
-- Against a p50 of 6.4ms.
--
-- It is also one of the app shell's reference queries, so EVERY page a user
-- opens pays it.
--
-- WHY IT WAS SLOW — AND WHY IT WAS NOT THE DATABASE
-- --------------------------------------------------
-- `dimensions_service.list_corretores_with_lead_count` read the brokers, then
-- issued ONE exact COUNT per broker. Its docstring called that "bounded:
-- brokers are a small dimension" — which is true and was still the wrong
-- conclusion. 29 brokers is 30 SEQUENTIAL PostgREST round trips, and the cost
-- is the round trips, not the counting: `idx_sw_leads_org_corretor` already
-- covers every one of those counts, so each is a fast index scan wrapped in
-- ~100ms of HTTP.
--
-- N+1 over a small N is still N+1. "The dimension is small" bounds the blast
-- radius; it does not make thirty sequential network calls cheap.
--
-- WHAT THIS REPLACES THEM WITH
-- ----------------------------
-- One grouped read. PostgREST cannot GROUP BY, so the grouping lives where
-- grouping belongs — in the database — and the service reads the view with a
-- single `.eq("org_id", ...)`.
--
-- `security_invoker = true`, matching `vw_nome_conferencia` (071): the view
-- must not become a way to read another org's counts, so it runs with the
-- CALLER's rights and `leads`' own RLS still applies. A definer-rights view
-- over an RLS'd table is a quiet hole; this is the house default for a reason.
--
-- LEFT JOIN, not INNER: a broker with zero leads must still appear, with a
-- count of 0. An inner join would silently drop new brokers from the list —
-- the same class of bug as reading a missing row as "no policy".
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE OR REPLACE VIEW social_wiring.vw_lead_corretor_contagem
WITH (security_invoker = true)
AS
SELECT
    c.id      AS corretor_id,
    c.org_id,
    COUNT(l.id) AS lead_count
FROM social_wiring.lead_corretores c
LEFT JOIN social_wiring.leads l
       ON l.corretor_id = c.id
      AND l.org_id      = c.org_id
GROUP BY c.id, c.org_id;

COMMENT ON VIEW social_wiring.vw_lead_corretor_contagem IS
    'Lead count per broker, one row per (org_id, corretor_id), zero included. '
    'Replaces the per-broker COUNT loop in '
    'app/modules/leads/services/dimensions_service.py — 30 sequential '
    'PostgREST round trips became 1.';
