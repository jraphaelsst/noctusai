-- 047_portal_roi_view_null_investimento.sql — stop `vw_portal_roi` lying
-- about spend it never recorded.
--
-- Fires `portal-roi-PROJECT.md` §2. `043_lead_campanhas_vendas.sql` shipped
-- `vw_portal_roi` with `cpl = COALESCE(c.investimento, 0) / NULLIF(...)`.
-- The `NULLIF` guarded the DENOMINATOR ("no leads yet" reads as unknown,
-- not a cpl of zero) but the NUMERATOR was still `COALESCE(investimento,
-- 0)` — so a portal with 3 728 leads and zero recorded spend computed
-- `0 / 3728 = 0.00` and rendered as "this portal costs R$ 0,00 per lead".
-- The truth is "we have never recorded what it costs". Live at authoring
-- time: 23 of 24 portals have leads, 0 of 24 have any spend recorded — this
-- was not an edge case, it was the default read on every row that mattered.
--
-- ── The actual bug, precisely ───────────────────────────────────────────
-- `c.investimento` (the per-origem SUM from the `lead_campanhas` subquery)
-- is NULL exactly when NO `lead_campanhas` row exists for that origem
-- (LEFT JOIN, no matching group — SUM over zero grouped rows produces no
-- group at all) and a real, possibly-zero NUMERIC whenever at least one
-- row exists (`investimento NOT NULL DEFAULT 0`, so SUM over existing rows
-- is never itself NULL). That NULL is exactly the "unrecorded" signal the
-- contract needs — `COALESCE(c.investimento, 0)` was destroying it before
-- either the raw column OR `cpl` ever saw it. SQL division already
-- propagates NULL correctly (`NULL / x = NULL`); the fix is to stop
-- masking the NULL with COALESCE, not to add another NULLIF layer on top
-- of one. `NULLIF(COALESCE(c.investimento, 0), 0)` (what the roadmap doc
-- sketched as the mechanical fix) was considered and REJECTED: it would
-- ALSO turn an explicit, deliberately-entered "R$ 0,00" row into `NULL`,
-- destroying a genuine fact ("this portal really costs nothing, we
-- checked") to fix a different one ("we never checked"). Those are not
-- the same fact and must not collapse to the same NULL.
--
-- ── Per-column verdict ───────────────────────────────────────────────────
--
-- `investimento` (raw): was `COALESCE(c.investimento, 0)`, now bare
-- `c.investimento`. This is the column the API layer (`portal_roi_service.
-- py`) reads to decide `null` vs `0` in the JSON contract — masking it here
-- makes the distinction unrecoverable one layer up, no matter how careful
-- the service code is.
--
-- `cpl`: numerator changed from `COALESCE(c.investimento, 0)` to bare
-- `c.investimento`. NULL investimento -> NULL cpl (unrecorded, unknown).
-- Zero investimento (a real row saying "R$ 0,00") with leads > 0 -> cpl =
-- 0.00 (a genuine, provable cost-per-lead of zero — NOT the same claim as
-- "unknown"). Denominator NULLIF is untouched (unaffected by this bug).
--
-- `roi`: ✅ ALREADY CORRECT, NOT TOUCHED. `NULLIF(COALESCE(c.investimento,
-- 0), 0)` is the DENOMINATOR here, not the numerator — dividing by zero is
-- undefined whether that zero is "unrecorded" or "genuinely zero spend",
-- so collapsing both to a NULL denominator is the right call in THIS
-- position (unlike `cpl`, where investimento is the numerator and a real
-- zero is a valid, distinct answer). The existing `COALESCE(...,0)` +
-- `NULLIF(...,0)` pair already produces that NULL for both cases via
-- Postgres's `NULLIF(NULL, 0) = NULL` semantics — no change needed.
--
-- `taxa_conversao`: SQL formula UNCHANGED — this is a documented, accepted
-- limitation, not an oversight. `total_vendas`/`valor_vendas` were already
-- decided (in `043`'s header, restated below) to stay `COALESCE(...,0)`
-- because they are counts of things and zero really is zero — that
-- decision is NOT revisited here. The genuine remaining ambiguity is
-- narrower than it first looks: `lead_campanhas` has an explicit
-- COVERAGE marker (`periodo_inicio`/`periodo_fim` — a row's mere
-- existence proves the operator entered SOMETHING for that portal, in
-- SOME period), so "zero rows anywhere" unambiguously means "never
-- entered". `lead_vendas` has NO equivalent coverage marker — a sale is
-- recorded when it happens, nobody logs a periodic "no sale occurred"
-- row the way `lead_campanhas` lets someone log "R$ 0,00 this month". So
-- "zero `lead_vendas` rows for this origem" cannot, even in principle
-- with the current schema, distinguish "genuinely closed nothing" from
-- "sales tracking isn't in use for this portal" — there is no coverage
-- signal to test. Mirroring the `cpl` fix onto `taxa_conversao`
-- (`NULLIF`-guarding the numerator the same way) was considered and
-- REJECTED: it does not resolve the ambiguity — it just forces every
-- portal with zero recorded sales to read "não informado", including a
-- portal that has been diligently tracked for months and genuinely
-- converts nothing, which is a real, useful fact worth showing. Given
-- `total_vendas` is already decided to be a genuine count, `taxa_conversao`
-- inherits that: a real 0% is reported as 0%, on the honest premise "the
-- best available reading of zero recorded sales is zero sales" until a
-- coverage mechanism for `lead_vendas` (out of scope here) exists to do
-- better. Doubly moot for this launch: B1 ships no `/vendas` write
-- surface at all (§4 slices — only `/campanhas` CRUD), so `lead_vendas`
-- will hold zero rows platform-wide regardless of this column's formula
-- until that surface ships.
--
-- 🔴 MIGRATION FILE ONLY — NOT applied to any DB by this change. This DB is
-- production; there is no separate dev DB. Apply only via
-- `noctus.dev.migrate_product` with explicit tech-lead consent.
--
-- Migration-number collision check performed per `043`'s documented
-- command (`git diff --name-only origin/dev...$b -- ... | grep
-- 'backend/migrations/'` across every local + `origin/*` branch, 2026-08-13):
-- no sibling branch touches `products/social-wiring/backend/migrations/`.
-- `047` is free.
--
-- CREATE OR REPLACE VIEW — forward-only, idempotent, no DDL against any
-- table (no ALTER, no new column, no data migration). Re-running this file
-- any number of times leaves the view in the same state.

SET search_path = social_wiring, public;

CREATE OR REPLACE VIEW social_wiring.vw_portal_roi AS
SELECT
    s.org_id,
    s.id                                   AS origem_id,
    s.slug,
    s.label,
    s.categoria,
    -- 047: bare, no COALESCE. NULL = no lead_campanhas row covers this
    -- portal in ANY period ("unrecorded"). 0.00 = a row exists and says
    -- the spend was zero ("recorded zero"). Those are different facts and
    -- the API layer needs this column intact to tell them apart.
    c.investimento                         AS investimento,
    COALESCE(l.total_leads, 0)             AS total_leads,
    COALESCE(v.total_vendas, 0)            AS total_vendas,
    COALESCE(v.valor_vendas, 0)            AS valor_vendas,
    -- 047: numerator is bare `c.investimento` (was `COALESCE(c.investimento,
    -- 0)`). NULL investimento -> NULL cpl via ordinary SQL null propagation
    -- (no NULLIF needed on this side — the bug was the COALESCE hiding the
    -- NULL, not a missing guard). A genuine recorded R$ 0,00 with leads > 0
    -- still yields a real cpl of 0.00, distinct from "unknown". Denominator
    -- NULLIF is unchanged — "no leads yet" still reads as unknown, not free.
    c.investimento / NULLIF(COALESCE(l.total_leads, 0), 0)               AS cpl,
    -- roi: UNCHANGED. Already correct — see header verdict above.
    COALESCE(v.valor_vendas, 0) / NULLIF(COALESCE(c.investimento, 0), 0) AS roi,
    -- taxa_conversao: UNCHANGED. Documented, accepted limitation — see
    -- header verdict above. Not the same call as cpl's; do not "fix" this
    -- to match cpl without re-reading that reasoning.
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
