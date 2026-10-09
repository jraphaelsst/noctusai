-- 022 — turn the platform org picker ON for agents (rollout after the social-wiring pilot)
--
-- 020 converted every agents RLS policy that keyed on the caller's home org to the
-- policy-literal helper public.current_org_id_for('agents'); 021 attached the acting
-- audit triggers. Keeper check_org_picker_ready_policies refuses this flip if any
-- agents policy still uses a home-only identity form. Reversible: set it back to false
-- (the products trigger from core 070 then ends every live selection, 'revoked').

UPDATE public.products
   SET org_picker_ready = true
 WHERE slug = 'agents'
   AND db_schema = 'agents';
