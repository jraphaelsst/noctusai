-- 017 — turn the platform org picker ON for academia-de-reciclagem (rollout after the social-wiring pilot)
--
-- 015 converted every academia_de_reciclagem RLS policy that keyed on the caller's home org to the
-- policy-literal helper public.current_org_id_for('academia_de_reciclagem'); 016 attached the acting
-- audit triggers. Keeper check_org_picker_ready_policies refuses this flip if any
-- academia_de_reciclagem policy still uses a home-only identity form. Reversible: set it back to false
-- (the products trigger from core 070 then ends every live selection, 'revoked').

UPDATE public.products
   SET org_picker_ready = true
 WHERE slug = 'academia-de-reciclagem'
   AND db_schema = 'academia_de_reciclagem';
