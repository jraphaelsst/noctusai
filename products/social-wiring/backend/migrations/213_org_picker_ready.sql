-- 213 — turn the platform org picker ON for social-wiring (pilot, owner 2026-10-08)
--
-- 211 + 212 converted every social_wiring and mailing RLS policy that keyed on the caller's org to
-- the policy-literal helper public.current_org_id_for('social_wiring'); the
-- seed code that reads platform_org_selections shipped in prod 4a5aff5ed
-- (deploy_verify green). Only now may the product accept selections.
-- Keeper check_org_picker_ready_policies refuses this flip if any social_wiring
-- policy still uses a home-only identity form. Reversible: set it back to false
-- (the products trigger from core 070 then ends every live selection, 'revoked').

UPDATE public.products
   SET org_picker_ready = true
 WHERE slug = 'social-wiring'
   AND db_schema = 'social_wiring';
