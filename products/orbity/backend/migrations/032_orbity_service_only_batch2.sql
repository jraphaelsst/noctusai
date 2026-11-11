-- orbity access-tier lockdown, batch 2 + link hygiene (owner, 2026-11-10; security review round 3).
-- 1. The legacy tables 023 retired by RENAME (kept as financial history, never read by the app) go service-only, like 031.
--    Their policies kept the pre-rename names. `revenues` / `expenses` are now security-invoker VIEWS over the finance
--    tables: the reports service reads them with the ADMIN client, so the browser roles lose them too.
-- 2. A published report link always ends: published reports without an `expires_at` get now() + 30 days (the public read
--    fails CLOSED on a missing expiry; new publishes get the default in the service).
SET search_path = orbity, public;

ALTER TABLE orbity.contracts_legacy ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "contracts_select_own_org" ON orbity.contracts_legacy;
DROP POLICY IF EXISTS "contracts_insert_own_org" ON orbity.contracts_legacy;
DROP POLICY IF EXISTS "contracts_update_own_org" ON orbity.contracts_legacy;
DROP POLICY IF EXISTS "contracts_delete_own_org" ON orbity.contracts_legacy;
DROP POLICY IF EXISTS "contracts_service_role_all" ON orbity.contracts_legacy;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.contracts_legacy;
CREATE POLICY "service_role_bypass" ON orbity.contracts_legacy FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.contracts_legacy FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.contracts_legacy TO service_role;
COMMENT ON TABLE orbity.contracts_legacy IS 'tier:org';
ALTER TABLE orbity.expenses_legacy ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "expenses_select_own_org" ON orbity.expenses_legacy;
DROP POLICY IF EXISTS "expenses_insert_own_org" ON orbity.expenses_legacy;
DROP POLICY IF EXISTS "expenses_update_own_org" ON orbity.expenses_legacy;
DROP POLICY IF EXISTS "expenses_delete_own_org" ON orbity.expenses_legacy;
DROP POLICY IF EXISTS "expenses_service_role_all" ON orbity.expenses_legacy;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.expenses_legacy;
CREATE POLICY "service_role_bypass" ON orbity.expenses_legacy FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.expenses_legacy FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.expenses_legacy TO service_role;
COMMENT ON TABLE orbity.expenses_legacy IS 'tier:org';
ALTER TABLE orbity.revenues_legacy ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "revenues_select_own_org" ON orbity.revenues_legacy;
DROP POLICY IF EXISTS "revenues_insert_own_org" ON orbity.revenues_legacy;
DROP POLICY IF EXISTS "revenues_update_own_org" ON orbity.revenues_legacy;
DROP POLICY IF EXISTS "revenues_delete_own_org" ON orbity.revenues_legacy;
DROP POLICY IF EXISTS "revenues_service_role_all" ON orbity.revenues_legacy;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.revenues_legacy;
CREATE POLICY "service_role_bypass" ON orbity.revenues_legacy FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.revenues_legacy FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.revenues_legacy TO service_role;
COMMENT ON TABLE orbity.revenues_legacy IS 'tier:org';

REVOKE ALL ON orbity.revenues, orbity.expenses FROM PUBLIC, anon, authenticated;
GRANT SELECT ON orbity.revenues, orbity.expenses TO service_role;

UPDATE orbity.reports SET expires_at = now() + interval '30 days' WHERE status = 'published' AND expires_at IS NULL;
