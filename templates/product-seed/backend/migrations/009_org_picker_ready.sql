-- 009 — turn the platform org picker ON for seed (rollout after the social-wiring pilot)
--
-- 007 converted every seed RLS policy that keyed on the caller's home org to the
-- policy-literal helper public.current_org_id_for('{{SCHEMA_NAME}}'); 008 attached the acting
-- audit triggers. Keeper check_org_picker_ready_policies refuses this flip if any
-- seed policy still uses a home-only identity form. Reversible: set it back to false
-- (the products trigger from core 070 then ends every live selection, 'revoked').

UPDATE public.products
   SET org_picker_ready = true
 WHERE slug = '{{SCHEMA_NAME}}'
   AND db_schema = '{{SCHEMA_NAME}}';
