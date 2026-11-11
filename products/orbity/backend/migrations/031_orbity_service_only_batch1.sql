-- orbity access-tier lockdown, batch 1 (owner, 2026-11-10: tiers locked BEFORE go-live; findings ledger `access-tier`).
-- These tables are reached ONLY through the orbity backend with the SERVICE-ROLE client (billing worker + webhook, the
-- contracts organ, the financial router, offboarding, the seed team router) -- verified by grep of every app/ and seed/
-- accessor; nothing in the frontend reads them through PostgREST. So the browser roles get no policy and no privilege.
-- Tables the user-JWT routers still read under RLS (leads, clients, tasks, automation, content, reports, meta_ads...) are
-- NOT here: revoking them would cut the product off; they move to the service role in their own slice. Re-runnable.
SET search_path = orbity, public;

ALTER TABLE orbity.billing_charges ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "billing_charges_select_own_org" ON orbity.billing_charges;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.billing_charges;
CREATE POLICY "service_role_bypass" ON orbity.billing_charges FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.billing_charges FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.billing_charges TO service_role;
COMMENT ON TABLE orbity.billing_charges IS 'tier:org';
ALTER TABLE orbity.payment_gateway_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.payment_gateway_events;
CREATE POLICY "service_role_bypass" ON orbity.payment_gateway_events FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.payment_gateway_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.payment_gateway_events TO service_role;
COMMENT ON TABLE orbity.payment_gateway_events IS 'tier:org';
ALTER TABLE orbity.examples ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "examples_delete_own_org" ON orbity.examples;
DROP POLICY IF EXISTS "examples_insert_own_org" ON orbity.examples;
DROP POLICY IF EXISTS "examples_select_own_org" ON orbity.examples;
DROP POLICY IF EXISTS "examples_update_own_org" ON orbity.examples;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.examples;
CREATE POLICY "service_role_bypass" ON orbity.examples FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.examples FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.examples TO service_role;
COMMENT ON TABLE orbity.examples IS 'tier:org';
ALTER TABLE orbity.invitations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "invitations_select_own_org" ON orbity.invitations;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.invitations;
CREATE POLICY "service_role_bypass" ON orbity.invitations FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.invitations FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.invitations TO service_role;
COMMENT ON TABLE orbity.invitations IS 'tier:org';
ALTER TABLE orbity.ctr_contracts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.ctr_contracts;
CREATE POLICY "service_role_bypass" ON orbity.ctr_contracts FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ctr_contracts FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ctr_contracts TO service_role;
COMMENT ON TABLE orbity.ctr_contracts IS 'tier:org';
ALTER TABLE orbity.ctr_contract_attachments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "ctr_contract_attachments_select_own_org" ON orbity.ctr_contract_attachments;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.ctr_contract_attachments;
CREATE POLICY "service_role_bypass" ON orbity.ctr_contract_attachments FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ctr_contract_attachments FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ctr_contract_attachments TO service_role;
COMMENT ON TABLE orbity.ctr_contract_attachments IS 'tier:org';
ALTER TABLE orbity.ctr_contract_billings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "ctr_contract_billings_select_own_org" ON orbity.ctr_contract_billings;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.ctr_contract_billings;
CREATE POLICY "service_role_bypass" ON orbity.ctr_contract_billings FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ctr_contract_billings FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ctr_contract_billings TO service_role;
COMMENT ON TABLE orbity.ctr_contract_billings IS 'tier:org';
ALTER TABLE orbity.ctr_contract_lines ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "ctr_contract_lines_select_own_org" ON orbity.ctr_contract_lines;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.ctr_contract_lines;
CREATE POLICY "service_role_bypass" ON orbity.ctr_contract_lines FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ctr_contract_lines FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ctr_contract_lines TO service_role;
COMMENT ON TABLE orbity.ctr_contract_lines IS 'tier:org';
ALTER TABLE orbity.ctr_contract_usage ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "ctr_contract_usage_select_own_org" ON orbity.ctr_contract_usage;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.ctr_contract_usage;
CREATE POLICY "service_role_bypass" ON orbity.ctr_contract_usage FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ctr_contract_usage FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ctr_contract_usage TO service_role;
COMMENT ON TABLE orbity.ctr_contract_usage IS 'tier:org';
ALTER TABLE orbity.ctr_contract_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "ctr_contract_versions_select_own_org" ON orbity.ctr_contract_versions;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.ctr_contract_versions;
CREATE POLICY "service_role_bypass" ON orbity.ctr_contract_versions FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ctr_contract_versions FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ctr_contract_versions TO service_role;
COMMENT ON TABLE orbity.ctr_contract_versions IS 'tier:org';
