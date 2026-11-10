-- orbity.whatsapp_connections: service-only (security review F4, 2026-11-10).
-- The table holds each org's WAHA base_url, session, ENCRYPTED api key and webhook token. The API reads and writes it with
-- the service role (noctusai_seed.whatsapp_connections_router) and nothing in the frontend reads it through PostgREST, so
-- the browser roles get no policy and no privilege: an `authenticated` session is any member of the org, and the API
-- applies the admin-only masking a direct read would skip. Re-runnable.
SET search_path = orbity, public;

ALTER TABLE orbity.whatsapp_connections ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "whatsapp_connections_select_own_org" ON orbity.whatsapp_connections;
DROP POLICY IF EXISTS "whatsapp_connections_service_role_bypass" ON orbity.whatsapp_connections;
CREATE POLICY "whatsapp_connections_service_role_bypass" ON orbity.whatsapp_connections
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.whatsapp_connections FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.whatsapp_connections TO service_role;
COMMENT ON TABLE orbity.whatsapp_connections IS 'tier:org';
