-- 040 -- turn the platform org picker ON for igig
--
-- 038 converted every igig RLS policy that keyed on the caller's org to the policy-literal helper
-- public.current_org_id_for('igig'); 039 attached the acting-write audit triggers; the seed code
-- that reads platform_org_selections is already in prod (social-wiring pilot, 213). Keeper
-- check_org_picker_ready_policies refuses this flip if any igig policy still uses a home-only
-- identity form. Reversible: set it back to false (the products trigger from core 070 then ends
-- every live selection, 'revoked').

UPDATE public.products
   SET org_picker_ready = true
 WHERE slug = 'igig'
   AND db_schema = 'igig';
