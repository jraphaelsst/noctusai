-- orbity access-tier lockdown, batch 3 -- the LAST 23 tables (owner, 2026-11-10: orbity goes live first; this is the NEXT slice).
-- Until now nine routers (agenda, automation, clients, content_plans, crm, meta_ads, reports, social_content, tasks)
-- read and wrote these tables with the caller's OWN JWT under RLS (`org_id = public.current_org_id()`). RLS isolated the
-- tenants but left RULE-BYPASS open: a member could write straight through PostgREST and skip every backend validation
-- (forge `automation_pending_actions.payload`, which the worker then executes; point a row at another org's id).
-- Now every router reaches them with the SERVICE-ROLE client BOUND to the request's org (`app/org_scope.py` over the seed
-- `noctusai_lib.api.org_scoped.OrgScopedClient`: the org filter on every query, org_id stamped on every insert, foreign
-- keys proven to belong to the same org). The browser roles hold no privilege and no policy on any of them; the customer
-- role (`membro`) was already denied by get_current_user_org (403) and by current_org_id() (NULL). Same shape as 031/032.
-- Nothing in the frontend reads these through PostgREST (verified). Re-runnable.
-- BEFORE APPLYING (prod): run products/orbity/backend/audits/cross_org_references.sql (read-only, as postgres/service_role).
-- It MUST return 0 rows: any row is a reference whose target lives in another org (or a user outside the org), which the
-- org-bound client would refuse from now on. Fix or null those rows first.
-- AFTER APPLYING 034 + 035: verify the privileges (see the POST-APPLY block in 035: `pg_default_acl` for
-- `defaclnamespace = 'orbity'::regnamespace`, because a default-privilege revoke only applies to the role that granted it).
SET search_path = orbity, public;

-- member (org-scoped) policies of any name go; only the service_role policy remains.
DO $drop$
DECLARE r record;
BEGIN
  FOR r IN SELECT schemaname, tablename, policyname FROM pg_policies
           WHERE schemaname = 'orbity' AND tablename = ANY (ARRAY['ad_accounts', 'agenda_events', 'automation_executions', 'automation_flows', 'automation_pending_actions', 'automation_steps', 'campaign_metrics', 'campaigns', 'clients', 'content_campaigns', 'content_plan_items', 'content_plans', 'content_posts', 'lead_activities', 'lead_scoring_results', 'lead_scoring_rules', 'lead_stages', 'leads', 'post_approvals', 'report_snapshots', 'reports', 'routines', 'tasks'])
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
  END LOOP;
END
$drop$;

ALTER TABLE orbity.ad_accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.ad_accounts FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.ad_accounts FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.ad_accounts TO service_role;
COMMENT ON TABLE orbity.ad_accounts IS 'tier:org';

ALTER TABLE orbity.agenda_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.agenda_events FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.agenda_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.agenda_events TO service_role;
COMMENT ON TABLE orbity.agenda_events IS 'tier:org';

ALTER TABLE orbity.automation_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.automation_executions FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.automation_executions FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.automation_executions TO service_role;
COMMENT ON TABLE orbity.automation_executions IS 'tier:org';

ALTER TABLE orbity.automation_flows ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.automation_flows FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.automation_flows FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.automation_flows TO service_role;
COMMENT ON TABLE orbity.automation_flows IS 'tier:org';

ALTER TABLE orbity.automation_pending_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.automation_pending_actions FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.automation_pending_actions FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.automation_pending_actions TO service_role;
COMMENT ON TABLE orbity.automation_pending_actions IS 'tier:org';

ALTER TABLE orbity.automation_steps ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.automation_steps FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.automation_steps FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.automation_steps TO service_role;
COMMENT ON TABLE orbity.automation_steps IS 'tier:org';

ALTER TABLE orbity.campaign_metrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.campaign_metrics FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.campaign_metrics FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.campaign_metrics TO service_role;
COMMENT ON TABLE orbity.campaign_metrics IS 'tier:org';

ALTER TABLE orbity.campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.campaigns FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.campaigns FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.campaigns TO service_role;
COMMENT ON TABLE orbity.campaigns IS 'tier:org';

ALTER TABLE orbity.clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.clients FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.clients FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.clients TO service_role;
COMMENT ON TABLE orbity.clients IS 'tier:org';

ALTER TABLE orbity.content_campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.content_campaigns FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.content_campaigns FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.content_campaigns TO service_role;
COMMENT ON TABLE orbity.content_campaigns IS 'tier:org';

ALTER TABLE orbity.content_plan_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.content_plan_items FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.content_plan_items FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.content_plan_items TO service_role;
COMMENT ON TABLE orbity.content_plan_items IS 'tier:org';

ALTER TABLE orbity.content_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.content_plans FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.content_plans FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.content_plans TO service_role;
COMMENT ON TABLE orbity.content_plans IS 'tier:org';

ALTER TABLE orbity.content_posts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.content_posts FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.content_posts FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.content_posts TO service_role;
COMMENT ON TABLE orbity.content_posts IS 'tier:org';

ALTER TABLE orbity.lead_activities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.lead_activities FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.lead_activities FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.lead_activities TO service_role;
COMMENT ON TABLE orbity.lead_activities IS 'tier:org';

ALTER TABLE orbity.lead_scoring_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.lead_scoring_results FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.lead_scoring_results FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.lead_scoring_results TO service_role;
COMMENT ON TABLE orbity.lead_scoring_results IS 'tier:org';

ALTER TABLE orbity.lead_scoring_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.lead_scoring_rules FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.lead_scoring_rules FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.lead_scoring_rules TO service_role;
COMMENT ON TABLE orbity.lead_scoring_rules IS 'tier:org';

ALTER TABLE orbity.lead_stages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.lead_stages FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.lead_stages FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.lead_stages TO service_role;
COMMENT ON TABLE orbity.lead_stages IS 'tier:org';

ALTER TABLE orbity.leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.leads FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.leads FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.leads TO service_role;
COMMENT ON TABLE orbity.leads IS 'tier:org';

ALTER TABLE orbity.post_approvals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.post_approvals FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.post_approvals FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.post_approvals TO service_role;
COMMENT ON TABLE orbity.post_approvals IS 'tier:org';

ALTER TABLE orbity.report_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.report_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.report_snapshots FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.report_snapshots TO service_role;
COMMENT ON TABLE orbity.report_snapshots IS 'tier:org';

ALTER TABLE orbity.reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.reports FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.reports FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.reports TO service_role;
COMMENT ON TABLE orbity.reports IS 'tier:org';

ALTER TABLE orbity.routines ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.routines FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.routines FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.routines TO service_role;
COMMENT ON TABLE orbity.routines IS 'tier:org';

ALTER TABLE orbity.tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON orbity.tasks FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.tasks FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.tasks TO service_role;
COMMENT ON TABLE orbity.tasks IS 'tier:org';
