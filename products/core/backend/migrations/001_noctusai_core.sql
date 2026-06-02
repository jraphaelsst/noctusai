-- ============================================================
-- NoctusAI Core — Database Schema
-- Run this in the Supabase SQL Editor (paste all at once)
-- ============================================================

-------------------------------------------------
-- 1. ORGANIZATIONS (tenants)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS organizations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    plano TEXT NOT NULL DEFAULT 'free',        -- free | starter | pro | enterprise | disabled
    owner_id UUID,                              -- Supabase auth user who created it
    category TEXT NOT NULL DEFAULT 'normal'      -- normal | test
        CHECK (category IN ('normal', 'test')),
    logo_url TEXT,
    cnpj TEXT,
    telefone TEXT,
    endereco TEXT,
    onboarding_completed BOOLEAN DEFAULT false,
    onboarding_steps JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_owner ON organizations(owner_id);

-------------------------------------------------
-- 2. NOCTUS USERS (platform-level profiles)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS noctus_users (
    id UUID PRIMARY KEY,                        -- matches Supabase auth.users.id
    email TEXT NOT NULL,
    nome TEXT NOT NULL,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'user',           -- admin | manager | user
    org_role TEXT DEFAULT 'member',              -- owner | admin | member | viewer
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_noctus_users_org ON noctus_users(org_id);
CREATE INDEX IF NOT EXISTS idx_noctus_users_email ON noctus_users(email);

-------------------------------------------------
-- 3. PRODUCTS (marketplace catalog)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,                   -- e.g. 'erp-imobiliario'
    descricao TEXT,
    icone TEXT,                                  -- emoji or icon name
    url_base TEXT NOT NULL,                      -- product URL
    cor TEXT DEFAULT '#6366f1',                   -- brand color
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_slug ON products(slug);

-------------------------------------------------
-- 4. LICENSES (org ↔ product access)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS licenses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',        -- active | expired | revoked
    inicio TIMESTAMPTZ DEFAULT now(),
    fim TIMESTAMPTZ,                              -- null = no expiry
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_licenses_org ON licenses(org_id);
CREATE INDEX IF NOT EXISTS idx_licenses_product ON licenses(product_id);

-- Only one active license per org+product; historical revoked/expired records are unrestricted
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_one_active_per_org_product
    ON licenses (org_id, product_id)
    WHERE status = 'active';

-------------------------------------------------
-- 5. PLANS (subscription tiers)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    descricao TEXT,
    price_monthly NUMERIC NOT NULL DEFAULT 0,
    price_yearly NUMERIC NOT NULL DEFAULT 0,
    max_users INT NOT NULL DEFAULT -1,
    max_products INT NOT NULL DEFAULT -1,
    features JSONB NOT NULL DEFAULT '{}',
    is_custom BOOLEAN NOT NULL DEFAULT false,
    ativo BOOLEAN NOT NULL DEFAULT true,
    stripe_price_id_monthly TEXT,
    stripe_price_id_yearly TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-------------------------------------------------
-- 6. SUBSCRIPTIONS (org ↔ plan)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    plan_id UUID NOT NULL REFERENCES plans(id),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'canceled', 'expired', 'trial')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    stripe_subscription_id TEXT,
    stripe_customer_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_org ON subscriptions(org_id);

-------------------------------------------------
-- 7. API KEYS
-------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    scopes JSONB NOT NULL DEFAULT '["read"]',
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID NOT NULL REFERENCES noctus_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(org_id);

-------------------------------------------------
-- 8. ROLES (RBAC)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    permissions TEXT[] NOT NULL DEFAULT '{}',
    is_system BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-------------------------------------------------
-- 9. INVITATIONS (team management)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL REFERENCES noctus_users(id),
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invitations_org ON invitations(org_id);
CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);

-------------------------------------------------
-- 10. NOTIFICATIONS
-------------------------------------------------
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

-------------------------------------------------
-- 11. AUDIT LOGS
-------------------------------------------------
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

-------------------------------------------------
-- 12. WEBHOOK ENDPOINTS
-------------------------------------------------
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

-------------------------------------------------
-- 13. WEBHOOK DELIVERIES
-------------------------------------------------
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

-------------------------------------------------
-- 14. PLATFORM SETTINGS
-------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    is_secret BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT now(),
    updated_by UUID REFERENCES auth.users(id)
);

-------------------------------------------------
-- 15. ORG SETTINGS
-------------------------------------------------
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

-- FK indexes
CREATE INDEX IF NOT EXISTS idx_api_keys_created_by ON public.api_keys(created_by);
CREATE INDEX IF NOT EXISTS idx_invitations_invited_by ON public.invitations(invited_by);
CREATE INDEX IF NOT EXISTS idx_notifications_org_id ON public.notifications(org_id);
CREATE INDEX IF NOT EXISTS idx_platform_settings_updated_by ON public.platform_settings(updated_by);
CREATE INDEX IF NOT EXISTS idx_roles_org_id ON public.roles(org_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_id ON public.subscriptions(plan_id);

-------------------------------------------------
-- 16. RLS Policies
-------------------------------------------------

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE noctus_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_settings ENABLE ROW LEVEL SECURITY;

-- Products & Plans are readable by all authenticated users
CREATE POLICY "products_read_all" ON products
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "plans_read_all" ON plans
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "plans_admin_write" ON plans
    FOR ALL USING ((SELECT auth.uid()) IN (SELECT id FROM noctus_users WHERE role = 'admin'));

-- Users can read their own org
CREATE POLICY "org_read_own" ON organizations
    FOR SELECT TO authenticated
    USING (id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

-- Users can read profiles in their org
CREATE POLICY "users_read_own" ON noctus_users
    FOR SELECT TO authenticated
    USING (id = (SELECT auth.uid()) OR org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

-- Licenses: read own org
CREATE POLICY "licenses_read_own_org" ON licenses
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

-- Subscriptions: read own org, admin write
CREATE POLICY "subscriptions_read_own" ON subscriptions
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

CREATE POLICY "subscriptions_admin_all" ON subscriptions
    FOR ALL USING ((SELECT auth.uid()) IN (SELECT id FROM noctus_users WHERE role = 'admin'));

-- API keys: own org
CREATE POLICY "api_keys_read_own" ON api_keys
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

CREATE POLICY "api_keys_write_own" ON api_keys
    FOR ALL TO authenticated
    USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

-- Invitations: own org
CREATE POLICY "invitations_read_own" ON invitations
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid())));

-- Notifications: own records
CREATE POLICY "notifications_own" ON notifications
    FOR ALL USING (user_id = (SELECT auth.uid()));

CREATE POLICY "notifications_service" ON notifications
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Audit logs: read own org
CREATE POLICY "audit_logs_org_read" ON audit_logs
    FOR SELECT USING (
        org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid()))
    );

CREATE POLICY "audit_logs_service" ON audit_logs
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Webhook endpoints: own org
CREATE POLICY "webhook_endpoints_org" ON webhook_endpoints
    FOR ALL USING (
        org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid()))
    );

CREATE POLICY "webhook_endpoints_service" ON webhook_endpoints
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Webhook deliveries: via endpoint's org
CREATE POLICY "webhook_deliveries_via_endpoint" ON webhook_deliveries
    FOR SELECT USING (
        endpoint_id IN (
            SELECT id FROM webhook_endpoints
            WHERE org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid()))
        )
    );

CREATE POLICY "webhook_deliveries_service" ON webhook_deliveries
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Platform settings: service role only
CREATE POLICY "platform_settings_service" ON platform_settings
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Org settings: org members
CREATE POLICY "org_settings_org_members" ON org_settings
    FOR ALL USING (
        org_id IN (SELECT org_id FROM noctus_users WHERE id = (SELECT auth.uid()))
    );

CREATE POLICY "org_settings_service" ON org_settings
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Service role policies for core tables
CREATE POLICY "organizations_service" ON organizations
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "noctus_users_service" ON noctus_users
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "products_service" ON products
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "licenses_service" ON licenses
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "plans_service" ON plans
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "subscriptions_service" ON subscriptions
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "api_keys_service" ON api_keys
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "roles_service" ON roles
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "roles_read_own_org" ON public.roles
  FOR SELECT TO authenticated
  USING (org_id IN (
    SELECT noctus_users.org_id FROM noctus_users
    WHERE noctus_users.id = (SELECT auth.uid())
  ));

CREATE POLICY "invitations_service" ON invitations
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-------------------------------------------------
-- 17. Seed Data
-------------------------------------------------

-- Default plans
INSERT INTO plans (nome, slug, descricao, price_monthly, price_yearly, max_users, max_products, ativo)
VALUES
    ('Free', 'free', 'Plano gratuito com recursos básicos', 0, 0, 3, 1, true),
    ('Pro', 'pro', 'Plano profissional para equipes', 99, 990, 15, 5, true),
    ('Enterprise', 'enterprise', 'Plano empresarial com tudo ilimitado', 299, 2990, -1, -1, true)
ON CONFLICT (slug) DO NOTHING;

-- System roles
INSERT INTO roles (org_id, name, slug, permissions, is_system)
VALUES
    (NULL, 'Proprietário', 'owner', ARRAY['*'], true),
    (NULL, 'Administrador', 'admin', ARRAY['team:manage', 'billing:manage', 'settings:manage', 'products:access'], true),
    (NULL, 'Membro', 'member', ARRAY['products:access', 'team:read'], true),
    (NULL, 'Visualizador', 'viewer', ARRAY['products:access:readonly', 'team:read'], true)
ON CONFLICT DO NOTHING;

-- ERP Imobiliário product
INSERT INTO products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'ERP Imobiliário',
    'erp-imobiliario',
    'Sistema completo para gestão de imobiliárias: clientes, imóveis, permutas, matching inteligente e metas.',
    '🏠',
    'http://localhost:8080',
    '#10b981',
    true
) ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- 17. RLS HELPER FUNCTIONS (unified pattern)
-- ============================================================

CREATE OR REPLACE FUNCTION public.current_user_id()
  RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public
AS $$ SELECT (SELECT auth.uid()); $$;

-- current_org_id() — SECURITY DEFINER org resolver.
-- Reads from the trusted noctus_users table (NOT from the JWT claim, which is
-- user_metadata-nested and thus: (a) always NULL at the top level, and
-- (b) user-editable — a privilege-escalation hole if used for RLS).
-- Root-fixed 2026-06-02 (feat/rls-migration-parity): original used
-- auth.jwt() ->> 'org_id' which is always NULL in Supabase.
CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public
AS $$ SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid()); $$;

CREATE OR REPLACE FUNCTION public.is_platform_admin()
  RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public
AS $$ SELECT EXISTS (
  SELECT 1 FROM public.noctus_users
  WHERE id = (SELECT auth.uid()) AND role = 'admin'
); $$;

-- ============================================================
-- 18. PROVISIONING LIFECYCLE
-- ============================================================

CREATE OR REPLACE FUNCTION public.provision_erp(p_org_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, erp
AS $$
BEGIN
  INSERT INTO erp.site_config (org_id, nome_imobiliaria, ativo)
  VALUES (p_org_id, 'Minha Imobiliária', true)
  ON CONFLICT DO NOTHING;
  INSERT INTO public.audit_logs (user_id, org_id, action, resource_type, details)
  VALUES (NULL, p_org_id, 'provision', 'product', '{"product": "erp-imobiliario", "status": "provisioned"}'::jsonb);
END;
$$;

CREATE OR REPLACE FUNCTION public.provision_personal_finance(p_org_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.audit_logs (user_id, org_id, action, resource_type, details)
  VALUES (NULL, p_org_id, 'provision', 'product', '{"product": "personal-finance", "status": "provisioned"}'::jsonb);
END;
$$;

CREATE OR REPLACE FUNCTION public.provision_therapy(p_org_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.audit_logs (user_id, org_id, action, resource_type, details)
  VALUES (NULL, p_org_id, 'provision', 'product', '{"product": "therapy-platform", "status": "provisioned"}'::jsonb);
END;
$$;

CREATE OR REPLACE FUNCTION public.deprovision_product(p_org_id uuid, p_product_slug text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.audit_logs (user_id, org_id, action, resource_type, details)
  VALUES (NULL, p_org_id, 'deprovision', 'product',
    jsonb_build_object('product', p_product_slug, 'status', 'deprovisioned'));
  INSERT INTO public.notifications (user_id, org_id, type, title, message, metadata)
  SELECT nu.id, p_org_id, 'system',
    'Licença revogada',
    'O acesso ao produto ' || p_product_slug || ' foi revogado para sua organização.',
    jsonb_build_object('product', p_product_slug, 'action', 'revoked')
  FROM public.noctus_users nu WHERE nu.org_id = p_org_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.on_license_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_slug text;
  v_org_id uuid;
BEGIN
  SELECT slug INTO v_slug FROM public.products WHERE id = NEW.product_id;
  v_org_id := NEW.org_id;
  IF TG_OP = 'INSERT' AND NEW.status = 'active' THEN
    CASE v_slug
      WHEN 'erp-imobiliario' THEN PERFORM public.provision_erp(v_org_id);
      WHEN 'personal-finance' THEN PERFORM public.provision_personal_finance(v_org_id);
      WHEN 'therapy-platform' THEN PERFORM public.provision_therapy(v_org_id);
      ELSE NULL;
    END CASE;
    INSERT INTO public.notifications (user_id, org_id, type, title, message, metadata)
    SELECT nu.id, v_org_id, 'system',
      'Novo produto disponível',
      'Sua organização agora tem acesso ao ' || COALESCE((SELECT nome FROM public.products WHERE id = NEW.product_id), v_slug) || '!',
      jsonb_build_object('product', v_slug, 'license_id', NEW.id, 'action', 'granted')
    FROM public.noctus_users nu WHERE nu.org_id = v_org_id;
  ELSIF TG_OP = 'UPDATE' AND OLD.status = 'active' AND NEW.status = 'revoked' THEN
    PERFORM public.deprovision_product(v_org_id, v_slug);
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS license_provisioning_trigger ON public.licenses;
CREATE TRIGGER license_provisioning_trigger
  AFTER INSERT OR UPDATE ON public.licenses
  FOR EACH ROW EXECUTE FUNCTION public.on_license_change();

-- ============================================================
-- 19. USAGE REPORTING
-- ============================================================

CREATE TABLE IF NOT EXISTS public.product_usage (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations(id),
  product_id uuid NOT NULL REFERENCES public.products(id),
  metric text NOT NULL,
  value bigint NOT NULL DEFAULT 0,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT product_usage_unique UNIQUE (org_id, product_id, metric, recorded_at)
);

ALTER TABLE public.product_usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON public.product_usage FOR ALL TO service_role USING (true);
CREATE POLICY "admin_read" ON public.product_usage FOR SELECT TO authenticated
  USING ((SELECT auth.uid()) IN (SELECT id FROM public.noctus_users WHERE role = 'admin'));
CREATE POLICY "org_read_own" ON public.product_usage FOR SELECT TO authenticated
  USING (org_id IN (SELECT noctus_users.org_id FROM noctus_users WHERE noctus_users.id = (SELECT auth.uid())));

CREATE INDEX idx_product_usage_org ON public.product_usage(org_id);
CREATE INDEX idx_product_usage_recorded ON public.product_usage(recorded_at DESC);

CREATE OR REPLACE FUNCTION public.snapshot_product_usage()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  lic RECORD;
  v_slug text;
  v_active_users bigint;
  v_total_records bigint;
  v_now timestamptz := now();
BEGIN
  FOR lic IN
    SELECT l.org_id, l.product_id, p.slug
    FROM public.licenses l JOIN public.products p ON p.id = l.product_id
    WHERE l.status = 'active'
  LOOP
    v_slug := lic.slug;
    v_active_users := 0;
    v_total_records := 0;
    CASE v_slug
      WHEN 'erp-imobiliario' THEN
        SELECT COUNT(DISTINCT usuario_id) INTO v_active_users
        FROM erp.user_actions_log WHERE created_at > v_now - interval '30 days';
        SELECT (
          (SELECT COUNT(*) FROM erp.ativos WHERE org_id = lic.org_id) +
          (SELECT COUNT(*) FROM erp.clientes WHERE org_id = lic.org_id) +
          (SELECT COUNT(*) FROM erp.condominios WHERE org_id = lic.org_id)
        ) INTO v_total_records;
      WHEN 'personal-finance' THEN
        SELECT COUNT(DISTINCT user_id) INTO v_active_users
        FROM "personal-finance".transacoes WHERE created_at > v_now - interval '30 days';
        SELECT (
          (SELECT COUNT(*) FROM "personal-finance".contas) +
          (SELECT COUNT(*) FROM "personal-finance".transacoes) +
          (SELECT COUNT(*) FROM "personal-finance".categorias WHERE user_id IS NOT NULL)
        ) INTO v_total_records;
      WHEN 'therapy-platform' THEN
        SELECT COUNT(DISTINCT therapist_id) + COUNT(DISTINCT patient_id) INTO v_active_users
        FROM therapy.appointments WHERE created_at > v_now - interval '30 days';
        SELECT (
          (SELECT COUNT(*) FROM therapy.appointments) +
          (SELECT COUNT(*) FROM therapy.session_records) +
          (SELECT COUNT(*) FROM therapy.reviews)
        ) INTO v_total_records;
      ELSE CONTINUE;
    END CASE;
    INSERT INTO public.product_usage (org_id, product_id, metric, value, recorded_at)
    VALUES
      (lic.org_id, lic.product_id, 'active_users_30d', v_active_users, v_now),
      (lic.org_id, lic.product_id, 'total_records', v_total_records, v_now)
    ON CONFLICT (org_id, product_id, metric, recorded_at) DO UPDATE SET value = EXCLUDED.value;
  END LOOP;
END;
$$;

SELECT cron.schedule('daily-usage-snapshot', '0 3 * * *', 'SELECT public.snapshot_product_usage()');
