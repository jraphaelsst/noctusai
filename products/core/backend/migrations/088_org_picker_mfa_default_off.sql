-- Migration: 088_org_picker_mfa_default_off
-- Schema: public (core)
--
-- WHY: 073 turned the org-picker 2FA requirement off for every product that existed on
-- 2026-10-09, but left the column DEFAULT at true. Every product registered afterwards came back
-- with 2FA required -- monica (core 087, 2026-10-27) blocked the owner's login into Monica's app.
-- Owner, 2026-10-27: "remove 2fa so i can log into monica's app" -- no fix, no 2FA.
--
-- WHAT: the default becomes false and every product row is false, so a new product can no longer
-- re-introduce the requirement. The prod row for monica was already set false by hand the same day.
-- RESTORE (only on an explicit owner decision): ALTER ... SET DEFAULT true + UPDATE ... SET true.

SET search_path = public, public;

ALTER TABLE public.products ALTER COLUMN org_picker_requires_mfa SET DEFAULT false;

UPDATE public.products SET org_picker_requires_mfa = false WHERE org_picker_requires_mfa;

COMMENT ON COLUMN public.products.org_picker_requires_mfa IS
    'true = platform staff need an aal2 (2FA) session to act in another org through this product''s '
    'org picker. Off fleet-wide by owner decision (core 073, 2026-10-09; default false since core 088, '
    '2026-10-27). Restore only on an explicit owner decision.';
