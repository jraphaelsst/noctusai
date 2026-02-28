-- 002_missing_tables.sql
-- Creates tables referenced by Core backend routers but missing from 001_noctusai_core.sql:
--   notifications, audit_logs, webhook_endpoints, webhook_deliveries,
--   platform_settings, org_settings

-- Notifications -----------------------------------------------------------

CREATE TABLE IF NOT EXISTS notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES noctus_users(id) ON DELETE CASCADE,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('team_invite', 'subscription_change', 'usage_alert', 'system')),
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  read BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id) WHERE read = false;

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notifications_own" ON notifications
  FOR ALL USING (user_id = auth.uid());

CREATE POLICY "notifications_service" ON notifications
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Audit Logs --------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES noctus_users(id),
  org_id UUID REFERENCES organizations(id),
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  details JSONB NOT NULL DEFAULT '{}',
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "audit_logs_org_read" ON audit_logs
  FOR SELECT USING (
    org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid())
  );

CREATE POLICY "audit_logs_service" ON audit_logs
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Webhook Endpoints -------------------------------------------------------

CREATE TABLE IF NOT EXISTS webhook_endpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  secret TEXT NOT NULL,
  events TEXT[] NOT NULL DEFAULT '{}',
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_org ON webhook_endpoints(org_id);

ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY;

CREATE POLICY "webhook_endpoints_org" ON webhook_endpoints
  FOR ALL USING (
    org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid())
  );

CREATE POLICY "webhook_endpoints_service" ON webhook_endpoints
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Webhook Deliveries ------------------------------------------------------

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  endpoint_id UUID NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  response_status INT,
  response_body TEXT,
  attempts INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_id, created_at DESC);

ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "webhook_deliveries_via_endpoint" ON webhook_deliveries
  FOR SELECT USING (
    endpoint_id IN (
      SELECT id FROM webhook_endpoints
      WHERE org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid())
    )
  );

CREATE POLICY "webhook_deliveries_service" ON webhook_deliveries
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Platform Settings -------------------------------------------------------

CREATE TABLE IF NOT EXISTS platform_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  description TEXT,
  is_secret BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT now(),
  updated_by UUID REFERENCES auth.users(id)
);

ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "platform_settings_service" ON platform_settings
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Org Settings ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS org_settings (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  is_secret BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, key)
);

CREATE INDEX IF NOT EXISTS idx_org_settings_org ON org_settings(org_id);

ALTER TABLE org_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_settings_org_members" ON org_settings
  FOR ALL USING (
    org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid())
  );

CREATE POLICY "org_settings_service" ON org_settings
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);
