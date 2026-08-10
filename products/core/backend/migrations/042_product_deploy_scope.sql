-- 042_product_deploy_scope.sql
--
-- Adds the WORKING-SCOPE axis to the product catalog.
--
-- WHY THIS EXISTS
-- ---------------
-- Until now the admin panel's "Deploy: LIVE/DEV" badge was *derived* — it came
-- from `/api/products/deployment-status`, which probes whether a product's
-- container answers /api/health in whatever environment Core happens to be
-- running in. That is an OBSERVATION of runtime reality, and it is still useful,
-- but it can only ever answer "is it up right now?".
--
-- What the team actually needs is a stored INTENT: a deliberate, human-set guide
-- that answers "which environment do we work this product in?". Those are two
-- different questions, and conflating them means you cannot express "this
-- product is running in prod but we've stopped shipping to prod" — which is
-- exactly the state a wind-down needs.
--
-- THE CONTRACT (the whole point of the column)
--   ativo = true,  deploy_scope = 'live'  → work it in PROD (dev-validate, then promote)
--   ativo = true,  deploy_scope = 'dev'   → work it in DEV only; never reaches prod
--   ativo = false                          → IGNORE the product entirely; do not touch its code
--
-- TWO INVARIANTS, ENFORCED HERE RATHER THAN TRUSTED
--   I1. An INACTIVE product can never be LIVE. Enforced by a CHECK constraint,
--       not by application code, because a guide that can drift into a state the
--       rules forbid is not a guide — and every writer (API, psql, a future
--       job) must obey it, not just the one that happens to go through FastAPI.
--   I2. Reactivation always lands in 'dev'. A product coming back from inactive
--       has not been re-validated in prod, so defaulting it to 'live' would
--       silently re-expose it. The DEFAULT below plus the API's transition logic
--       make 'dev' the only reachable landing state.
--
-- The deactivation path (live → dev → inactive) is a consequence of I1: you
-- cannot go straight from (ativo, live) to (inativo, live), so the API demotes
-- the scope in the SAME statement as the deactivation. One UPDATE, so there is
-- no instant where a row sits in the forbidden combination.

BEGIN;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS deploy_scope text NOT NULL DEFAULT 'dev';

-- Vocabulary guard. Kept separate from the invariant below so a violation names
-- which rule was broken instead of one opaque combined failure.
ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_deploy_scope_valid;
ALTER TABLE public.products
    ADD CONSTRAINT products_deploy_scope_valid
    CHECK (deploy_scope IN ('live', 'dev'));

-- BACKFILL — preserve observed reality, do not invent it.
--
-- Every product that is currently REACHABLE in production is recorded as 'live';
-- everything else stays at the 'dev' column default. The list below is the prod
-- fleet as verified on the VPS on 2026-08-10 (`docker ps`, 15 healthy
-- containers). knowledge-extractor has no container at all and pilates is not
-- running, so both correctly remain 'dev' — which is exactly what the admin
-- panel already showed via the probe, so this migration changes no badge.
--
-- Deliberately NOT keyed off `ativo`: at write time every catalog row is active,
-- so keying off it would mark the un-deployed products 'live' and the first
-- thing an operator saw would be a lie.
UPDATE public.products
   SET deploy_scope = 'live'
 WHERE slug IN (
    'core',
    'erp-imobiliario',
    'social-wiring',
    'orbity',
    'igig',
    'therapy-platform',
    'personal-finance',
    'daily-life',
    'dev-team',
    'adconnect',
    'seed'
 );

-- I1 — added AFTER the backfill so the statement above cannot trip it, and so a
-- pre-existing bad row surfaces as a migration failure rather than being
-- silently skipped by NOT VALID.
ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_inactive_never_live;
ALTER TABLE public.products
    ADD CONSTRAINT products_inactive_never_live
    CHECK (ativo IS NOT FALSE OR deploy_scope = 'dev');

COMMENT ON COLUMN public.products.deploy_scope IS
    'Working scope: live = worked in prod, dev = worked in dev only. Stored '
    'INTENT set by a human, not runtime reachability (that is '
    '/api/products/deployment-status). An inactive product is forced to dev by '
    'the products_inactive_never_live constraint.';

COMMIT;
