-- 019 -- turn the platform org picker ON for community
--
-- 017 converted every community RLS policy that keyed on the caller's org to the policy-literal helper
-- public.current_org_id_for('community'); 018 attached the acting-write audit triggers; the seed code
-- that reads platform_org_selections is already in prod (social-wiring pilot, 213). Keeper
-- check_org_picker_ready_policies refuses this flip if any community policy still uses a home-only
-- identity form. Reversible: set it back to false (the products trigger from core 070 then ends
-- every live selection, 'revoked').

UPDATE public.products
   SET org_picker_ready = true
 WHERE slug = 'community'
   AND db_schema = 'community';
