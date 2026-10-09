-- 009 — turn the platform org picker ON for seed (rollout after the social-wiring pilot)
--
-- 007 converted every seed RLS policy that keyed on the caller's home org to the
-- policy-literal helper public.current_org_id_for('seed'); 008 attached the acting
-- audit triggers. Keeper check_org_picker_ready_policies refuses this flip if any
-- seed policy still uses a home-only identity form. Reversible: set it back to false
-- (the products trigger from core 070 then ends every live selection, 'revoked').
-- Keyed on db_schema ONLY (unique, core 070): this chain is the template for every new
-- product, whose slug differs from its schema; the scaffold's products-row migration sets it.

UPDATE public.products
   SET org_picker_ready = true
 WHERE db_schema = 'seed';
