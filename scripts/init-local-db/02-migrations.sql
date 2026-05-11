-- ============================================================================
-- 02-migrations.sql — concatenated product migrations.
--
-- GENERATED FILE. Regenerate via: bash scripts/build-init-local-db.sh
--
-- Each product's first migration is wrapped in BEGIN/COMMIT so one product's
-- failure (e.g., a Supabase-only feature this offline profile doesn't
-- support — `cron.schedule()`, `CREATE EXTENSION vector`, `pg_net`)
-- doesn't poison the others.
--
-- `ON_ERROR_STOP off` overrides the docker-entrypoint default of `=1` so a
-- single failing statement aborts its enclosing transaction (BEGIN/COMMIT
-- block rolls back) but psql CONTINUES to the next product's block. With
-- the default ON_ERROR_STOP=1 the entrypoint would abort the whole file on
-- the first cross-product incompatibility and the rest of the fleet's
-- schemas would be lost — empirically observed during T4 verification.
-- ============================================================================

\set ON_ERROR_STOP off

-- ────────────────────────────────────────────────────────────────────────────
-- products/core/backend/migrations/001_noctusai_core.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

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

CREATE OR REPLACE FUNCTION public.current_org_id()
  RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public
AS $$ SELECT (SELECT (auth.jwt() ->> 'org_id'))::uuid; $$;

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

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/adconnect/backend/migrations/001_adconnect.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- AdConnect schema — single fresh-start migration
-- Schema: adconnect
--
-- Convention: every product ships ONE 001 migration that builds the full
-- schema from scratch. New tables / columns / RLS land as edits to this
-- file (so fresh environments stand up with a single command). For live
-- DBs already past 001, ship additive patches as numbered files (002+),
-- but keep them in lock-step with the 001 — at any point in time, applying
-- 001 alone to a fresh DB MUST produce the same final shape as applying
-- 001 + every patch in order.
--
-- See KB § PATTERNS/database-rls.md § Single 001 migration convention
-- for the rationale + how to add an additive patch when needed.
--
-- Topological order:
--   1. Framework  (status_pagina, invitations)
--   2. Identity   (distributors, distributor_memberships) — audited shape
--                  from Phase 0/1 of adconnect-mvp-implementation
--   3. Catalog    (categorias, products, precos_distribuidor, promos)
--   4. Sellout    (relatorios_sellout — defined before rewards so the FK
--                  from recompensas_acumuladas lands inline)
--   5. Orders     (carts, itens_carrinho, pedidos, itens_pedido)
--   6. Rewards    (regras_recompensa, recompensas_acumuladas, resgates)
--   7. Financial  (faturas)
--   8. Seed rows  (status_pagina entries)
-- ============================================================================

SET search_path = adconnect, public;

CREATE SCHEMA IF NOT EXISTS adconnect;

-- Grant usage to authenticated users (required for PostgREST).
GRANT USAGE ON SCHEMA adconnect TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA adconnect TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA adconnect TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA adconnect GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA adconnect GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- updated_at trigger function (lifted from noctusai_lib.domain.sql_templates)
-- ============================================================================

CREATE OR REPLACE FUNCTION adconnect.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = adconnect, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;


-- ============================================================================
-- 1. FRAMEWORK — page status (feature flags) + invitations
-- ============================================================================

CREATE TABLE adconnect.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE adconnect.status_pagina ENABLE ROW LEVEL SECURITY;

-- Anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON adconnect.status_pagina
    FOR SELECT USING (status = 'producao');


CREATE TABLE adconnect.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    -- AdConnect extension: an invitation can be scoped to a specific
    -- distributor — distributor_id is the membership target on accept.
    -- FK added below after distributors table exists.
    distributor_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adconnect.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON adconnect.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_adconnect_invitations_org ON adconnect.invitations(org_id);
CREATE INDEX idx_adconnect_invitations_token ON adconnect.invitations(token);


-- ============================================================================
-- 2. IDENTITY — distributors + distributor_memberships
--
-- Per Phase 0/1 audit (adconnect-mvp-implementation/findings.md §):
--   - Auth model Option A locked: distributor users live in
--     public.noctus_users with org_id = brand's org id; per-distributor
--     membership lives in adconnect.distributor_memberships.
--   - Mirrors therapy.clinics shape (the "sub-entity within an org" pattern).
--   - CNPJs ARE LGPD PII — flagged at write-time in the auth.py invitation flow.
-- ============================================================================

CREATE TABLE adconnect.distributors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    cnpj TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    -- Address (split for LGPD-targeted retention rules later)
    endereco_logradouro TEXT,
    endereco_numero TEXT,
    endereco_complemento TEXT,
    endereco_bairro TEXT,
    endereco_cidade TEXT,
    endereco_uf TEXT,
    endereco_cep TEXT,
    -- Contact (PII — LGPD-flagged at write site)
    contato_nome TEXT,
    contato_email TEXT,
    contato_telefone TEXT,
    -- State
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'pendente', 'suspenso', 'inativo')),
    tier TEXT NOT NULL DEFAULT 'STARTER' CHECK (tier IN ('STARTER', 'INSIDER', 'MASTER', 'SMARTER')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_adconnect_distributors_org ON adconnect.distributors(org_id);
CREATE INDEX idx_adconnect_distributors_cnpj ON adconnect.distributors(cnpj);
CREATE INDEX idx_adconnect_distributors_status ON adconnect.distributors(status);

CREATE OR REPLACE TRIGGER set_updated_at_distributors
    BEFORE UPDATE ON adconnect.distributors
    FOR EACH ROW EXECUTE FUNCTION adconnect.set_updated_at();


CREATE TABLE adconnect.distributor_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.noctus_users(id) ON DELETE CASCADE,
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'distributor_member' CHECK (role IN ('distributor_owner', 'distributor_member', 'distributor_viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, distributor_id)
);

CREATE INDEX idx_adconnect_memberships_user ON adconnect.distributor_memberships(user_id);
CREATE INDEX idx_adconnect_memberships_distributor ON adconnect.distributor_memberships(distributor_id);


-- ----------------------------------------------------------------------------
-- Identity RLS — service_role bypass + per-op policies (audited shape).
-- Mirror Therapy's pattern: backend handles authorization in Python; RLS
-- is the second line of defense for direct-DB access (admin tools etc.).
-- ----------------------------------------------------------------------------

ALTER TABLE adconnect.distributors ENABLE ROW LEVEL SECURITY;
ALTER TABLE adconnect.distributor_memberships ENABLE ROW LEVEL SECURITY;

-- Service role bypass (backend authorization)
CREATE POLICY "service_role_bypass_distributors" ON adconnect.distributors
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass_memberships" ON adconnect.distributor_memberships
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- distributors: SELECT — member or brand admin sees row.
CREATE POLICY "distributors_select_member_or_brand_admin" ON adconnect.distributors
    FOR SELECT TO authenticated
    USING (
        id IN (
            SELECT distributor_id FROM adconnect.distributor_memberships
            WHERE user_id = (SELECT auth.uid())
        )
        OR EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = adconnect.distributors.org_id
        )
    );

-- distributors: INSERT/UPDATE/DELETE — brand owner/admin only.
CREATE POLICY "distributors_write_brand_admin" ON adconnect.distributors
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = adconnect.distributors.org_id
        )
    );

CREATE POLICY "distributors_update_brand_admin" ON adconnect.distributors
    FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = adconnect.distributors.org_id
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = adconnect.distributors.org_id
        )
    );

CREATE POLICY "distributors_delete_brand_admin" ON adconnect.distributors
    FOR DELETE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = adconnect.distributors.org_id
        )
    );

-- memberships: SELECT — own row or brand admin.
CREATE POLICY "memberships_select_own_or_brand_admin" ON adconnect.distributor_memberships
    FOR SELECT TO authenticated
    USING (
        user_id = (SELECT auth.uid())
        OR EXISTS (
            SELECT 1 FROM public.noctus_users u
            JOIN adconnect.distributors d ON d.id = adconnect.distributor_memberships.distributor_id
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = d.org_id
        )
    );

-- memberships: INSERT/UPDATE/DELETE — brand owner/admin only (granted by
-- brand admin when accepting an invitation).
CREATE POLICY "memberships_write_brand_admin" ON adconnect.distributor_memberships
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            JOIN adconnect.distributors d ON d.id = adconnect.distributor_memberships.distributor_id
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = d.org_id
        )
    );

CREATE POLICY "memberships_update_brand_admin" ON adconnect.distributor_memberships
    FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            JOIN adconnect.distributors d ON d.id = adconnect.distributor_memberships.distributor_id
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = d.org_id
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            JOIN adconnect.distributors d ON d.id = adconnect.distributor_memberships.distributor_id
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = d.org_id
        )
    );

CREATE POLICY "memberships_delete_brand_admin" ON adconnect.distributor_memberships
    FOR DELETE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.noctus_users u
            JOIN adconnect.distributors d ON d.id = adconnect.distributor_memberships.distributor_id
            WHERE u.id = (SELECT auth.uid())
              AND u.org_role IN ('owner', 'admin')
              AND u.org_id = d.org_id
        )
    );

-- Backfill the deferred FK on invitations.distributor_id now that
-- distributors exists.
ALTER TABLE adconnect.invitations
    ADD CONSTRAINT invitations_distributor_fkey
    FOREIGN KEY (distributor_id)
    REFERENCES adconnect.distributors(id) ON DELETE SET NULL;


-- ============================================================================
-- 3. CATALOG — categorias + products + precos_distribuidor + promos
--
-- Wave 2 (Phase 2) draft RLS uses the simpler USING-only shape per-table.
-- If brand-admin write semantics differ from distributor-user semantics,
-- the engineer implementing Phase 2 should split into per-op policies
-- mirroring the identity section above.
-- ============================================================================

CREATE TABLE adconnect.categorias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativa BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, nome)
);

ALTER TABLE adconnect.categorias ENABLE ROW LEVEL SECURITY;

CREATE POLICY "categorias_select_own_org" ON adconnect.categorias
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_adconnect_categorias_org ON adconnect.categorias(org_id);


CREATE TABLE adconnect.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    categoria_id UUID REFERENCES adconnect.categorias(id) ON DELETE SET NULL,
    sku TEXT NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    base_price NUMERIC(12, 2) NOT NULL,
    in_stock BOOLEAN NOT NULL DEFAULT true,
    estoque_quantidade INTEGER,
    fotos TEXT[] NOT NULL DEFAULT '{}',
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, sku)
);

ALTER TABLE adconnect.products ENABLE ROW LEVEL SECURITY;

CREATE POLICY "products_select_own_org" ON adconnect.products
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_adconnect_products_org ON adconnect.products(org_id);
CREATE INDEX idx_adconnect_products_categoria ON adconnect.products(categoria_id);
CREATE INDEX idx_adconnect_products_sku ON adconnect.products(org_id, sku);


CREATE TABLE adconnect.precos_distribuidor (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES adconnect.products(id) ON DELETE CASCADE,
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE CASCADE,
    preferential_price NUMERIC(12, 2) NOT NULL,
    valido_de TIMESTAMPTZ,
    valido_ate TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, distributor_id)
);

ALTER TABLE adconnect.precos_distribuidor ENABLE ROW LEVEL SECURITY;

CREATE POLICY "precos_distrib_users_see_own" ON adconnect.precos_distribuidor
    FOR SELECT TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "precos_brand_admin_sees_all" ON adconnect.precos_distribuidor
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = precos_distribuidor.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_precos_product ON adconnect.precos_distribuidor(product_id);
CREATE INDEX idx_adconnect_precos_distributor ON adconnect.precos_distribuidor(distributor_id);


CREATE TABLE adconnect.promos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    desconto_percentual NUMERIC(5, 2),
    desconto_valor NUMERIC(12, 2),
    valido_de TIMESTAMPTZ NOT NULL,
    valido_ate TIMESTAMPTZ NOT NULL,
    ativa BOOLEAN NOT NULL DEFAULT true,
    aplicavel_categorias UUID[] NOT NULL DEFAULT '{}',
    aplicavel_produtos UUID[] NOT NULL DEFAULT '{}',
    aplicavel_distribuidores UUID[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (desconto_percentual IS NOT NULL AND desconto_valor IS NULL) OR
        (desconto_percentual IS NULL AND desconto_valor IS NOT NULL)
    )
);

ALTER TABLE adconnect.promos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "promos_select_own_org" ON adconnect.promos
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_adconnect_promos_org ON adconnect.promos(org_id);
CREATE INDEX idx_adconnect_promos_validade ON adconnect.promos(valido_de, valido_ate) WHERE ativa = true;


-- ============================================================================
-- 4. SELLOUT — relatorios_sellout
-- Defined before rewards so the FK from recompensas_acumuladas lands inline.
-- Three submission modes (per PROJECT.md §2): structured / nfe_xml / freeform.
-- ============================================================================

CREATE TABLE adconnect.relatorios_sellout (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE RESTRICT,
    submitted_by UUID NOT NULL,
    submission_mode TEXT NOT NULL CHECK (submission_mode IN ('estruturado', 'nfe_xml', 'freeform')),
    -- Structured-mode fields (also populated when NF-e parser fills them):
    cnpj_cliente_final TEXT,
    valor_total NUMERIC(12, 2),
    quantidade_itens INTEGER,
    descricao_resumida TEXT,
    items_json JSONB,
    -- NF-e mode:
    nfe_xml_url TEXT,
    nfe_chave TEXT,
    -- Freeform mode:
    attachment_url TEXT,
    observacoes TEXT,
    -- Lifecycle:
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'em_analise', 'aprovado', 'recusado')),
    review_notes TEXT,
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    -- Period coverage (typically a calendar month):
    periodo_inicio DATE NOT NULL,
    periodo_fim DATE NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (submission_mode = 'estruturado' AND valor_total IS NOT NULL) OR
        (submission_mode = 'nfe_xml' AND nfe_xml_url IS NOT NULL) OR
        (submission_mode = 'freeform' AND attachment_url IS NOT NULL)
    ),
    CHECK (periodo_fim >= periodo_inicio)
);

ALTER TABLE adconnect.relatorios_sellout ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sellout_distrib_users_see_own" ON adconnect.relatorios_sellout
    FOR ALL TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "sellout_brand_admin_sees_all" ON adconnect.relatorios_sellout
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = relatorios_sellout.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_sellout_distributor ON adconnect.relatorios_sellout(distributor_id);
CREATE INDEX idx_adconnect_sellout_status ON adconnect.relatorios_sellout(status);
CREATE INDEX idx_adconnect_sellout_periodo ON adconnect.relatorios_sellout(periodo_inicio, periodo_fim);
CREATE INDEX idx_adconnect_sellout_nfe_chave ON adconnect.relatorios_sellout(nfe_chave) WHERE nfe_chave IS NOT NULL;


-- ============================================================================
-- 5. ORDERS — carts + itens_carrinho + pedidos + itens_pedido
-- Pedidos status lifecycle: rascunho → enviado → confirmado →
-- enviado_para_entrega → entregue / cancelado. Service-layer enforces
-- transitions (don't model state via flags; single status column).
-- ============================================================================

CREATE TABLE adconnect.carts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE CASCADE,
    created_by UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'abandonado', 'convertido')),
    total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adconnect.carts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "carts_distrib_users_see_own" ON adconnect.carts
    FOR ALL TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "carts_brand_admin_sees_all" ON adconnect.carts
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = carts.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_carts_distributor ON adconnect.carts(distributor_id);
CREATE INDEX idx_adconnect_carts_status ON adconnect.carts(status) WHERE status = 'ativo';


CREATE TABLE adconnect.itens_carrinho (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL REFERENCES adconnect.carts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES adconnect.products(id) ON DELETE RESTRICT,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    price_at_add NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cart_id, product_id)
);

ALTER TABLE adconnect.itens_carrinho ENABLE ROW LEVEL SECURITY;

CREATE POLICY "itens_carrinho_via_cart" ON adconnect.itens_carrinho
    FOR ALL TO authenticated
    USING (
        cart_id IN (
            SELECT c.id FROM adconnect.carts c
            WHERE c.distributor_id IN (
                SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
                WHERE dm.user_id = (SELECT auth.uid())
            )
        )
    );

CREATE INDEX idx_adconnect_itens_carrinho_cart ON adconnect.itens_carrinho(cart_id);
CREATE INDEX idx_adconnect_itens_carrinho_product ON adconnect.itens_carrinho(product_id);


CREATE TABLE adconnect.pedidos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE RESTRICT,
    cart_id UUID REFERENCES adconnect.carts(id) ON DELETE SET NULL,
    placed_by UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN (
        'rascunho', 'enviado', 'confirmado', 'enviado_para_entrega', 'entregue', 'cancelado'
    )),
    total NUMERIC(12, 2) NOT NULL,
    observacoes TEXT,
    placed_at TIMESTAMPTZ,
    confirmed_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adconnect.pedidos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pedidos_distrib_users_see_own" ON adconnect.pedidos
    FOR ALL TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "pedidos_brand_admin_sees_all" ON adconnect.pedidos
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = pedidos.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_pedidos_distributor ON adconnect.pedidos(distributor_id);
CREATE INDEX idx_adconnect_pedidos_status ON adconnect.pedidos(status);
CREATE INDEX idx_adconnect_pedidos_placed_at ON adconnect.pedidos(placed_at DESC);


CREATE TABLE adconnect.itens_pedido (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pedido_id UUID NOT NULL REFERENCES adconnect.pedidos(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES adconnect.products(id) ON DELETE RESTRICT,
    sku_at_order TEXT NOT NULL,
    nome_at_order TEXT NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    price_at_order NUMERIC(12, 2) NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adconnect.itens_pedido ENABLE ROW LEVEL SECURITY;

CREATE POLICY "itens_pedido_via_pedido" ON adconnect.itens_pedido
    FOR ALL TO authenticated
    USING (
        pedido_id IN (
            SELECT p.id FROM adconnect.pedidos p
            WHERE p.distributor_id IN (
                SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
                WHERE dm.user_id = (SELECT auth.uid())
            )
        )
    );

CREATE INDEX idx_adconnect_itens_pedido_pedido ON adconnect.itens_pedido(pedido_id);
CREATE INDEX idx_adconnect_itens_pedido_product ON adconnect.itens_pedido(product_id);


-- ============================================================================
-- 6. REWARDS — regras_recompensa + recompensas_acumuladas + resgates_recompensa
-- Reward engine lives at app/services/rewards_service.py — pure function on
-- top of DB rows: matches relatorio_sellout / pedido against regras_recompensa,
-- writes recompensas_acumuladas rows. Testable in isolation per PROJECT.md
-- §6 Phase 4.
-- ============================================================================

CREATE TABLE adconnect.regras_recompensa (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN ('cashback_percentual', 'cashback_fixo', 'pontos')),
    valor NUMERIC(12, 4) NOT NULL,
    aplicavel_categorias UUID[] NOT NULL DEFAULT '{}',
    aplicavel_produtos UUID[] NOT NULL DEFAULT '{}',
    aplicavel_distribuidores UUID[] NOT NULL DEFAULT '{}',
    valor_minimo_pedido NUMERIC(12, 2),
    quantidade_minima INTEGER,
    valido_de TIMESTAMPTZ,
    valido_ate TIMESTAMPTZ,
    ativa BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adconnect.regras_recompensa ENABLE ROW LEVEL SECURITY;

CREATE POLICY "regras_select_own_org" ON adconnect.regras_recompensa
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_adconnect_regras_org ON adconnect.regras_recompensa(org_id);
CREATE INDEX idx_adconnect_regras_ativa ON adconnect.regras_recompensa(org_id, ativa) WHERE ativa = true;


CREATE TABLE adconnect.recompensas_acumuladas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE RESTRICT,
    regra_id UUID NOT NULL REFERENCES adconnect.regras_recompensa(id) ON DELETE RESTRICT,
    -- Source: at most one of these is non-null (a reward is triggered by
    -- either an order placement or an approved sellout report).
    source_pedido_id UUID REFERENCES adconnect.pedidos(id) ON DELETE SET NULL,
    source_relatorio_sellout_id UUID REFERENCES adconnect.relatorios_sellout(id) ON DELETE SET NULL,
    valor NUMERIC(12, 2) NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('cashback', 'pontos')),
    status TEXT NOT NULL DEFAULT 'acumulado' CHECK (status IN ('acumulado', 'resgatado', 'expirado')),
    accrued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (source_pedido_id IS NOT NULL AND source_relatorio_sellout_id IS NULL) OR
        (source_pedido_id IS NULL AND source_relatorio_sellout_id IS NOT NULL)
    )
);

ALTER TABLE adconnect.recompensas_acumuladas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "recompensas_distrib_users_see_own" ON adconnect.recompensas_acumuladas
    FOR ALL TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "recompensas_brand_admin_sees_all" ON adconnect.recompensas_acumuladas
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = recompensas_acumuladas.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_recompensas_distributor ON adconnect.recompensas_acumuladas(distributor_id);
CREATE INDEX idx_adconnect_recompensas_status ON adconnect.recompensas_acumuladas(distributor_id, status);
CREATE INDEX idx_adconnect_recompensas_source_pedido ON adconnect.recompensas_acumuladas(source_pedido_id) WHERE source_pedido_id IS NOT NULL;
CREATE INDEX idx_adconnect_recompensas_source_sellout ON adconnect.recompensas_acumuladas(source_relatorio_sellout_id) WHERE source_relatorio_sellout_id IS NOT NULL;


CREATE TABLE adconnect.resgates_recompensa (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE RESTRICT,
    requested_by UUID NOT NULL,
    valor_total NUMERIC(12, 2) NOT NULL CHECK (valor_total > 0),
    metodo TEXT NOT NULL CHECK (metodo IN ('credito_em_pedido', 'credito_em_fatura', 'reembolso_pix', 'outro')),
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aprovado', 'recusado', 'pago')),
    observacoes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);

ALTER TABLE adconnect.resgates_recompensa ENABLE ROW LEVEL SECURITY;

CREATE POLICY "resgates_distrib_users_see_own" ON adconnect.resgates_recompensa
    FOR ALL TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "resgates_brand_admin_sees_all" ON adconnect.resgates_recompensa
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = resgates_recompensa.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_resgates_distributor ON adconnect.resgates_recompensa(distributor_id);
CREATE INDEX idx_adconnect_resgates_status ON adconnect.resgates_recompensa(status);


-- ============================================================================
-- 7. FINANCIAL — faturas
-- AdConnect emits its own invoices (NF-e generation). Stripe processing
-- is INHERITED from products/core/backend/app/services/stripe_service.py;
-- this table records the AdConnect-side fatura with NF-e XML and the
-- stripe_invoice_id reference. SDK calls live in core, not here.
-- ============================================================================

CREATE TABLE adconnect.faturas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id UUID NOT NULL REFERENCES adconnect.distributors(id) ON DELETE RESTRICT,
    pedido_id UUID REFERENCES adconnect.pedidos(id) ON DELETE SET NULL,
    numero_fatura TEXT NOT NULL UNIQUE,
    valor_total NUMERIC(12, 2) NOT NULL CHECK (valor_total >= 0),
    moeda TEXT NOT NULL DEFAULT 'BRL',
    -- NF-e generation (Phase 5 wires the provider — Focus NFe per
    -- PROJECT.md §7 q1; Protocol-wrapped in app/services/nfe_service.py):
    nfe_xml TEXT,
    nfe_xml_url TEXT,
    nfe_chave TEXT,
    nfe_status TEXT NOT NULL DEFAULT 'pendente' CHECK (nfe_status IN (
        'pendente', 'enviado', 'autorizado', 'rejeitado', 'cancelado'
    )),
    nfe_provider TEXT,
    nfe_provider_id TEXT,
    -- Stripe inheritance (the SDK calls happen in products/core):
    stripe_invoice_id TEXT,
    stripe_customer_id TEXT,
    stripe_payment_intent_id TEXT,
    -- Lifecycle:
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN (
        'rascunho', 'emitida', 'paga', 'vencida', 'cancelada', 'estornada'
    )),
    issued_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    due_date DATE,
    canceled_at TIMESTAMPTZ,
    observacoes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE adconnect.faturas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "faturas_distrib_users_see_own" ON adconnect.faturas
    FOR SELECT TO authenticated
    USING (
        distributor_id IN (
            SELECT dm.distributor_id FROM adconnect.distributor_memberships dm
            WHERE dm.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY "faturas_brand_admin_sees_all" ON adconnect.faturas
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM adconnect.distributors d
            WHERE d.id = faturas.distributor_id
              AND d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_adconnect_faturas_distributor ON adconnect.faturas(distributor_id);
CREATE INDEX idx_adconnect_faturas_pedido ON adconnect.faturas(pedido_id);
CREATE INDEX idx_adconnect_faturas_status ON adconnect.faturas(status);
CREATE INDEX idx_adconnect_faturas_due_date ON adconnect.faturas(due_date) WHERE status IN ('emitida', 'vencida');
CREATE INDEX idx_adconnect_faturas_stripe_invoice ON adconnect.faturas(stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL;
CREATE INDEX idx_adconnect_faturas_nfe_chave ON adconnect.faturas(nfe_chave) WHERE nfe_chave IS NOT NULL;


-- ============================================================================
-- 8. SEED ROWS — status_pagina entries
-- ============================================================================

INSERT INTO adconnect.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao'),
    ('catalog', 'desenvolvimento'),
    ('product_detail', 'desenvolvimento'),
    ('cart', 'desenvolvimento'),
    ('checkout', 'desenvolvimento'),
    ('orders', 'desenvolvimento'),
    ('order_detail', 'desenvolvimento'),
    ('sellout_submit', 'desenvolvimento'),
    ('sellout_history', 'desenvolvimento'),
    ('rewards_ledger', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/daily-life/backend/migrations/001_daily_life.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- Daily Life Product schema
-- Schema: daily_life
-- Description: Personal productivity hub — tasks, goals, habits, schedule,
--              notes, automations, and performance tracking.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS daily_life;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA daily_life TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA daily_life TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA daily_life TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE daily_life.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE daily_life.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON daily_life.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE daily_life.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON daily_life.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_dl_invitations_org ON daily_life.invitations(org_id);
CREATE INDEX idx_dl_invitations_token ON daily_life.invitations(token);


-- ============================================================================
-- Tasks (Tarefas)
-- ============================================================================

CREATE TABLE daily_life.tarefas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    prioridade TEXT NOT NULL DEFAULT 'media' CHECK (prioridade IN ('alta', 'media', 'baixa')),
    prioridade_ordem INT NOT NULL DEFAULT 2,
    categoria TEXT,
    data_vencimento DATE,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'em_progresso', 'concluida', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.tarefas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tarefas_select_own" ON daily_life.tarefas
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "tarefas_insert_own" ON daily_life.tarefas
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "tarefas_update_own" ON daily_life.tarefas
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "tarefas_delete_own" ON daily_life.tarefas
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_tarefas_user ON daily_life.tarefas(user_id);
CREATE INDEX idx_dl_tarefas_user_status ON daily_life.tarefas(user_id, status);
CREATE INDEX idx_dl_tarefas_org ON daily_life.tarefas(org_id);


-- ============================================================================
-- Goals & Habits (Metas)
-- ============================================================================

CREATE TABLE daily_life.metas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    tipo TEXT NOT NULL DEFAULT 'meta' CHECK (tipo IN ('meta', 'habito')),
    categoria TEXT,
    meta_valor NUMERIC,
    valor_atual NUMERIC DEFAULT 0,
    unidade TEXT,
    frequencia TEXT CHECK (frequencia IS NULL OR frequencia IN ('diario', 'semanal', 'mensal')),
    data_limite DATE,
    status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'concluida', 'pausada', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.metas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "metas_select_own" ON daily_life.metas
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "metas_insert_own" ON daily_life.metas
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "metas_update_own" ON daily_life.metas
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "metas_delete_own" ON daily_life.metas
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_metas_user ON daily_life.metas(user_id);
CREATE INDEX idx_dl_metas_user_tipo ON daily_life.metas(user_id, tipo);


-- ============================================================================
-- Habit Check-Ins
-- ============================================================================

CREATE TABLE daily_life.checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meta_id UUID NOT NULL REFERENCES daily_life.metas(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    valor NUMERIC DEFAULT 1,
    nota TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(meta_id, data)
);

ALTER TABLE daily_life.checkins ENABLE ROW LEVEL SECURITY;

CREATE POLICY "checkins_select_own" ON daily_life.checkins
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "checkins_insert_own" ON daily_life.checkins
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_checkins_meta ON daily_life.checkins(meta_id);
CREATE INDEX idx_dl_checkins_user_data ON daily_life.checkins(user_id, data);


-- ============================================================================
-- Calendar Events (Eventos)
-- ============================================================================

CREATE TABLE daily_life.eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    categoria TEXT,
    data_inicio TIMESTAMPTZ NOT NULL,
    data_fim TIMESTAMPTZ,
    dia_inteiro BOOLEAN DEFAULT FALSE,
    local TEXT,
    lembrete_minutos INT,
    cor TEXT,
    status TEXT NOT NULL DEFAULT 'agendado' CHECK (status IN ('agendado', 'concluido', 'cancelado')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.eventos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "eventos_select_own" ON daily_life.eventos
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "eventos_insert_own" ON daily_life.eventos
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "eventos_update_own" ON daily_life.eventos
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "eventos_delete_own" ON daily_life.eventos
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_eventos_user ON daily_life.eventos(user_id);
CREATE INDEX idx_dl_eventos_user_data ON daily_life.eventos(user_id, data_inicio);
CREATE INDEX idx_dl_eventos_org ON daily_life.eventos(org_id);


-- ============================================================================
-- Notes (Notas)
-- ============================================================================

CREATE TABLE daily_life.notas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    conteudo TEXT,
    categoria TEXT,
    tags TEXT[] DEFAULT '{}',
    fixada BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.notas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notas_select_own" ON daily_life.notas
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "notas_insert_own" ON daily_life.notas
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "notas_update_own" ON daily_life.notas
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "notas_delete_own" ON daily_life.notas
    FOR DELETE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_notas_user ON daily_life.notas(user_id);
CREATE INDEX idx_dl_notas_user_fixada ON daily_life.notas(user_id, fixada);


-- ============================================================================
-- Productivity Metrics (daily snapshots)
-- ============================================================================

CREATE TABLE daily_life.metricas_produtividade (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    tarefas_concluidas INT DEFAULT 0,
    tarefas_criadas INT DEFAULT 0,
    checkins_realizados INT DEFAULT 0,
    eventos_do_dia INT DEFAULT 0,
    notas_criadas INT DEFAULT 0,
    score_produtividade NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, data)
);

ALTER TABLE daily_life.metricas_produtividade ENABLE ROW LEVEL SECURITY;

CREATE POLICY "metricas_select_own" ON daily_life.metricas_produtividade
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "metricas_insert_own" ON daily_life.metricas_produtividade
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "metricas_update_own" ON daily_life.metricas_produtividade
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_metricas_user_data ON daily_life.metricas_produtividade(user_id, data);


-- ============================================================================
-- Focus Sessions (Pomodoro / Deep Work)
-- ============================================================================

CREATE TABLE daily_life.sessoes_foco (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tarefa_id UUID REFERENCES daily_life.tarefas(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL DEFAULT 'pomodoro' CHECK (tipo IN ('pomodoro', 'deep_work', 'livre')),
    duracao_minutos INT NOT NULL,
    inicio TIMESTAMPTZ NOT NULL,
    fim TIMESTAMPTZ,
    nota TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daily_life.sessoes_foco ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sessoes_select_own" ON daily_life.sessoes_foco
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY "sessoes_insert_own" ON daily_life.sessoes_foco
    FOR INSERT TO authenticated
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "sessoes_update_own" ON daily_life.sessoes_foco
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE INDEX idx_dl_sessoes_user ON daily_life.sessoes_foco(user_id);
CREATE INDEX idx_dl_sessoes_user_inicio ON daily_life.sessoes_foco(user_id, inicio);


-- ============================================================================
-- Auto-update timestamps trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION daily_life.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = daily_life
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER tarefas_updated_at BEFORE UPDATE ON daily_life.tarefas
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();

CREATE TRIGGER metas_updated_at BEFORE UPDATE ON daily_life.metas
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();

CREATE TRIGGER eventos_updated_at BEFORE UPDATE ON daily_life.eventos
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();

CREATE TRIGGER notas_updated_at BEFORE UPDATE ON daily_life.notas
    FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();


-- ============================================================================
-- Command knowledge tables (CLI learning system)
-- ============================================================================

CREATE TABLE daily_life.commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('exact', 'pattern', 'alias')),
    handler TEXT NOT NULL,
    parameters JSONB DEFAULT '{}',
    description TEXT,
    category TEXT,
    examples TEXT[] DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.commands ENABLE ROW LEVEL SECURITY;
CREATE POLICY "commands_service" ON daily_life.commands FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "commands_read" ON daily_life.commands FOR SELECT TO authenticated USING (true);
CREATE INDEX idx_dl_commands_type ON daily_life.commands(type);
CREATE INDEX idx_dl_commands_trigger ON daily_life.commands(trigger);

CREATE TABLE daily_life.intent_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL DEFAULT 'keyword' CHECK (pattern_type IN ('regex', 'keyword', 'fuzzy')),
    mapped_command_id UUID REFERENCES daily_life.commands(id) ON DELETE CASCADE,
    handler TEXT,
    parameter_extraction JSONB DEFAULT '{}',
    confidence_threshold NUMERIC DEFAULT 0.8,
    examples TEXT[] DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.intent_patterns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "patterns_service" ON daily_life.intent_patterns FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "patterns_read" ON daily_life.intent_patterns FOR SELECT TO authenticated USING (true);

CREATE TABLE daily_life.context_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('contact', 'location', 'default', 'alias', 'preference')),
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.context_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "context_all" ON daily_life.context_rules FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_context_user_type ON daily_life.context_rules(user_id, rule_type);

CREATE TABLE daily_life.command_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    raw_input TEXT NOT NULL,
    resolved_command TEXT,
    resolved_handler TEXT,
    tier_used TEXT NOT NULL CHECK (tier_used IN ('direct', 'pattern', 'llm', 'failed')),
    parameters JSONB DEFAULT '{}',
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    execution_time_ms INT,
    tokens_used INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.command_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "history_all" ON daily_life.command_history FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_history_user ON daily_life.command_history(user_id);
CREATE INDEX idx_dl_history_created ON daily_life.command_history(created_at);
CREATE INDEX idx_dl_history_tier ON daily_life.command_history(tier_used);

CREATE TABLE daily_life.learned_promotions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_history_id UUID REFERENCES daily_life.command_history(id) ON DELETE SET NULL,
    raw_input TEXT NOT NULL,
    extracted_intent TEXT NOT NULL,
    extracted_handler TEXT NOT NULL,
    extracted_parameters JSONB DEFAULT '{}',
    suggested_pattern TEXT,
    suggested_pattern_type TEXT DEFAULT 'keyword' CHECK (suggested_pattern_type IN ('regex', 'keyword', 'fuzzy')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'auto_approved')),
    occurrences INT DEFAULT 1,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_to_pattern_id UUID REFERENCES daily_life.intent_patterns(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.learned_promotions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "promotions_all" ON daily_life.learned_promotions FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_promotions_user_status ON daily_life.learned_promotions(user_id, status);
CREATE INDEX idx_dl_promotions_intent ON daily_life.learned_promotions(extracted_intent);

CREATE TRIGGER commands_updated_at BEFORE UPDATE ON daily_life.commands FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
CREATE TRIGGER context_updated_at BEFORE UPDATE ON daily_life.context_rules FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO daily_life.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('tarefas', 'producao'),
    ('metas', 'producao'),
    ('agenda', 'producao'),
    ('notas', 'producao'),
    ('foco', 'producao'),
    ('metricas', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/dev-team/backend/migrations/0001_init_telemetry_events.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- 0001 — dev-team telemetry events
--
-- Postgres mirror of the engine's SQLite schema (dev_team/src/dev_team/
-- memory/store/telemetry.sqlite). The local SQLite stays for single-tenant
-- CLI / MCP usage; this Postgres table backs the multi-tenant product API.
--
-- Schema reference: projects/agno-dev-team-rollout/PROJECT.md §5.4
--
-- RLS pattern follows the canonical org_id-from-JWT shape used across the
-- platform (see products/mailing/backend/migrations/002_ai_outputs.sql for
-- the reference). Each event is tagged with the writer's org_id; reads
-- scoped by `org_id = (jwt -> 'org_id')::uuid`.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS dev_team;

GRANT USAGE ON SCHEMA dev_team TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA dev_team TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA dev_team TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA dev_team
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA dev_team
    GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- 1. Standard platform table — page status (feature flags)
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.status_pagina (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina  TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'producao'
                   CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao    TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE dev_team.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON dev_team.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- 2. Standard platform table — invitations
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.invitations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member',
    invited_by  UUID NOT NULL,
    token       TEXT UNIQUE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE dev_team.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON dev_team.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX IF NOT EXISTS idx_dev_team_invitations_org
    ON dev_team.invitations (org_id);
CREATE INDEX IF NOT EXISTS idx_dev_team_invitations_token
    ON dev_team.invitations (token);


-- ============================================================================
-- 3. Telemetry events — every agent turn captured for measurability
--
-- Mirrors `dev_team/src/dev_team/memory/store/telemetry.sqlite`'s `events`
-- table. The product writes one row per agno turn; reads serve the metrics
-- API (/api/metrics, /api/agents/{name}/metrics) and the future dashboard.
-- ============================================================================

CREATE TABLE IF NOT EXISTS dev_team.dev_team_telemetry_events (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID NOT NULL DEFAULT public.current_org_id(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    project         TEXT,                 -- project slug, nullable
    config_name     TEXT NOT NULL,        -- which YAML config was active
    agent_name      TEXT NOT NULL,        -- e.g. "backend_engineer"
    sub_team        TEXT,                 -- "design_review_team" / null
    turn_index      INTEGER NOT NULL,     -- per-task turn counter
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    total_cost_usd  NUMERIC(10, 6) NOT NULL,
    latency_ms      INTEGER NOT NULL,
    tool_calls      JSONB,                -- list of {name, args, latency_ms}
    outcome         TEXT NOT NULL CHECK (outcome IN ('ok', 'error', 'timeout')),
    output_chars    INTEGER NOT NULL,
    task_hash       TEXT                  -- sha1 of the task string for grouping
);

CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_org_agent
    ON dev_team.dev_team_telemetry_events (org_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_org_project
    ON dev_team.dev_team_telemetry_events (org_id, project);
CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_timestamp
    ON dev_team.dev_team_telemetry_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_dev_team_telemetry_task_hash
    ON dev_team.dev_team_telemetry_events (task_hash);

ALTER TABLE dev_team.dev_team_telemetry_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "telemetry_events_own_org" ON dev_team.dev_team_telemetry_events
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

COMMENT ON TABLE dev_team.dev_team_telemetry_events IS
    'Per-tenant mirror of the engine SQLite events table. One row per agno turn. Read by /api/metrics + /api/agents/{name}/metrics; written by the product when /api/run dispatches the team.';

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- =====================================================================
-- ERP Imobiliário — Consolidated Schema Migration
-- Merged from 87 incremental migration files into a single idempotent script.
-- Run this once on a fresh Supabase project.
--
-- All ERP objects live in the `erp` schema. Core platform tables stay in `public`.
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- 0. SCHEMA + PERMISSIONS
-- ─────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS erp;

GRANT USAGE ON SCHEMA erp TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA erp TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- ─────────────────────────────────────────────────────────────────────
-- 1. EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- ─────────────────────────────────────────────────────────────────────
-- 2. ENUMS
-- ─────────────────────────────────────────────────────────────────────

CREATE TYPE erp.tipo_meta AS ENUM ('diaria', 'semanal', 'mensal', 'anual');

CREATE TYPE erp.status_meta AS ENUM ('aberta', 'concluida', 'atrasada', 'no_prazo', 'vence_amanha');

CREATE TYPE erp.app_role AS ENUM ('admin', 'corretor', 'coordenador', 'dev');

CREATE TYPE erp.categoria_meta AS ENUM (
  'captacao', 'visitas', 'contatos', 'propostas', 'fechamento',
  'captacao_imoveis', 'captacao_compradores', 'atualizacao_imoveis', 'outro'
);

CREATE TYPE erp.conclusao_prazo_meta AS ENUM ('no_prazo', 'atrasada');

CREATE TYPE erp.nivel_performance_meta AS ENUM ('baixo', 'regular', 'bom', 'excelente');

CREATE TYPE erp.etapa_funil AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado');

CREATE TYPE erp.tipo_atividade AS ENUM ('ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro');

CREATE TYPE erp.status_negociacao AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado', 'cancelado');

CREATE TYPE erp.tipo_acao AS ENUM (
  'criar', 'editar', 'excluir', 'concluir',
  'arquivar', 'desarquivar', 'mover', 'login', 'logout'
);

CREATE TYPE erp.tipo_entidade AS ENUM (
  'meta', 'cliente', 'usuario', 'atividade', 'config_meta', 'auth',
  'negociacao', 'match', 'condominio', 'ativo'
);

CREATE TYPE erp.status_match AS ENUM ('pendente', 'aceito', 'rejeitado', 'expirado');

-- ─────────────────────────────────────────────────────────────────────
-- 3. SEQUENCES
-- ─────────────────────────────────────────────────────────────────────

CREATE SEQUENCE IF NOT EXISTS erp.metas_id_seq;
CREATE SEQUENCE IF NOT EXISTS erp.negociacoes_id_seq START WITH 1;

-- ─────────────────────────────────────────────────────────────────────
-- 4. UTILITY FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- Timestamp helpers (São Paulo timezone)
CREATE OR REPLACE FUNCTION erp.current_date_sao_paulo()
RETURNS DATE
LANGUAGE SQL STABLE
SET search_path = erp, public
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

CREATE OR REPLACE FUNCTION erp.now_sao_paulo()
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL STABLE
SET search_path = erp, public
AS $$ SELECT NOW() AT TIME ZONE 'America/Sao_Paulo'; $$;

CREATE OR REPLACE FUNCTION erp.normalize_timestamp_sp(ts TIMESTAMP WITH TIME ZONE)
RETURNS TIMESTAMP WITH TIME ZONE
LANGUAGE SQL IMMUTABLE
SET search_path = erp, public
AS $$ SELECT ts AT TIME ZONE 'America/Sao_Paulo'; $$;

-- Generic updated_at trigger
CREATE OR REPLACE FUNCTION erp.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- São Paulo timestamp trigger for created_at/updated_at
CREATE OR REPLACE FUNCTION erp.set_timestamps_sp()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE
  has_updated_at boolean;
BEGIN
  -- Check if the table has an updated_at column (safe for all tables)
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = TG_TABLE_SCHEMA
      AND table_name = TG_TABLE_NAME
      AND column_name = 'updated_at'
  ) INTO has_updated_at;

  IF TG_OP = 'INSERT' THEN
    NEW.created_at := now_sao_paulo();
    IF has_updated_at THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF has_updated_at THEN
      NEW.updated_at := now_sao_paulo();
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- ID generators (sequence-based, concurrency-safe)
CREATE OR REPLACE FUNCTION erp.generate_meta_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.metas_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'MT' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'MT' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

CREATE OR REPLACE FUNCTION erp.generate_negociacao_id()
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE next_number INTEGER; next_id TEXT;
BEGIN
  next_number := nextval('erp.negociacoes_id_seq')::INTEGER;
  IF next_number <= 9999 THEN
    next_id := 'NG' || LPAD(next_number::TEXT, 4, '0');
  ELSE
    next_id := 'NG' || next_number::TEXT;
  END IF;
  RETURN next_id;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 5. TABLES
-- ─────────────────────────────────────────────────────────────────────

-- 5a. Profiles (linked to auth.users)
CREATE TABLE erp.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  email TEXT NOT NULL,
  telefone TEXT NOT NULL,
  avatar TEXT,
  tema TEXT NOT NULL DEFAULT 'light' CHECK (tema IN ('light', 'dark')),
  last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5b. User roles
CREATE TABLE erp.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  role app_role NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);

-- Role check helper (stays in public — used by RLS policies and auth context)
CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role erp.app_role)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM erp.user_roles WHERE user_id = _user_id AND role = _role); $$;

-- 5c. Metas (goals) — fully merged with all incremental columns
CREATE TABLE erp.metas (
  id TEXT PRIMARY KEY DEFAULT erp.generate_meta_id(),
  usuario_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
  tipo erp.tipo_meta NOT NULL,
  categoria erp.categoria_meta NOT NULL DEFAULT 'captacao',
  categoria_custom TEXT,
  nome TEXT,
  detalhes TEXT,
  meta_pretendida INTEGER NOT NULL,
  meta_realizada INTEGER DEFAULT 0,
  data_prazo DATE NOT NULL,
  status erp.status_meta DEFAULT 'aberta' NOT NULL,
  carry_in INTEGER NOT NULL DEFAULT 0,
  carry_out INTEGER NOT NULL DEFAULT 0,
  conclusao_prazo erp.conclusao_prazo_meta NOT NULL DEFAULT 'no_prazo',
  nivel_performance erp.nivel_performance_meta NOT NULL DEFAULT 'baixo',
  dias_restantes INTEGER,
  tem_impedimento BOOLEAN NOT NULL DEFAULT false,
  motivo_impedimento TEXT,
  criada_manualmente BOOLEAN NOT NULL DEFAULT false,
  finalizada_em TIMESTAMP WITH TIME ZONE,
  finalizada_no_prazo BOOLEAN,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT check_motivo_impedimento CHECK (
    (tem_impedimento = false) OR
    (tem_impedimento = true AND motivo_impedimento IS NOT NULL AND trim(motivo_impedimento) <> '')
  )
);

-- 5d. Metas config (monthly targets)
CREATE TABLE erp.metas_config (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  usuario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo tipo_meta NOT NULL,
  categoria categoria_meta NOT NULL,
  categoria_custom TEXT,
  meta_pretendida INTEGER NOT NULL DEFAULT 0,
  ativo BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  UNIQUE(usuario_id, tipo, categoria)
);

-- 5e. Clientes (CRM)
CREATE TABLE erp.clientes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES erp.profiles(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  email TEXT UNIQUE,
  telefone TEXT,
  origem TEXT,
  interesse TEXT,
  observacoes TEXT,
  etapa_atual etapa_funil NOT NULL DEFAULT 'qualificacao',
  probabilidade INTEGER NOT NULL DEFAULT 10 CHECK (probabilidade >= 0 AND probabilidade <= 100),
  valor_estimado NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_estimado >= 0),
  arquivado BOOLEAN NOT NULL DEFAULT false,
  kanban_pos INTEGER NOT NULL DEFAULT 0,
  lead_score INTEGER CHECK (lead_score >= 0 AND lead_score <= 100),
  lead_score_justificativa TEXT,
  lead_score_updated_at TIMESTAMPTZ,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5f. Funil movimentos (funnel history)
CREATE TABLE erp.funil_movimentos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES erp.clientes(id) ON DELETE CASCADE,
  de_etapa etapa_funil,
  para_etapa etapa_funil NOT NULL,
  responsavel_id UUID NOT NULL REFERENCES erp.profiles(id),
  motivo TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5g. Atividades (activities)
CREATE TABLE erp.atividades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES erp.clientes(id) ON DELETE CASCADE,
  usuario_id UUID NOT NULL REFERENCES erp.profiles(id),
  tipo tipo_atividade NOT NULL DEFAULT 'outro',
  descricao TEXT NOT NULL,
  data_execucao TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5h. Password request codes (admin temporary passwords)
CREATE TABLE erp.password_request_codes (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  admin_user_id UUID NOT NULL,
  corretor_id UUID NOT NULL,
  code TEXT NOT NULL,
  temp_password TEXT NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5i. Status pagina (feature flags)
CREATE TABLE erp.status_pagina (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_pagina TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento')),
  descricao TEXT,
  tipo_pagina TEXT NOT NULL DEFAULT 'geral',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5j. User actions log (audit trail)
CREATE TABLE erp.user_actions_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo_acao tipo_acao NOT NULL,
  tipo_entidade tipo_entidade NOT NULL,
  entidade_id TEXT,
  descricao TEXT NOT NULL,
  detalhes JSONB,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 5k. Negociações (negotiations) — FK to ativos added after ativos table creation
CREATE TABLE erp.negociacoes (
  id TEXT PRIMARY KEY DEFAULT generate_negociacao_id(),
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  ativo_origem_id UUID NOT NULL,
  ativo_destino_id UUID NOT NULL,
  cliente_proprietario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  cliente_ofertante_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  valor_imovel NUMERIC(12,2) NOT NULL,
  valor_permuta NUMERIC(12,2) NOT NULL,
  valor_complemento NUMERIC(12,2) DEFAULT 0,
  status_etapa status_negociacao NOT NULL DEFAULT 'qualificacao',
  timeline JSONB DEFAULT '[]'::JSONB,
  observacoes TEXT
);

-- 5l. Condominios
CREATE TABLE erp.condominios (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  endereco TEXT,
  bairro TEXT,
  cidade TEXT,
  estado TEXT,
  cep TEXT,
  valor_condominio NUMERIC DEFAULT 0,
  sindico TEXT,
  telefone_sindico TEXT,
  administradora TEXT,
  torres INTEGER,
  unidades_por_andar INTEGER,
  total_unidades INTEGER,
  possui_portaria BOOLEAN DEFAULT false,
  possui_piscina BOOLEAN DEFAULT false,
  possui_academia BOOLEAN DEFAULT false,
  possui_salao_festas BOOLEAN DEFAULT false,
  possui_playground BOOLEAN DEFAULT false,
  possui_churrasqueira BOOLEAN DEFAULT false,
  observacoes TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- 5l. Matches (computed matches between ativos)
CREATE TABLE erp.matches (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ativo_origem_id UUID NOT NULL,
  ativo_destino_id UUID NOT NULL,
  score NUMERIC(5,1) NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
  status status_match NOT NULL DEFAULT 'pendente',
  justificativa TEXT,
  detalhes JSONB DEFAULT '{}'::JSONB,
  score_breakdown JSONB DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE(ativo_origem_id, ativo_destino_id)
);

-- 5q. Ativos (unified assets: imóveis + permutas)
CREATE TABLE erp.ativos (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  natureza TEXT NOT NULL CHECK (natureza IN ('imovel', 'permuta_imovel', 'permuta_automovel')),
  -- Shared fields
  valor NUMERIC NOT NULL DEFAULT 0,
  status TEXT DEFAULT 'ativo',
  observacoes TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  -- Property fields (imovel + permuta_imovel)
  tipo_imovel TEXT,
  cep TEXT,
  logradouro TEXT,
  numero TEXT,
  complemento TEXT,
  bairro TEXT,
  cidade TEXT,
  estado TEXT,
  zona TEXT,
  condominio_id UUID REFERENCES condominios(id) ON DELETE SET NULL,
  condominio_nome TEXT,
  area_privativa NUMERIC,
  area_total NUMERIC,
  quartos INTEGER,
  suites INTEGER,
  banheiros INTEGER,
  vagas INTEGER,
  andar INTEGER,
  ano_construcao INTEGER,
  -- Imóvel-only fields
  ref TEXT,
  corretor TEXT,
  proprietario_id UUID REFERENCES clientes(id) ON DELETE SET NULL,
  aceita_permutas BOOLEAN DEFAULT false,
  finalidade TEXT DEFAULT 'venda',
  iptu NUMERIC,
  pronto_para_portais BOOLEAN DEFAULT false,
  titulo_anuncio TEXT,
  descricao_seo TEXT,
  fotos TEXT[],
  plantas TEXT[],
  palavras_chave TEXT[],
  pontos_de_interesse TEXT[],
  tour_virtual_url TEXT,
  latitude NUMERIC,
  longitude NUMERIC,
  lqs_score_hint TEXT,
  observacoes_negociacao TEXT,
  interesses JSONB DEFAULT '[]'::JSONB,
  -- Vehicle fields (permuta_automovel)
  tipo_veiculo TEXT,
  marca TEXT,
  modelo TEXT,
  motor TEXT,
  ano INTEGER,
  quilometragem INTEGER,
  -- Permuta flexibility fields
  faixa_preco_min NUMERIC,
  faixa_preco_max NUMERIC,
  regiao_preferida TEXT[],
  aceita_completar_diferenca BOOLEAN DEFAULT false,
  limite_complemento NUMERIC,
  metragem_min NUMERIC,
  metragem_max NUMERIC,
  quartos_min INTEGER,
  vagas_min INTEGER,
  ano_min INTEGER,
  ano_max INTEGER,
  quilometragem_max INTEGER,
  -- AI matching fields (pgvector)
  embedding extensions.vector(1536),
  interesses_descricao TEXT
);

-- Add FK constraints from matches to ativos
ALTER TABLE erp.matches
  ADD CONSTRAINT matches_ativo_origem_id_fkey FOREIGN KEY (ativo_origem_id) REFERENCES erp.ativos(id) ON DELETE CASCADE,
  ADD CONSTRAINT matches_ativo_destino_id_fkey FOREIGN KEY (ativo_destino_id) REFERENCES erp.ativos(id) ON DELETE CASCADE;

-- Add FK constraints from negociacoes to ativos
ALTER TABLE erp.negociacoes
  ADD CONSTRAINT negociacoes_ativo_origem_id_fkey FOREIGN KEY (ativo_origem_id) REFERENCES erp.ativos(id) ON DELETE CASCADE,
  ADD CONSTRAINT negociacoes_ativo_destino_id_fkey FOREIGN KEY (ativo_destino_id) REFERENCES erp.ativos(id) ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────────────
-- 6. INDEXES
-- ─────────────────────────────────────────────────────────────────────

-- Metas
CREATE INDEX idx_metas_usuario_tipo_data ON erp.metas(usuario_id, tipo, data_prazo);
CREATE INDEX idx_metas_usuario_tipo_categoria_data ON erp.metas(usuario_id, tipo, categoria, data_prazo);
CREATE INDEX idx_metas_categoria ON erp.metas(categoria);
CREATE INDEX idx_metas_categoria_custom ON erp.metas(categoria_custom);
CREATE INDEX idx_metas_tem_impedimento ON erp.metas(tem_impedimento) WHERE tem_impedimento = true;
CREATE INDEX idx_metas_nome ON erp.metas(nome);

-- Metas config
CREATE INDEX idx_metas_config_categoria_custom ON erp.metas_config(categoria_custom);

-- Profiles
CREATE INDEX idx_profiles_last_activity ON erp.profiles(last_activity_at);

-- Clientes
CREATE INDEX idx_clientes_etapa_pos ON erp.clientes(etapa_atual, kanban_pos);
CREATE INDEX idx_clientes_owner ON erp.clientes(usuario_id, arquivado);
CREATE INDEX idx_clientes_busca ON erp.clientes USING gin(to_tsvector('portuguese', nome || ' ' || COALESCE(email, '') || ' ' || COALESCE(telefone, '')));

-- Funil movimentos
CREATE INDEX idx_funil_movimentos_cliente ON erp.funil_movimentos(cliente_id, created_at DESC);

-- Atividades
CREATE INDEX idx_atividades_cliente ON erp.atividades(cliente_id, created_at DESC);

-- Password request codes
CREATE INDEX idx_password_request_codes_admin_corretor ON erp.password_request_codes(admin_user_id, corretor_id);

-- User actions log
CREATE INDEX idx_user_actions_log_usuario_id ON erp.user_actions_log(usuario_id);
CREATE INDEX idx_user_actions_log_created_at ON erp.user_actions_log(created_at DESC);
CREATE INDEX idx_user_actions_log_tipo_acao ON erp.user_actions_log(tipo_acao);
CREATE INDEX idx_user_actions_log_tipo_entidade ON erp.user_actions_log(tipo_entidade);

-- Negociações
CREATE INDEX idx_negociacoes_ativo_origem ON erp.negociacoes(ativo_origem_id);
CREATE INDEX idx_negociacoes_ativo_destino ON erp.negociacoes(ativo_destino_id);
CREATE INDEX idx_negociacoes_proprietario ON erp.negociacoes(cliente_proprietario_id);
CREATE INDEX idx_negociacoes_ofertante ON erp.negociacoes(cliente_ofertante_id);
CREATE INDEX idx_negociacoes_status ON erp.negociacoes(status_etapa);

-- Condominios
CREATE INDEX idx_condominios_owner_id ON erp.condominios(owner_id);
CREATE INDEX idx_condominios_cidade ON erp.condominios(cidade);

-- Matches
CREATE INDEX idx_matches_ativo_origem_id ON erp.matches(ativo_origem_id);
CREATE INDEX idx_matches_ativo_destino_id ON erp.matches(ativo_destino_id);
CREATE INDEX idx_matches_score_desc ON erp.matches(score DESC);
CREATE INDEX idx_matches_status ON erp.matches(status);

-- Ativos
CREATE INDEX idx_ativos_owner_id ON erp.ativos(owner_id);
CREATE INDEX idx_ativos_natureza ON erp.ativos(natureza);
CREATE INDEX idx_ativos_tipo_imovel ON erp.ativos(tipo_imovel);
CREATE INDEX idx_ativos_cidade ON erp.ativos(cidade);
CREATE INDEX idx_ativos_estado ON erp.ativos(estado);
CREATE INDEX idx_ativos_valor ON erp.ativos(valor);
CREATE INDEX idx_ativos_status ON erp.ativos(status);
CREATE INDEX idx_ativos_proprietario ON erp.ativos(proprietario_id);
CREATE INDEX idx_ativos_embedding ON erp.ativos
  USING ivfflat (embedding extensions.vector_cosine_ops)
  WITH (lists = 100);

-- FK indexes (missing foreign key indexes for query performance)
CREATE INDEX IF NOT EXISTS idx_atividades_usuario_id ON erp.atividades(usuario_id);
CREATE INDEX IF NOT EXISTS idx_ativos_condominio_id ON erp.ativos(condominio_id);
CREATE INDEX IF NOT EXISTS idx_chamados_portal_portal_acesso_id ON erp.chamados_portal(portal_acesso_id);
CREATE INDEX IF NOT EXISTS idx_funil_movimentos_responsavel_id ON erp.funil_movimentos(responsavel_id);
CREATE INDEX IF NOT EXISTS idx_negociacoes_owner_id ON erp.negociacoes(owner_id);
CREATE INDEX IF NOT EXISTS idx_vistorias_rapidas_checkin_id ON erp.vistorias_rapidas(checkin_id);

-- ─────────────────────────────────────────────────────────────────────
-- 7. ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────────────

-- Enable RLS on all tables
ALTER TABLE erp.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.metas_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.funil_movimentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.atividades ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.password_request_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.status_pagina ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.user_actions_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.negociacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.condominios ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.ativos ENABLE ROW LEVEL SECURITY;

-- ── Profiles ──
CREATE POLICY "profiles_select_own" ON erp.profiles FOR SELECT
  USING ((SELECT auth.uid()) = id OR public.has_role((SELECT auth.uid()), 'admin'::app_role));
CREATE POLICY "profiles_insert" ON erp.profiles FOR INSERT TO authenticated
  WITH CHECK ((SELECT auth.uid()) = id);
CREATE POLICY "profiles_update" ON erp.profiles FOR UPDATE TO authenticated
  USING ((SELECT auth.uid()) = id OR public.has_role((SELECT auth.uid()), 'admin'::app_role))
  WITH CHECK ((SELECT auth.uid()) = id OR public.has_role((SELECT auth.uid()), 'admin'::app_role));

-- ── User roles ──
CREATE POLICY "user_roles_select" ON erp.user_roles FOR SELECT TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = user_id);
CREATE POLICY "user_roles_insert" ON erp.user_roles FOR INSERT TO authenticated
  WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY "user_roles_update" ON erp.user_roles FOR UPDATE TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY "user_roles_delete" ON erp.user_roles FOR DELETE TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY "Deny unauthenticated access to user_roles" ON erp.user_roles FOR ALL TO anon USING (false);

-- ── Metas ──
CREATE POLICY "metas_select" ON erp.metas FOR SELECT TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = usuario_id);
CREATE POLICY "metas_insert" ON erp.metas FOR INSERT TO authenticated
  WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (usuario_id = (SELECT auth.uid()) AND usuario_id IS NOT NULL));
CREATE POLICY "metas_update" ON erp.metas FOR UPDATE TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR ((SELECT auth.uid()) = usuario_id AND tipo = 'diaria'::erp.tipo_meta AND status != 'concluida'::erp.status_meta)
  )
  WITH CHECK (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR ((SELECT auth.uid()) = usuario_id AND tipo = 'diaria'::erp.tipo_meta AND status != 'concluida'::erp.status_meta)
  );
CREATE POLICY "metas_delete" ON erp.metas FOR DELETE TO public
  USING (has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR ((SELECT auth.uid()) = usuario_id AND (tipo IN ('semanal'::erp.tipo_meta, 'mensal'::erp.tipo_meta, 'anual'::erp.tipo_meta) OR (tipo = 'diaria'::erp.tipo_meta AND status <> 'concluida'::erp.status_meta))));

-- ── Metas config ──
CREATE POLICY "metas_config_select" ON erp.metas_config FOR SELECT
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = usuario_id);
CREATE POLICY "metas_config_insert" ON erp.metas_config FOR INSERT
  WITH CHECK ((SELECT auth.uid()) = usuario_id);
CREATE POLICY "metas_config_update" ON erp.metas_config FOR UPDATE
  USING ((SELECT auth.uid()) = usuario_id);
CREATE POLICY "metas_config_delete" ON erp.metas_config FOR DELETE
  USING ((SELECT auth.uid()) = usuario_id);

-- ── Clientes ──
CREATE POLICY "clientes_select" ON erp.clientes FOR SELECT TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = usuario_id);
CREATE POLICY "clientes_insert" ON erp.clientes FOR INSERT TO authenticated
  WITH CHECK ((SELECT auth.uid()) = usuario_id);
CREATE POLICY "clientes_update" ON erp.clientes FOR UPDATE TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = usuario_id);
CREATE POLICY "clientes_delete" ON erp.clientes FOR DELETE TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = usuario_id);

-- ── Funil movimentos ──
CREATE POLICY "funil_movimentos_select" ON erp.funil_movimentos FOR SELECT TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = funil_movimentos.cliente_id AND clientes.usuario_id = (SELECT auth.uid()))
  );
CREATE POLICY "funil_movimentos_insert" ON erp.funil_movimentos FOR INSERT TO authenticated
  WITH CHECK (
    EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = funil_movimentos.cliente_id AND clientes.usuario_id = (SELECT auth.uid()))
    AND responsavel_id = (SELECT auth.uid())
  );

-- ── Atividades ──
CREATE POLICY "atividades_select" ON erp.atividades FOR SELECT TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = atividades.cliente_id AND clientes.usuario_id = (SELECT auth.uid()))
  );
CREATE POLICY "atividades_insert" ON erp.atividades FOR INSERT TO authenticated
  WITH CHECK (
    EXISTS (SELECT 1 FROM erp.clientes WHERE clientes.id = atividades.cliente_id AND clientes.usuario_id = (SELECT auth.uid()))
    AND usuario_id = (SELECT auth.uid())
  );

-- ── Password request codes ──
CREATE POLICY "Admins can manage their own password request codes" ON erp.password_request_codes FOR ALL
  USING ((SELECT auth.uid()) = admin_user_id);
CREATE POLICY "Only admins can view password codes" ON erp.password_request_codes FOR SELECT TO authenticated
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));

-- ── Status pagina ──
CREATE POLICY "Todos podem ver páginas gerais em produção" ON erp.status_pagina FOR SELECT
  USING (status = 'producao' AND tipo_pagina = 'geral');
CREATE POLICY "Admins podem ver todas as páginas" ON erp.status_pagina FOR SELECT
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));
CREATE POLICY "Devs podem ver páginas gerais em desenvolvimento" ON erp.status_pagina FOR SELECT
  USING (public.has_role((SELECT auth.uid()), 'dev'::erp.app_role) AND tipo_pagina = 'geral');
CREATE POLICY "Apenas admins podem gerenciar páginas" ON erp.status_pagina FOR ALL
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role))
  WITH CHECK (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role));

-- ── User actions log ──
CREATE POLICY "user_actions_log_select" ON erp.user_actions_log FOR SELECT
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = usuario_id);
CREATE POLICY "user_actions_log_insert" ON erp.user_actions_log FOR INSERT
  WITH CHECK ((SELECT auth.uid()) = usuario_id);

-- ── Negociações ──
CREATE POLICY "negociacoes_select" ON erp.negociacoes FOR SELECT
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = owner_id
    OR (SELECT auth.uid()) = cliente_proprietario_id
    OR (SELECT auth.uid()) = cliente_ofertante_id
  );
CREATE POLICY "negociacoes_insert" ON erp.negociacoes FOR INSERT
  WITH CHECK ((SELECT auth.uid()) = owner_id);
CREATE POLICY "negociacoes_update" ON erp.negociacoes FOR UPDATE
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = cliente_proprietario_id
    OR (SELECT auth.uid()) = cliente_ofertante_id
  );
CREATE POLICY "negociacoes_delete" ON erp.negociacoes FOR DELETE
  USING (public.has_role((SELECT auth.uid()), 'admin'::erp.app_role) OR (SELECT auth.uid()) = owner_id);

-- ── Condominios ──
CREATE POLICY "Users can view all condominios" ON erp.condominios FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert their own condominios" ON erp.condominios FOR INSERT TO authenticated
  WITH CHECK ((SELECT auth.uid()) = owner_id);
CREATE POLICY "Users can update their own condominios" ON erp.condominios FOR UPDATE TO authenticated
  USING ((SELECT auth.uid()) = owner_id);
CREATE POLICY "Users can delete their own condominios" ON erp.condominios FOR DELETE TO authenticated
  USING ((SELECT auth.uid()) = owner_id);

-- ── Matches ──
CREATE POLICY "matches_select" ON erp.matches FOR SELECT TO authenticated
  USING (
    EXISTS (SELECT 1 FROM erp.ativos WHERE ativos.id = matches.ativo_origem_id AND ativos.owner_id = (SELECT auth.uid()))
    OR EXISTS (SELECT 1 FROM erp.ativos WHERE ativos.id = matches.ativo_destino_id AND ativos.owner_id = (SELECT auth.uid()))
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  );
CREATE POLICY "matches_insert" ON erp.matches FOR INSERT TO authenticated
  WITH CHECK (
    EXISTS (SELECT 1 FROM erp.ativos WHERE ativos.id = matches.ativo_origem_id AND ativos.owner_id = (SELECT auth.uid()))
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  );
CREATE POLICY "matches_update" ON erp.matches FOR UPDATE TO authenticated
  USING (
    EXISTS (SELECT 1 FROM erp.ativos WHERE ativos.id = matches.ativo_origem_id AND ativos.owner_id = (SELECT auth.uid()))
    OR EXISTS (SELECT 1 FROM erp.ativos WHERE ativos.id = matches.ativo_destino_id AND ativos.owner_id = (SELECT auth.uid()))
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  );
CREATE POLICY "matches_delete" ON erp.matches FOR DELETE TO authenticated
  USING (
    EXISTS (SELECT 1 FROM erp.ativos WHERE ativos.id = matches.ativo_origem_id AND ativos.owner_id = (SELECT auth.uid()))
    OR public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
  );

-- ── Ativos ──
CREATE POLICY "Users can view all active ativos" ON erp.ativos FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users can insert their own ativos" ON erp.ativos FOR INSERT TO authenticated
  WITH CHECK ((SELECT auth.uid()) = owner_id);
CREATE POLICY "Users can update their own ativos" ON erp.ativos FOR UPDATE TO authenticated
  USING ((SELECT auth.uid()) = owner_id);
CREATE POLICY "Users can delete their own ativos" ON erp.ativos FOR DELETE TO authenticated
  USING ((SELECT auth.uid()) = owner_id);

-- ─────────────────────────────────────────────────────────────────────
-- 8. BUSINESS LOGIC FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- NOTE: has_role() is defined in section 5b (right after user_roles table)

-- AI matching: similarity search via pgvector
CREATE OR REPLACE FUNCTION erp.match_ativos(
  query_embedding extensions.vector(1536),
  match_count INT DEFAULT 50,
  similarity_threshold FLOAT DEFAULT 0.3,
  exclude_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  similarity FLOAT
)
LANGUAGE sql STABLE
SET search_path = erp, public, extensions
AS $$
  SELECT
    a.id,
    1 - (a.embedding OPERATOR(extensions.<=>) query_embedding) AS similarity
  FROM erp.ativos a
  WHERE a.embedding IS NOT NULL
    AND (exclude_id IS NULL OR a.id != exclude_id)
    AND a.status = 'ativo'
    AND 1 - (a.embedding OPERATOR(extensions.<=>) query_embedding) > similarity_threshold
  ORDER BY a.embedding OPERATOR(extensions.<=>) query_embedding
  LIMIT match_count;
$$;

-- Auth: Create profile on signup (stays in public — triggered by auth.users)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public'
AS $$
BEGIN
  INSERT INTO erp.profiles (id, nome, email, telefone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'telefone', '')
  );
  RETURN NEW;
END;
$$;

-- Auth: Assign default corretor role on signup (stays in public — triggered by auth.users)
CREATE OR REPLACE FUNCTION public.assign_default_corretor_role()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO erp.user_roles (user_id, role)
  VALUES (NEW.id, 'corretor')
  ON CONFLICT (user_id, role) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Period helpers
CREATE OR REPLACE FUNCTION erp.get_period_key(tipo_meta tipo_meta, data_ref date)
RETURNS TEXT LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN RETURN TO_CHAR(data_ref, 'YYYY-MM-DD');
    WHEN 'semanal' THEN RETURN TO_CHAR(data_ref, 'IYYY-IW');
    WHEN 'mensal' THEN RETURN TO_CHAR(data_ref, 'YYYY-MM');
    WHEN 'anual' THEN RETURN TO_CHAR(data_ref, 'YYYY');
  END CASE;
END;
$$;

CREATE OR REPLACE FUNCTION erp.period_end_date(tipo_meta tipo_meta, data_ref date)
RETURNS DATE LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  CASE tipo_meta
    WHEN 'diaria' THEN RETURN data_ref;
    WHEN 'semanal' THEN RETURN data_ref + (7 - EXTRACT(ISODOW FROM data_ref)::INTEGER);
    WHEN 'mensal' THEN RETURN (DATE_TRUNC('month', data_ref) + INTERVAL '1 month - 1 day')::DATE;
    WHEN 'anual' THEN RETURN (DATE_TRUNC('year', data_ref) + INTERVAL '1 year - 1 day')::DATE;
  END CASE;
END;
$$;

-- Working days calculations
CREATE OR REPLACE FUNCTION erp.dias_uteis_mes(p_data_ref date)
RETURNS integer LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_primeiro DATE; v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_primeiro := DATE_TRUNC('month', p_data_ref)::DATE;
  v_ultimo := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  v_dia := v_primeiro;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.semanas_mes(p_data_ref date)
RETURNS numeric LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_dias INTEGER;
BEGIN
  v_dias := EXTRACT(DAY FROM (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE);
  RETURN ROUND(v_dias::numeric / 7, 2);
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_domingo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_domingo := p_data_ref + (7 - EXTRACT(ISODOW FROM p_data_ref)::INTEGER);
  v_dia := p_data_ref;
  WHILE v_dia <= v_domingo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_semana(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_segunda DATE; v_domingo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_segunda := p_data_ref - (EXTRACT(ISODOW FROM p_data_ref)::INTEGER - 1);
  v_domingo := v_segunda + 6;
  v_dia := v_segunda;
  WHILE v_dia <= v_domingo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_ultimo := (DATE_TRUNC('month', p_data_ref) + INTERVAL '1 month - 1 day')::DATE;
  v_dia := p_data_ref;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_mes(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$ BEGIN RETURN dias_uteis_mes(p_data_ref); END; $$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_restantes_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_ultimo := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  v_dia := p_data_ref;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.dias_uteis_totais_ano(p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_primeiro DATE; v_ultimo DATE; v_dia DATE; v_count INTEGER := 0;
BEGIN
  v_primeiro := DATE_TRUNC('year', p_data_ref)::DATE;
  v_ultimo := (DATE_TRUNC('year', p_data_ref) + INTERVAL '1 year - 1 day')::DATE;
  v_dia := v_primeiro;
  WHILE v_dia <= v_ultimo LOOP
    IF EXTRACT(ISODOW FROM v_dia) BETWEEN 1 AND 5 THEN v_count := v_count + 1; END IF;
    v_dia := v_dia + 1;
  END LOOP;
  RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION erp.calcular_meta_proporcional(p_meta_mensal INTEGER, p_tipo tipo_meta, p_data_ref DATE)
RETURNS INTEGER LANGUAGE plpgsql STABLE SET search_path TO 'erp', 'public'
AS $$
DECLARE v_total INTEGER; v_restantes INTEGER; v_diaria NUMERIC; v_resultado INTEGER;
BEGIN
  CASE p_tipo
    WHEN 'diaria' THEN
      v_total := dias_uteis_totais_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC / GREATEST(v_total, 1));
    WHEN 'semanal' THEN
      v_total := dias_uteis_totais_mes(p_data_ref);
      v_restantes := dias_uteis_restantes_semana(p_data_ref);
      v_diaria := p_meta_mensal::NUMERIC / GREATEST(v_total, 1);
      v_resultado := CEIL(v_diaria * v_restantes);
    WHEN 'mensal' THEN
      v_total := dias_uteis_totais_mes(p_data_ref);
      v_restantes := dias_uteis_restantes_mes(p_data_ref);
      v_resultado := CEIL(p_meta_mensal::NUMERIC * v_restantes::NUMERIC / GREATEST(v_total, 1));
    WHEN 'anual' THEN
      v_total := dias_uteis_totais_ano(p_data_ref);
      v_restantes := dias_uteis_restantes_ano(p_data_ref);
      v_resultado := CEIL((p_meta_mensal * 12)::NUMERIC * v_restantes::NUMERIC / GREATEST(v_total, 1));
  END CASE;
  RETURN GREATEST(v_resultado, 1);
END;
$$;

-- Scaffold meta (lookup-only, no auto-creation)
CREATE OR REPLACE FUNCTION erp.ensure_scaffold_meta(
  p_usuario_id uuid, p_tipo tipo_meta, p_categoria categoria_meta, p_data_ref date
)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_data_prazo DATE; v_meta_id TEXT;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: não é possível acessar metas para outros usuários';
  END IF;
  v_data_prazo := period_end_date(p_tipo, p_data_ref);
  SELECT id INTO v_meta_id FROM erp.metas
  WHERE usuario_id = p_usuario_id AND tipo = p_tipo AND categoria = p_categoria AND data_prazo = v_data_prazo
  ORDER BY created_at DESC LIMIT 1;
  RETURN v_meta_id;
END;
$$;

-- Rollup metas (aggregation with São Paulo timezone)
CREATE OR REPLACE FUNCTION erp.rollup_metas(p_usuario_id uuid, p_categoria categoria_meta, p_data_ref date)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE
  v_periodo_inicio DATE; v_periodo_fim DATE;
  v_real_bruta INTEGER; v_pretendida INTEGER; v_carry_in_prev INTEGER;
  v_acumulado INTEGER; v_real_cap INTEGER; v_carry_out_calc INTEGER;
  v_status status_meta; v_meta_id TEXT; v_data_prazo DATE; v_prev_data_prazo DATE;
  v_meta_mensal INTEGER; v_semanas NUMERIC; v_hoje DATE;
BEGIN
  IF p_usuario_id != auth.uid() AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado';
  END IF;
  v_hoje := current_date_sao_paulo();
  SELECT meta_pretendida INTO v_meta_mensal FROM erp.metas_config
  WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND ativo = true LIMIT 1;
  v_meta_mensal := COALESCE(v_meta_mensal, 0);

  -- Weekly
  v_data_prazo := period_end_date('semanal', p_data_ref);
  v_periodo_inicio := v_data_prazo - 6;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('semanal', v_periodo_inicio - 7);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'semanal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_semanas := semanas_mes(p_data_ref);
  v_pretendida := CASE WHEN v_semanas > 0 THEN CEIL(v_meta_mensal::numeric / v_semanas) ELSE v_meta_mensal END;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'semanal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Monthly
  v_data_prazo := period_end_date('mensal', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('month', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('mensal', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'mensal' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'mensal', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;

  -- Annual
  v_data_prazo := period_end_date('anual', p_data_ref);
  v_periodo_inicio := DATE_TRUNC('year', p_data_ref)::DATE;
  v_periodo_fim := v_data_prazo;
  v_prev_data_prazo := period_end_date('anual', v_periodo_inicio - 1);
  SELECT carry_out INTO v_carry_in_prev FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'anual' AND categoria = p_categoria AND data_prazo = v_prev_data_prazo;
  v_carry_in_prev := COALESCE(v_carry_in_prev, 0);
  SELECT COALESCE(SUM(meta_realizada), 0) INTO v_real_bruta FROM erp.metas WHERE usuario_id = p_usuario_id AND tipo = 'diaria' AND categoria = p_categoria AND data_prazo >= v_periodo_inicio AND data_prazo <= v_periodo_fim;
  v_pretendida := v_meta_mensal * 12;
  v_acumulado := v_real_bruta + v_carry_in_prev;
  v_real_cap := LEAST(v_acumulado, v_pretendida);
  v_carry_out_calc := GREATEST(v_acumulado - v_pretendida, 0);
  v_status := CASE WHEN v_real_cap >= v_pretendida THEN 'concluida' WHEN v_hoje > v_data_prazo THEN 'atrasada' ELSE 'no_prazo' END;
  v_meta_id := ensure_scaffold_meta(p_usuario_id, 'anual', p_categoria, p_data_ref);
  IF v_meta_id IS NOT NULL THEN
    UPDATE erp.metas SET meta_pretendida = v_pretendida, meta_realizada = v_real_cap, carry_in = v_carry_in_prev, carry_out = v_carry_out_calc, status = v_status, updated_at = NOW() WHERE id = v_meta_id;
  END IF;
END;
$$;

-- Concluir meta agrupada (SP timezone)
CREATE OR REPLACE FUNCTION erp.concluir_meta_agrupada(p_meta_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_meta RECORD; v_no_prazo boolean; v_hoje DATE;
BEGIN
  v_hoje := current_date_sao_paulo();
  SELECT * INTO v_meta FROM erp.metas WHERE id = p_meta_id AND tipo IN ('semanal', 'mensal', 'anual') AND usuario_id = auth.uid();
  IF NOT FOUND THEN RETURN jsonb_build_object('success', false, 'error', 'Meta não encontrada ou sem permissão'); END IF;
  IF v_meta.meta_realizada < v_meta.meta_pretendida THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não atingida. Realize: ' || v_meta.meta_realizada || '/' || v_meta.meta_pretendida);
  END IF;
  v_no_prazo := (v_hoje <= v_meta.data_prazo);
  UPDATE erp.metas SET status = 'concluida', finalizada_em = NOW(), finalizada_no_prazo = v_no_prazo,
    conclusao_prazo = CASE WHEN v_no_prazo THEN 'no_prazo' ELSE 'atrasada' END::erp.conclusao_prazo_meta, updated_at = NOW()
  WHERE id = p_meta_id;
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$$;

-- Conclusao prazo trigger function
CREATE OR REPLACE FUNCTION erp.set_conclusao_prazo()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.status = 'concluida' AND (OLD.status IS DISTINCT FROM 'concluida') THEN
      IF NEW.finalizada_em IS NULL THEN NEW.finalizada_em := now(); END IF;
      NEW.finalizada_no_prazo := (NEW.finalizada_em::date <= NEW.data_prazo);
      NEW.conclusao_prazo := CASE WHEN NEW.finalizada_em::date <= NEW.data_prazo THEN 'no_prazo' ELSE 'atrasada' END;
    ELSE
      IF NEW.conclusao_prazo IS DISTINCT FROM OLD.conclusao_prazo THEN
        RAISE EXCEPTION 'conclusao_prazo é gerenciado pelo sistema e não pode ser alterado manualmente';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- Status update function (batch job)
CREATE OR REPLACE FUNCTION erp.atualizar_status_metas()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_count INTEGER := 0; v_tmp INTEGER; v_hoje DATE; v_amanha DATE;
BEGIN
  v_hoje := current_date_sao_paulo();
  v_amanha := v_hoje + 1;
  UPDATE erp.metas SET dias_restantes = data_prazo - v_hoje, updated_at = NOW() WHERE status NOT IN ('concluida');
  UPDATE erp.metas SET status = 'vence_amanha', updated_at = NOW() WHERE data_prazo = v_amanha AND status NOT IN ('concluida') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'atrasada', updated_at = NOW() WHERE data_prazo < v_hoje AND status NOT IN ('concluida') AND status != 'atrasada';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo > v_amanha AND status NOT IN ('concluida') AND status != 'no_prazo';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  UPDATE erp.metas SET status = 'no_prazo', updated_at = NOW() WHERE data_prazo = v_hoje AND status NOT IN ('concluida', 'no_prazo') AND status != 'vence_amanha';
  GET DIAGNOSTICS v_tmp = ROW_COUNT; v_count := v_count + v_tmp;
  RETURN jsonb_build_object('success', true, 'metas_atualizadas', v_count, 'timestamp', NOW());
END;
$$;

-- Performance level calculation
CREATE OR REPLACE FUNCTION erp.calcular_nivel_performance(p_realizada INTEGER, p_pretendida INTEGER)
RETURNS nivel_performance_meta LANGUAGE plpgsql IMMUTABLE
SET search_path = erp, public
AS $$
DECLARE v_prog NUMERIC;
BEGIN
  IF p_pretendida = 0 THEN RETURN 'baixo'; END IF;
  v_prog := (p_realizada::NUMERIC / p_pretendida::NUMERIC) * 100;
  IF v_prog >= 100 THEN RETURN 'excelente';
  ELSIF v_prog >= 80 THEN RETURN 'bom';
  ELSIF v_prog >= 50 THEN RETURN 'regular';
  ELSE RETURN 'baixo'; END IF;
END;
$$;

-- Trigger functions for metas
CREATE OR REPLACE FUNCTION erp.atualizar_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  NEW.nivel_performance := calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.atualizar_dias_restantes()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN NEW.dias_restantes := NEW.data_prazo - current_date_sao_paulo(); RETURN NEW; END;
$$;

CREATE OR REPLACE FUNCTION erp.validar_alteracao_status_meta()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF auth.uid() IS NULL THEN RETURN NEW; END IF;
  IF NEW.status = 'concluida' AND OLD.status != 'concluida' THEN RETURN NEW; END IF;
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status != 'concluida' THEN
    RAISE EXCEPTION 'O status da meta é atualizado automaticamente pelo sistema';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.validar_alteracao_nivel_performance()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF auth.uid() IS NULL THEN RETURN NEW; END IF;
  IF OLD.nivel_performance IS DISTINCT FROM NEW.nivel_performance THEN
    IF NEW.nivel_performance != calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida) THEN
      RAISE EXCEPTION 'O nível de performance é calculado automaticamente';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.prevent_date_change_on_daily_metas()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN RETURN NEW; END IF;
  IF OLD.tipo = 'diaria' AND NEW.data_prazo IS DISTINCT FROM OLD.data_prazo THEN
    RAISE EXCEPTION 'Apenas administradores podem alterar a data prazo de metas diárias';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION erp.recalcular_metas_on_mensal_change()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
AS $$
BEGIN
  IF NEW.tipo = 'mensal' AND OLD.meta_pretendida IS DISTINCT FROM NEW.meta_pretendida THEN
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo);
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo - INTERVAL '1 month');
    PERFORM rollup_metas(NEW.usuario_id, NEW.categoria, NEW.data_prazo + INTERVAL '1 month');
  END IF;
  RETURN NEW;
END;
$$;

-- Timestamp normalization triggers
CREATE OR REPLACE FUNCTION erp.normalize_metas_finalizada_em()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.finalizada_em IS NOT NULL THEN NEW.finalizada_em := normalize_timestamp_sp(NEW.finalizada_em); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION erp.normalize_atividades_data_execucao()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.data_execucao IS NOT NULL THEN NEW.data_execucao := normalize_timestamp_sp(NEW.data_execucao); ELSE NEW.data_execucao := now_sao_paulo(); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION erp.normalize_profiles_last_activity()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.last_activity_at IS NOT NULL THEN NEW.last_activity_at := normalize_timestamp_sp(NEW.last_activity_at); ELSE NEW.last_activity_at := now_sao_paulo(); END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION erp.normalize_password_codes_expires()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$ BEGIN IF NEW.expires_at IS NOT NULL THEN NEW.expires_at := normalize_timestamp_sp(NEW.expires_at); END IF; RETURN NEW; END; $$;

-- Inactive users deactivation
CREATE OR REPLACE FUNCTION erp.desativar_metas_usuarios_inativos()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'erp', 'public'
AS $$
DECLARE v_users INTEGER := 0; v_configs INTEGER := 0;
BEGIN
  IF auth.uid() IS NOT NULL AND NOT public.has_role(auth.uid(), 'admin') THEN
    RAISE EXCEPTION 'Acesso negado: apenas administradores';
  END IF;
  WITH inativos AS (SELECT id FROM erp.profiles WHERE last_activity_at < NOW() - INTERVAL '20 days')
  UPDATE erp.metas_config SET ativo = false, updated_at = NOW()
  WHERE usuario_id IN (SELECT id FROM inativos) AND ativo = true;
  GET DIAGNOSTICS v_configs = ROW_COUNT;
  SELECT COUNT(DISTINCT usuario_id) INTO v_users FROM (SELECT usuario_id FROM erp.metas_config WHERE updated_at >= NOW() - INTERVAL '1 minute' AND ativo = false) t;
  RETURN jsonb_build_object('success', true, 'usuarios_afetados', v_users, 'configs_desativadas', v_configs, 'timestamp', NOW());
END;
$$;

-- Expired password codes cleanup
CREATE OR REPLACE FUNCTION erp.delete_expired_password_codes()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = erp, public
AS $$ BEGIN DELETE FROM erp.password_request_codes WHERE expires_at < now(); END; $$;

-- Distribuir meta descendente (downward distribution from manual metas)
CREATE OR REPLACE FUNCTION erp.distribuir_meta_descendente()
RETURNS TRIGGER AS $$
DECLARE
  v_meta_diaria DECIMAL; v_meta_semanal DECIMAL; v_meta_mensal DECIMAL; v_meta_anual DECIMAL;
  v_data_atual DATE; v_data_fim DATE; v_data_temp DATE;
  v_dias_uteis INTEGER; v_semanas INTEGER; v_meses INTEGER; v_dia_semana INTEGER; v_existe_meta BOOLEAN;
BEGIN
  IF NOT NEW.criada_manualmente THEN RETURN NEW; END IF;
  CASE NEW.tipo
    WHEN 'anual' THEN
      v_meta_mensal := NEW.meta_pretendida / 12.0;
      FOR v_meses IN 0..11 LOOP
        v_data_atual := DATE_TRUNC('year', NEW.data_prazo) + (v_meses || ' months')::INTERVAL;
        v_data_fim := (v_data_atual + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
        v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
        v_meta_semanal := v_meta_mensal / v_semanas;
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), v_data_fim, false, NEW.nome, NEW.detalhes);
        FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', v_data_temp) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
          v_dias_uteis := 0; v_data_temp := v_data_temp;
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
          v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
          INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
          v_data_temp := v_data_atual::DATE + ((v_semanas - 1) * 7);
          WHILE v_data_temp <= v_data_fim LOOP
            IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
              INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
              VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
            END IF;
            v_data_temp := v_data_temp + 1;
          END LOOP;
        END LOOP;
      END LOOP;
    WHEN 'mensal' THEN
      v_data_atual := DATE_TRUNC('month', NEW.data_prazo)::DATE;
      v_data_fim := (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
      v_semanas := CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0);
      v_meta_semanal := NEW.meta_pretendida / v_semanas;
      v_meta_anual := NEW.meta_pretendida * 12;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      FOR v_semanas IN 1..CEIL(EXTRACT(DAY FROM v_data_fim) / 7.0) LOOP
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        v_data_fim := LEAST(v_data_temp + 6, (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE);
        v_dias_uteis := 0; v_data_temp := v_data_temp;
        WHILE v_data_temp <= v_data_fim LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
        v_meta_diaria := v_meta_semanal / GREATEST(v_dias_uteis, 1);
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'semanal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_semanal), v_data_fim, false, NEW.nome, NEW.detalhes);
        v_data_temp := v_data_atual + ((v_semanas - 1) * 7);
        WHILE v_data_temp <= v_data_fim LOOP
          IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
            INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
            VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
          END IF;
          v_data_temp := v_data_temp + 1;
        END LOOP;
      END LOOP;
    WHEN 'semanal' THEN
      v_data_atual := NEW.data_prazo - EXTRACT(DOW FROM NEW.data_prazo)::INTEGER + 1;
      IF EXTRACT(DOW FROM NEW.data_prazo) = 0 THEN v_data_atual := v_data_atual - 7; END IF;
      v_dias_uteis := 0; v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN v_dias_uteis := v_dias_uteis + 1; END IF; v_data_temp := v_data_temp + 1; END LOOP;
      v_meta_diaria := NEW.meta_pretendida / GREATEST(v_dias_uteis, 1);
      v_meta_mensal := NEW.meta_pretendida * 4;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'mensal' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'mensal', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_mensal), (DATE_TRUNC('month', NEW.data_prazo) + INTERVAL '1 month' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_meta_anual := v_meta_mensal * 12;
      SELECT EXISTS(SELECT 1 FROM erp.metas WHERE usuario_id = NEW.usuario_id AND tipo = 'anual' AND categoria = NEW.categoria AND data_prazo = (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE AND (categoria_custom IS NULL OR categoria_custom = NEW.categoria_custom)) INTO v_existe_meta;
      IF NOT v_existe_meta THEN
        INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
        VALUES (NEW.usuario_id, 'anual', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_anual), (DATE_TRUNC('year', NEW.data_prazo) + INTERVAL '1 year' - INTERVAL '1 day')::DATE, false, NEW.nome, NEW.detalhes);
      END IF;
      v_data_temp := v_data_atual;
      FOR i IN 0..6 LOOP
        IF EXTRACT(DOW FROM v_data_temp) BETWEEN 1 AND 5 THEN
          INSERT INTO erp.metas (usuario_id, tipo, categoria, categoria_custom, meta_pretendida, data_prazo, criada_manualmente, nome, detalhes)
          VALUES (NEW.usuario_id, 'diaria', NEW.categoria, NEW.categoria_custom, ROUND(v_meta_diaria), v_data_temp, false, NEW.nome, NEW.detalhes);
        END IF;
        v_data_temp := v_data_temp + 1;
      END LOOP;
    ELSE NULL;
  END CASE;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public;

-- ─────────────────────────────────────────────────────────────────────
-- 9. TRIGGERS
-- ─────────────────────────────────────────────────────────────────────

-- Auth triggers
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
CREATE TRIGGER on_auth_user_created_assign_role AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.assign_default_corretor_role();

-- Timestamp triggers (São Paulo)
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.clientes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.profiles FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.negociacoes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT OR UPDATE ON erp.metas_config FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.atividades FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.funil_movimentos FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.user_actions_log FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.user_roles FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_timestamps_sp_trigger BEFORE INSERT ON erp.password_request_codes FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- Updated_at triggers (for tables not covered by set_timestamps_sp)
CREATE TRIGGER update_negociacoes_updated_at BEFORE UPDATE ON erp.negociacoes FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();
CREATE TRIGGER update_metas_config_updated_at BEFORE UPDATE ON erp.metas_config FOR EACH ROW EXECUTE FUNCTION erp.update_updated_at_column();

-- Metas-specific triggers
CREATE TRIGGER trg_set_conclusao_prazo BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.set_conclusao_prazo();
CREATE TRIGGER trigger_atualizar_nivel_performance BEFORE INSERT OR UPDATE OF meta_realizada, meta_pretendida ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.atualizar_nivel_performance();
CREATE TRIGGER trigger_validar_nivel_performance BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.validar_alteracao_nivel_performance();
CREATE TRIGGER trigger_atualizar_dias_restantes BEFORE INSERT OR UPDATE OF data_prazo ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.atualizar_dias_restantes();
CREATE TRIGGER trigger_validar_status_meta BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.validar_alteracao_status_meta();
CREATE TRIGGER prevent_date_change_trigger BEFORE UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.prevent_date_change_on_daily_metas();
CREATE TRIGGER trigger_recalcular_metas_mensal AFTER UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.recalcular_metas_on_mensal_change();

-- Timestamp normalization triggers
CREATE TRIGGER normalize_metas_finalizada_em_trigger BEFORE INSERT OR UPDATE ON erp.metas FOR EACH ROW EXECUTE FUNCTION erp.normalize_metas_finalizada_em();
CREATE TRIGGER normalize_atividades_data_execucao_trigger BEFORE INSERT ON erp.atividades FOR EACH ROW EXECUTE FUNCTION erp.normalize_atividades_data_execucao();
CREATE TRIGGER normalize_profiles_last_activity_trigger BEFORE INSERT OR UPDATE ON erp.profiles FOR EACH ROW EXECUTE FUNCTION erp.normalize_profiles_last_activity();
CREATE TRIGGER normalize_password_codes_expires_trigger BEFORE INSERT ON erp.password_request_codes FOR EACH ROW EXECUTE FUNCTION erp.normalize_password_codes_expires();

-- ─────────────────────────────────────────────────────────────────────
-- 9b. RPC ALIAS (used by backend: admin.rpc("get_data_sp"))
-- ─────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION erp.get_data_sp()
RETURNS DATE
LANGUAGE SQL STABLE
SET search_path = erp, public
AS $$ SELECT (NOW() AT TIME ZONE 'America/Sao_Paulo')::DATE; $$;

-- ─────────────────────────────────────────────────────────────────────
-- 10. SEED DATA
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO erp.status_pagina (nome_pagina, status, tipo_pagina) VALUES
  -- Principal
  ('dashboard', 'producao', 'geral'),
  ('funil', 'producao', 'geral'),
  ('clientes', 'producao', 'geral'),
  ('metas', 'producao', 'geral'),
  -- Comercial
  ('imoveis', 'producao', 'geral'),
  ('condominios', 'producao', 'geral'),
  ('permutas', 'producao', 'geral'),
  ('negociacoes', 'producao', 'geral'),
  ('propostas', 'producao', 'geral'),
  ('contratos', 'producao', 'geral'),
  ('locacoes', 'producao', 'geral'),
  ('comissoes', 'producao', 'geral'),
  -- Financeiro
  ('financeiro', 'producao', 'geral'),
  ('impostos', 'producao', 'geral'),
  ('banco', 'producao', 'geral'),
  ('analise-credito', 'producao', 'geral'),
  -- Operacional
  ('agenda', 'producao', 'geral'),
  ('vistorias', 'producao', 'geral'),
  ('manutencao', 'producao', 'geral'),
  ('chaves', 'producao', 'geral'),
  ('campo', 'producao', 'geral'),
  ('seguros', 'producao', 'geral'),
  -- Marketing & Comunicação
  ('marketing', 'producao', 'geral'),
  ('emails', 'producao', 'geral'),
  ('whatsapp', 'producao', 'geral'),
  ('meta-ads', 'producao', 'geral'),
  ('notificacoes', 'producao', 'geral'),
  -- Documentos
  ('documentos', 'producao', 'geral'),
  ('certidoes', 'producao', 'geral'),
  ('matriculas', 'producao', 'geral'),
  ('assinaturas', 'producao', 'geral'),
  ('dimob', 'producao', 'geral'),
  ('relatorios', 'producao', 'geral'),
  -- Portais & Site
  ('portal-cliente', 'producao', 'geral'),
  ('portal', 'producao', 'geral'),
  ('site', 'producao', 'geral'),
  -- Analytics & IA
  ('bi', 'producao', 'geral'),
  ('matching', 'producao', 'geral'),
  ('gamificacao', 'producao', 'geral'),
  -- Standalone
  ('distribuicao', 'producao', 'geral'),
  ('filiais', 'producao', 'geral'),
  ('configuracoes', 'producao', 'geral'),
  -- Painel de Controle (admin only)
  ('usuarios', 'producao', 'administrativa'),
  ('admin', 'producao', 'administrativa'),
  ('log-acoes', 'producao', 'administrativa')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════
-- 11. MVP EXPANSION TABLES (inline from 004_mvp_expansion.sql)
-- ═══════════════════════════════════════════════════════════════════════
-- These tables support all 38 existing routers plus new features
-- (notifications, WAHA, Meta API).
-- ═══════════════════════════════════════════════════════════════════════

-- ── GROUP A: Sales & Proposals ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.propostas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  cliente_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  valor_proposta numeric NOT NULL,
  valor_contraproposta numeric,
  status text NOT NULL DEFAULT 'enviada'
    CHECK (status IN ('enviada','em_analise','contraproposta','aceita','recusada','expirada')),
  condicoes_pagamento text,
  prazo_validade date,
  observacoes text,
  historico jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.contratos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('venda','locacao')),
  status text NOT NULL DEFAULT 'rascunho'
    CHECK (status IN ('rascunho','ativo','concluido','cancelado','distratado')),
  cliente_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  proposta_id uuid,
  valor_total numeric NOT NULL,
  valor_entrada numeric NOT NULL DEFAULT 0,
  num_parcelas integer NOT NULL DEFAULT 1,
  data_inicio date NOT NULL,
  data_fim date,
  data_assinatura date,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.parcelas_contrato (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  contrato_id uuid NOT NULL REFERENCES erp.contratos(id) ON DELETE CASCADE,
  numero integer NOT NULL,
  valor numeric NOT NULL,
  data_vencimento date NOT NULL,
  data_pagamento date,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','pago','atrasado','cancelado')),
  forma_pagamento text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP B: Financial ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.lancamentos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('receita','despesa')),
  categoria text NOT NULL,
  descricao text NOT NULL,
  valor numeric NOT NULL,
  data_vencimento date NOT NULL,
  data_pagamento date,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','pago','atrasado','cancelado')),
  forma_pagamento text,
  imovel_id uuid,
  cliente_id uuid,
  comissao_id uuid,
  recorrente boolean NOT NULL DEFAULT false,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.impostos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('iptu','itbi','txa_lixo','contribuicao_melhoria','outro')),
  ano integer NOT NULL,
  valor_total numeric NOT NULL,
  valor_pago numeric NOT NULL DEFAULT 0,
  num_parcelas integer NOT NULL DEFAULT 1,
  parcela_atual integer NOT NULL DEFAULT 0,
  desconto_cota_unica numeric NOT NULL DEFAULT 0,
  data_vencimento date NOT NULL,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','parcial','pago','atrasado','isento')),
  numero_guia text,
  comprovante_url text,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.extratos_bancarios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  banco text NOT NULL,
  agencia text,
  conta text,
  data_importacao timestamptz NOT NULL DEFAULT now(),
  arquivo_nome text NOT NULL,
  periodo_inicio date,
  periodo_fim date,
  total_registros integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.movimentacoes_bancarias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  extrato_id uuid NOT NULL REFERENCES erp.extratos_bancarios(id) ON DELETE CASCADE,
  data date NOT NULL,
  descricao text NOT NULL,
  valor numeric NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('credito','debito')),
  conciliado boolean NOT NULL DEFAULT false,
  lancamento_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP C: Commissions ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.comissoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  venda_id uuid,
  imovel_id uuid,
  valor_venda numeric NOT NULL,
  percentual_comissao numeric NOT NULL DEFAULT 6.0,
  valor_comissao numeric NOT NULL,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','aprovada','paga','cancelada')),
  data_venda date,
  data_pagamento date,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.comissoes_splits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  comissao_id uuid NOT NULL REFERENCES erp.comissoes(id) ON DELETE CASCADE,
  corretor_id uuid NOT NULL,
  corretor_nome text NOT NULL,
  percentual numeric NOT NULL,
  valor numeric NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP D: Rentals ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.contratos_locacao (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  locatario_id uuid NOT NULL,
  proprietario_id uuid,
  valor_aluguel numeric NOT NULL,
  dia_vencimento int NOT NULL DEFAULT 10,
  data_inicio date NOT NULL,
  data_fim date NOT NULL,
  indice_reajuste text NOT NULL DEFAULT 'IGPM'
    CHECK (indice_reajuste IN ('IGPM','IPCA','INPC','fixo')),
  percentual_reajuste numeric,
  status text NOT NULL DEFAULT 'ativo'
    CHECK (status IN ('ativo','encerrado','renovado','inadimplente')),
  taxa_administracao numeric NOT NULL DEFAULT 10.0,
  valor_caucao numeric,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP E: Calendar ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.eventos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  titulo text NOT NULL,
  descricao text,
  tipo text NOT NULL
    CHECK (tipo IN ('visita','reuniao','ligacao','vistoria','assinatura','outro')),
  data_inicio timestamptz NOT NULL,
  data_fim timestamptz NOT NULL,
  local text,
  cliente_id uuid,
  imovel_id uuid,
  status text NOT NULL DEFAULT 'agendado'
    CHECK (status IN ('agendado','confirmado','realizado','cancelado')),
  cor text DEFAULT '#6366f1',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP F: Documents & Signatures ─────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.documentos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL
    CHECK (tipo IN ('contrato','procuracao','laudo','certidao','outro')),
  arquivo_url text,
  arquivo_path text,
  tamanho_bytes bigint,
  mime_type text,
  imovel_id uuid,
  cliente_id uuid,
  proposta_id uuid,
  template_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.document_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL,
  conteudo text NOT NULL,
  variaveis text[] NOT NULL DEFAULT '{}',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.assinaturas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  documento_nome text NOT NULL,
  documento_url text,
  contrato_id uuid,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','enviado','assinado','recusado','expirado','cancelado')),
  provedor text NOT NULL DEFAULT 'interno'
    CHECK (provedor IN ('interno','clicksign','docusign','d4sign')),
  link_assinatura text,
  signatarios jsonb NOT NULL DEFAULT '[]',
  historico jsonb NOT NULL DEFAULT '[]',
  data_envio timestamptz,
  data_assinatura timestamptz,
  data_expiracao timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP G: Email & Marketing ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.emails (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid,
  remetente text NOT NULL,
  destinatario text NOT NULL,
  assunto text NOT NULL,
  corpo text NOT NULL,
  corpo_html text,
  direcao text NOT NULL CHECK (direcao IN ('enviado','recebido')),
  status text NOT NULL DEFAULT 'enviado'
    CHECK (status IN ('rascunho','enviado','entregue','aberto','erro')),
  template_id uuid,
  aberturas integer NOT NULL DEFAULT 0,
  cliques integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.email_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  assunto text NOT NULL,
  corpo text NOT NULL,
  variaveis text[] NOT NULL DEFAULT '{}',
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.campanhas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('email','whatsapp','alerta_imovel')),
  status text NOT NULL DEFAULT 'rascunho'
    CHECK (status IN ('rascunho','ativa','pausada','concluida')),
  template text NOT NULL,
  filtros jsonb NOT NULL DEFAULT '{}',
  total_enviados int NOT NULL DEFAULT 0,
  total_abertos int NOT NULL DEFAULT 0,
  total_cliques int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.envios_email (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  campanha_id uuid NOT NULL REFERENCES erp.campanhas(id) ON DELETE CASCADE,
  cliente_id uuid NOT NULL,
  email text NOT NULL,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','enviado','aberto','clicado','erro')),
  enviado_at timestamptz,
  aberto_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP H: WhatsApp ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.whatsapp_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid,
  phone text NOT NULL,
  direction text NOT NULL CHECK (direction IN ('sent','received')),
  message text NOT NULL,
  message_type text NOT NULL DEFAULT 'text'
    CHECK (message_type IN ('text','property_card','image')),
  metadata jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'sent'
    CHECK (status IN ('sent','delivered','read','failed')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP I: Inspections & Maintenance ──────────────────────────────

CREATE TABLE IF NOT EXISTS erp.vistorias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('entrada','saida','periodica')),
  data_vistoria date NOT NULL,
  responsavel_id uuid NOT NULL,
  responsavel_nome text,
  status text NOT NULL DEFAULT 'agendada'
    CHECK (status IN ('agendada','em_andamento','concluida','cancelada')),
  checklist jsonb NOT NULL DEFAULT '[]',
  fotos text[] NOT NULL DEFAULT '{}',
  observacoes_gerais text,
  assinatura_locatario text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.checkins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  imovel_id uuid,
  latitude numeric NOT NULL,
  longitude numeric NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('visita','vistoria','captacao','reuniao')),
  observacoes text,
  fotos text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.vistorias_rapidas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  corretor_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  checkin_id uuid REFERENCES erp.checkins(id),
  estado_geral text NOT NULL
    CHECK (estado_geral IN ('bom','regular','ruim','critico')),
  itens_checklist jsonb NOT NULL DEFAULT '{}',
  observacoes text,
  fotos text[] NOT NULL DEFAULT '{}',
  latitude numeric,
  longitude numeric,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.ordens_servico (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid,
  cliente_id uuid,
  titulo text NOT NULL,
  descricao text NOT NULL,
  tipo text NOT NULL
    CHECK (tipo IN ('preventiva','corretiva','emergencial','reforma')),
  prioridade text NOT NULL DEFAULT 'media'
    CHECK (prioridade IN ('baixa','media','alta','urgente')),
  status text NOT NULL DEFAULT 'aberto'
    CHECK (status IN ('aberto','em_andamento','aguardando','concluido','cancelado')),
  responsavel text,
  fornecedor text,
  custo_estimado numeric,
  custo_real numeric,
  data_abertura date NOT NULL,
  data_previsao date,
  data_conclusao date,
  fotos text[] NOT NULL DEFAULT '{}',
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP J: Insurance ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.seguros (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  cliente_id uuid,
  seguradora text NOT NULL,
  numero_apolice text,
  tipo_cobertura text NOT NULL
    CHECK (tipo_cobertura IN ('incendio','completo','responsabilidade_civil','vida','fianca_locaticia','outro')),
  valor_cobertura numeric NOT NULL,
  valor_premio numeric NOT NULL,
  data_inicio date NOT NULL,
  data_vencimento date NOT NULL,
  status text NOT NULL DEFAULT 'ativo'
    CHECK (status IN ('ativo','vencido','cancelado','renovado')),
  auto_renovar boolean NOT NULL DEFAULT false,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP K: Credit Analysis ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.analises_credito (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid,
  cpf text NOT NULL,
  nome text NOT NULL,
  score int,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente','aprovado','reprovado','em_analise')),
  resultado jsonb NOT NULL DEFAULT '{}',
  fonte text NOT NULL DEFAULT 'manual'
    CHECK (fonte IN ('serasa','boa_vista','manual')),
  validade date,
  consultado_por uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP L: Key Management ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.chaves (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  imovel_id uuid NOT NULL,
  codigo text NOT NULL,
  descricao text,
  status text NOT NULL DEFAULT 'disponivel'
    CHECK (status IN ('disponivel','emprestada','perdida')),
  ultima_retirada_por uuid,
  ultima_retirada_nome text,
  ultima_retirada_em timestamptz,
  ultima_devolucao_em timestamptz,
  observacoes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.chaves_historico (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  chave_id uuid NOT NULL REFERENCES erp.chaves(id) ON DELETE CASCADE,
  acao text NOT NULL CHECK (acao IN ('retirada','devolucao')),
  corretor_id uuid NOT NULL,
  corretor_nome text NOT NULL,
  motivo text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP M: Portals & Site ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.portal_acessos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid NOT NULL,
  token text NOT NULL UNIQUE,
  ativo boolean NOT NULL DEFAULT true,
  data_expiracao timestamptz,
  ultimo_acesso timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.chamados_portal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  cliente_id uuid NOT NULL,
  portal_acesso_id uuid NOT NULL REFERENCES erp.portal_acessos(id) ON DELETE CASCADE,
  assunto text NOT NULL,
  descricao text NOT NULL,
  status text NOT NULL DEFAULT 'aberto'
    CHECK (status IN ('aberto','em_andamento','resolvido','fechado')),
  prioridade text NOT NULL DEFAULT 'media'
    CHECK (prioridade IN ('baixa','media','alta','urgente')),
  resposta text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.portal_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('proprietario','locatario')),
  pessoa_id uuid NOT NULL,
  token text UNIQUE NOT NULL,
  nome text NOT NULL,
  email text,
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.site_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  nome_site text NOT NULL,
  slug text UNIQUE NOT NULL,
  logo_url text,
  cor_primaria text NOT NULL DEFAULT '#6366f1',
  cor_secundaria text NOT NULL DEFAULT '#1a1a2e',
  telefone text,
  whatsapp text,
  email_contato text,
  sobre text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP O: Gamification ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.pontuacoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  acao text NOT NULL,
  pontos int NOT NULL,
  referencia_id uuid,
  referencia_tipo text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.conquistas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  tipo text NOT NULL,
  nome text NOT NULL,
  descricao text,
  icone text NOT NULL DEFAULT '🏆',
  desbloqueada_em timestamptz NOT NULL DEFAULT now()
);

-- ── GROUP P: Distribution, Branches & Banking ───────────────────────

CREATE TABLE IF NOT EXISTS erp.distribuicao_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  modo text NOT NULL DEFAULT 'manual'
    CHECK (modo IN ('manual','round_robin','por_regiao','por_especialidade')),
  corretores_ativos uuid[] NOT NULL DEFAULT '{}',
  proximo_corretor_idx int NOT NULL DEFAULT 0,
  regras jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.filiais (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  nome text NOT NULL,
  codigo text NOT NULL,
  endereco text,
  cidade text,
  estado text,
  telefone text,
  responsavel_id uuid,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.remessas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('cnab240','cnab400')),
  banco text NOT NULL,
  arquivo_nome text,
  total_titulos integer NOT NULL DEFAULT 0,
  valor_total numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'gerado'
    CHECK (status IN ('gerado','enviado','processado','erro')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── Notifications ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.notificacoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  tipo text NOT NULL,
  titulo text NOT NULL,
  mensagem text,
  is_read boolean NOT NULL DEFAULT false,
  link text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.notificacao_preferencias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_id uuid NOT NULL,
  canal text NOT NULL DEFAULT 'app'
    CHECK (canal IN ('app','email','whatsapp')),
  tipo_evento text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(user_id, canal, tipo_evento)
);

ALTER TABLE erp.notificacoes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "org_isolation" ON erp.notificacoes
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

ALTER TABLE erp.notificacao_preferencias ENABLE ROW LEVEL SECURITY;
CREATE POLICY "org_isolation" ON erp.notificacao_preferencias
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

-- ── WAHA WhatsApp Config ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.whatsapp_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  provider text NOT NULL DEFAULT 'meta'
    CHECK (provider IN ('meta','waha')),
  meta_api_token text,
  meta_phone_number_id text,
  meta_api_version text DEFAULT 'v18.0',
  waha_api_url text,
  waha_api_key text,
  waha_session_name text DEFAULT 'default',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── Meta API (Facebook/Instagram) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.meta_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  page_id text,
  access_token text,
  ad_account_id text,
  webhook_verify_token text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.meta_leads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  lead_id text NOT NULL,
  form_id text,
  form_name text,
  campo_data jsonb NOT NULL DEFAULT '{}',
  cliente_id uuid,
  importado boolean NOT NULL DEFAULT false,
  importado_em timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.meta_campanhas_sync (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  campaign_id text NOT NULL,
  nome text,
  status text,
  spend numeric DEFAULT 0,
  impressions integer DEFAULT 0,
  clicks integer DEFAULT 0,
  leads integer DEFAULT 0,
  cpl numeric,
  last_sync timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- filial_id on existing tables
ALTER TABLE erp.ativos ADD COLUMN IF NOT EXISTS filial_id uuid;
ALTER TABLE erp.clientes ADD COLUMN IF NOT EXISTS filial_id uuid;

-- ── Indexes for expansion tables ────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_propostas_org ON erp.propostas(org_id);
CREATE INDEX IF NOT EXISTS idx_propostas_cliente ON erp.propostas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_propostas_imovel ON erp.propostas(imovel_id);
CREATE INDEX IF NOT EXISTS idx_propostas_status ON erp.propostas(status);
CREATE INDEX IF NOT EXISTS idx_contratos_org ON erp.contratos(org_id);
CREATE INDEX IF NOT EXISTS idx_contratos_cliente ON erp.contratos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_contratos_status ON erp.contratos(status);
CREATE INDEX IF NOT EXISTS idx_parcelas_contrato_contrato ON erp.parcelas_contrato(contrato_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_org ON erp.lancamentos(org_id);
CREATE INDEX IF NOT EXISTS idx_lancamentos_status ON erp.lancamentos(status);
CREATE INDEX IF NOT EXISTS idx_lancamentos_vencimento ON erp.lancamentos(data_vencimento);
CREATE INDEX IF NOT EXISTS idx_impostos_org ON erp.impostos(org_id);
CREATE INDEX IF NOT EXISTS idx_impostos_imovel ON erp.impostos(imovel_id);
CREATE INDEX IF NOT EXISTS idx_extratos_org ON erp.extratos_bancarios(org_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_extrato ON erp.movimentacoes_bancarias(extrato_id);
CREATE INDEX IF NOT EXISTS idx_comissoes_org ON erp.comissoes(org_id);
CREATE INDEX IF NOT EXISTS idx_comissoes_status ON erp.comissoes(status);
CREATE INDEX IF NOT EXISTS idx_comissoes_splits_comissao ON erp.comissoes_splits(comissao_id);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_org ON erp.contratos_locacao(org_id);
CREATE INDEX IF NOT EXISTS idx_contratos_locacao_status ON erp.contratos_locacao(status);
CREATE INDEX IF NOT EXISTS idx_eventos_org ON erp.eventos(org_id);
CREATE INDEX IF NOT EXISTS idx_eventos_corretor ON erp.eventos(corretor_id);
CREATE INDEX IF NOT EXISTS idx_eventos_data ON erp.eventos(data_inicio);
CREATE INDEX IF NOT EXISTS idx_documentos_org ON erp.documentos(org_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_org ON erp.assinaturas(org_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_status ON erp.assinaturas(status);
CREATE INDEX IF NOT EXISTS idx_emails_org ON erp.emails(org_id);
CREATE INDEX IF NOT EXISTS idx_campanhas_org ON erp.campanhas(org_id);
CREATE INDEX IF NOT EXISTS idx_envios_email_campanha ON erp.envios_email(campanha_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_org ON erp.whatsapp_messages(org_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_phone ON erp.whatsapp_messages(phone);
CREATE INDEX IF NOT EXISTS idx_vistorias_org ON erp.vistorias(org_id);
CREATE INDEX IF NOT EXISTS idx_vistorias_imovel ON erp.vistorias(imovel_id);
CREATE INDEX IF NOT EXISTS idx_checkins_org ON erp.checkins(org_id);
CREATE INDEX IF NOT EXISTS idx_checkins_corretor ON erp.checkins(corretor_id);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_org ON erp.ordens_servico(org_id);
CREATE INDEX IF NOT EXISTS idx_ordens_servico_status ON erp.ordens_servico(status);
CREATE INDEX IF NOT EXISTS idx_seguros_org ON erp.seguros(org_id);
CREATE INDEX IF NOT EXISTS idx_seguros_imovel ON erp.seguros(imovel_id);
CREATE INDEX IF NOT EXISTS idx_analises_credito_org ON erp.analises_credito(org_id);
CREATE INDEX IF NOT EXISTS idx_analises_credito_cpf ON erp.analises_credito(cpf);
CREATE INDEX IF NOT EXISTS idx_chaves_org ON erp.chaves(org_id);
CREATE INDEX IF NOT EXISTS idx_chaves_imovel ON erp.chaves(imovel_id);
CREATE INDEX IF NOT EXISTS idx_chaves_historico_chave ON erp.chaves_historico(chave_id);
CREATE INDEX IF NOT EXISTS idx_portal_acessos_org ON erp.portal_acessos(org_id);
CREATE INDEX IF NOT EXISTS idx_portal_acessos_token ON erp.portal_acessos(token);
CREATE INDEX IF NOT EXISTS idx_chamados_portal_org ON erp.chamados_portal(org_id);
CREATE INDEX IF NOT EXISTS idx_portal_tokens_org ON erp.portal_tokens(org_id);
CREATE INDEX IF NOT EXISTS idx_site_config_slug ON erp.site_config(slug);
CREATE INDEX IF NOT EXISTS idx_pontuacoes_org ON erp.pontuacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_pontuacoes_user ON erp.pontuacoes(user_id);
CREATE INDEX IF NOT EXISTS idx_conquistas_user ON erp.conquistas(user_id);
CREATE INDEX IF NOT EXISTS idx_filiais_org ON erp.filiais(org_id);
CREATE INDEX IF NOT EXISTS idx_remessas_org ON erp.remessas(org_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_user ON erp.notificacoes(user_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_read ON erp.notificacoes(is_read);
CREATE INDEX IF NOT EXISTS idx_notificacoes_created ON erp.notificacoes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meta_leads_org ON erp.meta_leads(org_id);
CREATE INDEX IF NOT EXISTS idx_meta_leads_lead_id ON erp.meta_leads(lead_id);
CREATE INDEX IF NOT EXISTS idx_meta_campanhas_org ON erp.meta_campanhas_sync(org_id);
CREATE INDEX IF NOT EXISTS idx_ativos_filial ON erp.ativos(filial_id);
CREATE INDEX IF NOT EXISTS idx_clientes_filial ON erp.clientes(filial_id);

-- ── RLS for expansion tables ────────────────────────────────────────

DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'propostas','contratos','parcelas_contrato',
    'lancamentos','impostos','extratos_bancarios','movimentacoes_bancarias',
    'comissoes','comissoes_splits',
    'contratos_locacao','eventos',
    'documentos','document_templates','assinaturas',
    'emails','email_templates','campanhas','envios_email',
    'whatsapp_messages',
    'vistorias','checkins','vistorias_rapidas','ordens_servico',
    'seguros','analises_credito',
    'chaves','chaves_historico',
    'portal_acessos','chamados_portal','portal_tokens','site_config',
    'pontuacoes','conquistas',
    'distribuicao_config','filiais','remessas',
    'notificacoes','notificacao_preferencias',
    'whatsapp_config','meta_config','meta_leads','meta_campanhas_sync'
  ])
  LOOP
    EXECUTE format('ALTER TABLE erp.%I ENABLE ROW LEVEL SECURITY', tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_select_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> ''org_id'')::uuid)',
      tbl || '_select_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_insert_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR INSERT TO authenticated WITH CHECK (org_id = ((SELECT auth.jwt()) ->> ''org_id'')::uuid)',
      tbl || '_insert_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_update_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR UPDATE TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> ''org_id'')::uuid)',
      tbl || '_update_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_delete_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR DELETE TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> ''org_id'')::uuid)',
      tbl || '_delete_policy', tbl
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_service_role_policy', tbl);
    EXECUTE format(
      'CREATE POLICY %I ON erp.%I FOR ALL TO service_role USING (true)',
      tbl || '_service_role_policy', tbl
    );
  END LOOP;
END $$;

-- Public access for portals
DROP POLICY IF EXISTS site_config_anon_read ON erp.site_config;
CREATE POLICY site_config_anon_read ON erp.site_config
  FOR SELECT TO anon USING (is_active = true);
DROP POLICY IF EXISTS portal_tokens_anon_read ON erp.portal_tokens;
CREATE POLICY portal_tokens_anon_read ON erp.portal_tokens
  FOR SELECT TO anon USING (is_active = true AND expires_at > now());
DROP POLICY IF EXISTS portal_acessos_anon_read ON erp.portal_acessos;
CREATE POLICY portal_acessos_anon_read ON erp.portal_acessos
  FOR SELECT TO anon USING (ativo = true);

-- ── Timestamp triggers for expansion tables ─────────────────────────

DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY[
    'propostas','contratos','lancamentos','impostos',
    'comissoes','contratos_locacao','eventos',
    'assinaturas','email_templates','campanhas',
    'vistorias','ordens_servico','seguros',
    'chamados_portal','distribuicao_config',
    'whatsapp_config','meta_config','meta_campanhas_sync'
  ])
  LOOP
    EXECUTE format(
      'CREATE TRIGGER IF NOT EXISTS set_timestamps_%I BEFORE INSERT OR UPDATE ON erp.%I FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp()',
      tbl, tbl
    );
  END LOOP;
END $$;

-- ─────────────────────────────────────────────────────────────────────
-- 12B. CERTIDÕES NEGATIVAS TABLES (inline from 007_certidoes_negativas.sql)
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.certidao_consultas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid,
    created_by uuid NOT NULL,
    tipo_documento text NOT NULL CHECK (tipo_documento IN ('cpf', 'cnpj')),
    documento text NOT NULL,
    nome text NOT NULL,
    data_nascimento text,
    genero text CHECK (genero IS NULL OR genero IN ('M', 'F')),
    rg text,
    nome_mae text,
    nome_pai text,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    total_certidoes int NOT NULL DEFAULT 0,
    concluidas int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS erp.certidao_resultados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    consulta_id uuid NOT NULL REFERENCES erp.certidao_consultas(id) ON DELETE CASCADE,
    org_id uuid,
    tipo text NOT NULL,
    nome_display text NOT NULL,
    ordem int NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'na_fila', 'sucesso', 'erro')),
    analise_ia text,
    arquivo_url text,
    arquivo_nome text,
    api_response jsonb,
    erro_mensagem text,
    api_requested_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_certidao_consultas_org ON erp.certidao_consultas(org_id);
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_status ON erp.certidao_consultas(status);
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_documento ON erp.certidao_consultas(documento);
CREATE INDEX IF NOT EXISTS idx_certidao_resultados_consulta ON erp.certidao_resultados(consulta_id);
CREATE INDEX IF NOT EXISTS idx_certidao_resultados_org ON erp.certidao_resultados(org_id);

ALTER TABLE erp.certidao_consultas ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.certidao_resultados ENABLE ROW LEVEL SECURITY;

CREATE POLICY certidao_consultas_select ON erp.certidao_consultas
    FOR SELECT TO authenticated USING (created_by = (SELECT auth.uid()));
CREATE POLICY certidao_consultas_insert ON erp.certidao_consultas
    FOR INSERT TO authenticated WITH CHECK (created_by = (SELECT auth.uid()));
CREATE POLICY certidao_consultas_update ON erp.certidao_consultas
    FOR UPDATE TO authenticated USING (created_by = (SELECT auth.uid()));
CREATE POLICY certidao_consultas_delete ON erp.certidao_consultas
    FOR DELETE TO authenticated USING (created_by = (SELECT auth.uid()));
CREATE POLICY certidao_consultas_service ON erp.certidao_consultas
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY certidao_resultados_select ON erp.certidao_resultados
    FOR SELECT TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = (SELECT auth.uid()))
    );
CREATE POLICY certidao_resultados_insert ON erp.certidao_resultados
    FOR INSERT TO authenticated WITH CHECK (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = (SELECT auth.uid()))
    );
CREATE POLICY certidao_resultados_update ON erp.certidao_resultados
    FOR UPDATE TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = (SELECT auth.uid()))
    );
CREATE POLICY certidao_resultados_delete ON erp.certidao_resultados
    FOR DELETE TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = (SELECT auth.uid()))
    );
CREATE POLICY certidao_resultados_service ON erp.certidao_resultados
    FOR ALL USING (auth.role() = 'service_role');

CREATE TRIGGER set_certidao_consultas_updated
    BEFORE UPDATE ON erp.certidao_consultas FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();
CREATE TRIGGER set_certidao_resultados_updated
    BEFORE UPDATE ON erp.certidao_resultados FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- Seed sidebar entry
INSERT INTO erp.status_pagina (nome_pagina, status)
VALUES ('certidoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- 12b. MATRÍCULA TEXT EXTRACTION (inline from 008_matricula_extracoes.sql)
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS erp.matricula_extracoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,
    nome_arquivo TEXT NOT NULL,
    tamanho_bytes INTEGER,
    num_paginas INTEGER,
    texto_extraido TEXT,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    erro_mensagem TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE erp.matricula_extracoes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_isolation" ON erp.matricula_extracoes
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_matricula_extracoes_org_id ON erp.matricula_extracoes(org_id);
CREATE INDEX idx_matricula_extracoes_user_id ON erp.matricula_extracoes(user_id);
CREATE INDEX idx_matricula_extracoes_created_at ON erp.matricula_extracoes(created_at DESC);

CREATE TRIGGER set_updated_at_matricula_extracoes
    BEFORE UPDATE ON erp.matricula_extracoes
    FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- ─────────────────────────────────────────────────────────────────────
-- 12c. SUPABASE STORAGE BUCKETS
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public)
VALUES
    ('erp-certidoes', 'erp-certidoes', true),
    ('erp-geral',     'erp-geral',     true)
ON CONFLICT (id) DO NOTHING;

-- RLS policies for storage.objects — scoped by org_id in the file path

CREATE POLICY erp_storage_select ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = ((SELECT auth.jwt()) ->> 'org_id')
    );

CREATE POLICY erp_storage_insert ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = ((SELECT auth.jwt()) ->> 'org_id')
    );

CREATE POLICY erp_storage_update ON storage.objects
    FOR UPDATE TO authenticated
    USING (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = ((SELECT auth.jwt()) ->> 'org_id')
    );

CREATE POLICY erp_storage_delete ON storage.objects
    FOR DELETE TO authenticated
    USING (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = ((SELECT auth.jwt()) ->> 'org_id')
    );

CREATE POLICY erp_storage_service ON storage.objects
    FOR ALL
    USING (
        bucket_id LIKE 'erp-%'
        AND auth.role() = 'service_role'
    );

-- ─────────────────────────────────────────────────────────────────────
-- 13. FINAL GRANTS (ensure all objects have correct permissions)
-- ─────────────────────────────────────────────────────────────────────

GRANT ALL ON ALL TABLES IN SCHEMA erp TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA erp TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA erp TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA erp TO anon, authenticated, service_role;

-- ─────────────────────────────────────────────────────────────────────
-- DONE. Schema is fully set up.
-- ─────────────────────────────────────────────────────────────────────

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/mailing/backend/migrations/001_mailing.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- Mailing Product schema
-- Schema: mailing
-- Description: Email Marketing & Automation platform — contacts, campaigns,
--              automations, templates, send tracking, analytics.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mailing;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA mailing TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA mailing TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA mailing TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- 1. Page status (feature flags) — standard platform table
-- ============================================================================

CREATE TABLE mailing.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON mailing.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- 2. Invitations — standard platform table
-- ============================================================================

CREATE TABLE mailing.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE mailing.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON mailing.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_mailing_invitations_org ON mailing.invitations(org_id);
CREATE INDEX idx_mailing_invitations_token ON mailing.invitations(token);


-- ============================================================================
-- 3. Contacts — email recipients managed by the org
-- ============================================================================

CREATE TABLE mailing.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    nome TEXT,
    telefone TEXT,
    empresa TEXT,
    tags TEXT[] DEFAULT '{}',
    custom_fields JSONB DEFAULT '{}',
    source TEXT DEFAULT 'manual' CHECK (source IN ('manual', 'import', 'sync:erp', 'form', 'api')),
    source_ref TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'unsubscribed', 'bounced', 'complained')),
    unsubscribed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, email)
);

ALTER TABLE mailing.contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "contacts_own_org" ON mailing.contacts
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_mailing_contacts_org_email ON mailing.contacts(org_id, email);
CREATE INDEX idx_mailing_contacts_org_status ON mailing.contacts(org_id, status);
CREATE INDEX idx_mailing_contacts_tags ON mailing.contacts USING GIN(tags);


-- ============================================================================
-- 4. Contact Lists — static lists and dynamic segments
-- ============================================================================

CREATE TABLE mailing.contact_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    tipo TEXT NOT NULL DEFAULT 'static' CHECK (tipo IN ('static', 'dynamic')),
    filtros JSONB DEFAULT '{}',
    contact_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.contact_lists ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lists_own_org" ON mailing.contact_lists
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 5. Contact List Members — join table for static lists
-- ============================================================================

CREATE TABLE mailing.contact_list_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id UUID NOT NULL REFERENCES mailing.contact_lists(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(list_id, contact_id)
);

ALTER TABLE mailing.contact_list_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "list_members_via_list" ON mailing.contact_list_members
    FOR ALL TO authenticated
    USING (
        list_id IN (
            SELECT id FROM mailing.contact_lists
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );


-- ============================================================================
-- 6. Templates — email templates with variable interpolation
-- ============================================================================

CREATE TABLE mailing.templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    assunto TEXT NOT NULL,
    corpo_html TEXT NOT NULL,
    corpo_text TEXT,
    variaveis TEXT[] DEFAULT '{}',
    categoria TEXT DEFAULT 'marketing' CHECK (categoria IN ('marketing', 'transactional', 'follow_up', 'newsletter')),
    ativo BOOLEAN DEFAULT true,
    thumbnail_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "templates_own_org" ON mailing.templates
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 7. Campaigns — one-time email blasts
-- ============================================================================

CREATE TABLE mailing.campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    template_id UUID REFERENCES mailing.templates(id),
    list_id UUID REFERENCES mailing.contact_lists(id),
    assunto_override TEXT,
    remetente_nome TEXT,
    remetente_email TEXT,
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'agendada', 'enviando', 'enviada', 'pausada', 'cancelada')),
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    total_recipients INT DEFAULT 0,
    total_sent INT DEFAULT 0,
    total_failed INT DEFAULT 0,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.campaigns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "campaigns_own_org" ON mailing.campaigns
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 8. Automations — multi-step sequences
-- ============================================================================

CREATE TABLE mailing.automations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('contact_added', 'tag_added', 'list_joined', 'form_submitted', 'manual', 'webhook')),
    trigger_config JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'ativa', 'pausada')),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.automations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "automations_own_org" ON mailing.automations
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 9. Automation Steps — individual steps in a sequence
-- ============================================================================

CREATE TABLE mailing.automation_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    automation_id UUID NOT NULL REFERENCES mailing.automations(id) ON DELETE CASCADE,
    posicao INT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('send_email', 'wait', 'condition', 'add_tag', 'remove_tag', 'move_to_list', 'webhook')),
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.automation_steps ENABLE ROW LEVEL SECURITY;

CREATE POLICY "steps_via_automation" ON mailing.automation_steps
    FOR ALL TO authenticated
    USING (
        automation_id IN (
            SELECT id FROM mailing.automations
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );


-- ============================================================================
-- 10. Automation Enrollments — contacts currently in an automation
-- ============================================================================

CREATE TABLE mailing.automation_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    automation_id UUID NOT NULL REFERENCES mailing.automations(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id) ON DELETE CASCADE,
    current_step_id UUID REFERENCES mailing.automation_steps(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused', 'exited')),
    next_action_at TIMESTAMPTZ,
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE(automation_id, contact_id)
);

ALTER TABLE mailing.automation_enrollments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "enrollments_via_automation" ON mailing.automation_enrollments
    FOR ALL TO authenticated
    USING (
        automation_id IN (
            SELECT id FROM mailing.automations
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_mailing_enrollments_next ON mailing.automation_enrollments(next_action_at)
    WHERE status = 'active';


-- ============================================================================
-- 11. Send Logs — per-recipient send tracking (campaigns + automations)
-- ============================================================================

CREATE TABLE mailing.send_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id),
    email TEXT NOT NULL,
    campaign_id UUID REFERENCES mailing.campaigns(id),
    automation_id UUID REFERENCES mailing.automations(id),
    automation_step_id UUID REFERENCES mailing.automation_steps(id),
    resend_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'complained', 'failed')),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    bounced_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.send_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "send_logs_own_org" ON mailing.send_logs
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_mailing_send_logs_campaign ON mailing.send_logs(campaign_id);
CREATE INDEX idx_mailing_send_logs_resend_id ON mailing.send_logs(resend_message_id);
CREATE INDEX idx_mailing_send_logs_status ON mailing.send_logs(status) WHERE status = 'queued';


-- ============================================================================
-- 12. Link Clicks — individual link click tracking
-- ============================================================================

CREATE TABLE mailing.link_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    send_log_id UUID NOT NULL REFERENCES mailing.send_logs(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    clicked_at TIMESTAMPTZ DEFAULT now(),
    user_agent TEXT,
    ip_address INET
);

ALTER TABLE mailing.link_clicks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "clicks_via_send_log" ON mailing.link_clicks
    FOR ALL TO authenticated
    USING (
        send_log_id IN (
            SELECT id FROM mailing.send_logs
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );


-- ============================================================================
-- 13. Unsubscribes — compliance audit trail (LGPD)
-- ============================================================================

CREATE TABLE mailing.unsubscribes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id),
    email TEXT NOT NULL,
    reason TEXT DEFAULT 'link_click' CHECK (reason IN ('manual', 'link_click', 'complaint', 'admin')),
    campaign_id UUID REFERENCES mailing.campaigns(id),
    unsubscribed_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.unsubscribes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "unsubscribes_own_org" ON mailing.unsubscribes
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 14. Sender Domains — domain verification tracking
-- ============================================================================

CREATE TABLE mailing.sender_domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    domain TEXT NOT NULL,
    resend_domain_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'failed')),
    dns_records JSONB,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.sender_domains ENABLE ROW LEVEL SECURITY;

CREATE POLICY "domains_own_org" ON mailing.sender_domains
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- Seed data — page status for mailing features
-- ============================================================================

INSERT INTO mailing.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('contacts', 'producao'),
    ('lists', 'producao'),
    ('templates', 'producao'),
    ('campaigns', 'producao'),
    ('automations', 'producao'),
    ('analytics', 'producao'),
    ('settings', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/media-scheduling/backend/migrations/001_seed.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- Media Scheduling schema
-- Schema: media_scheduling
-- Description: Minimal product schema that proves the entire shared stack works.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = media_scheduling, public;

CREATE SCHEMA IF NOT EXISTS media_scheduling;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA media_scheduling TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA media_scheduling TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA media_scheduling TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA media_scheduling GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA media_scheduling GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE media_scheduling.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE media_scheduling.status_pagina ENABLE ROW LEVEL SECURITY;

-- Note: this policy intentionally does NOT use `rls_subquery_policy` — that
-- helper always emits `TO authenticated`, but `todos_veem_producao` is an
-- anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON media_scheduling.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE media_scheduling.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE media_scheduling.invitations ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(media_scheduling, "invitations", "invitations_select_own_org",
--   "SELECT", using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")`
-- output (whitespace-normalized). The scaffold's regression test enforces this.
CREATE POLICY "invitations_select_own_org" ON media_scheduling.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_media_scheduling_invitations_org ON media_scheduling.invitations(org_id);
CREATE INDEX idx_media_scheduling_invitations_token ON media_scheduling.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO media_scheduling.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/personal-finance/backend/migrations/001_personal_finance.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- =====================================================================
-- NoctusAI Personal Finance — Database Schema
-- Schema: "personal-finance"
--
-- **Rewritten 2026-05-03 by `pf-org-scoping-migration` Phase 6** to reflect
-- deployed truth. Pre-rewrite this file declared a fictional `user_org_id()`
-- helper + an org-scoped shape that was never actually applied; live state
-- was user-scoped (per the `pf-schema-drift-reconciliation` audit, 2026-04-27).
-- This rewrite makes the migration accurately describe the deployed schema:
-- org-scoped via `public.current_org_id()`, `created_by uuid NULL` audit
-- field, no `user_org_id` schema-local helper, uniform RLS shape.
--
-- Migration 008 still exists on disk and was the transition vehicle that
-- flipped the live DB from user-scoped to org-scoped. On fresh clones it is
-- a near-no-op: 001 already declares truth, and 008's idempotent guards
-- short-circuit the column-rename steps when user_id no longer exists.
-- =====================================================================

-- ===================== SCHEMA & PERMISSIONS =====================
CREATE SCHEMA IF NOT EXISTS "personal-finance";

GRANT USAGE ON SCHEMA "personal-finance" TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA "personal-finance" TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "personal-finance" TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA "personal-finance" TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA "personal-finance" TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA "personal-finance" GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- ===================== ORG SCOPING =====================
-- RLS reads the platform-level `public.current_org_id()` helper (defined in
-- core; reads the JWT `org_id` claim). No PF-local org helper.

-- ===================== ACCOUNTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".contas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN (
        'corrente','poupanca','cartao_credito','investimento',
        'carteira','emprestimo','outro'
    )),
    instituicao TEXT,
    saldo DECIMAL(14,2) DEFAULT 0,
    moeda TEXT DEFAULT 'BRL',
    cor TEXT DEFAULT '#6366f1',
    icone TEXT DEFAULT '🏦',
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== CATEGORIES =====================
-- §7.2=B: per-org seeded copies. RLS is uniform `org_id = current_org_id()`
-- with no NULL branch; defaults are seeded per-org by
-- `app/services/onboarding_service.seed_default_categories`.
CREATE TABLE IF NOT EXISTS "personal-finance".categorias (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa','transferencia')),
    categoria_pai_id UUID REFERENCES "personal-finance".categorias(id),
    icone TEXT,
    cor TEXT,
    tipo_orcamento TEXT CHECK (tipo_orcamento IN ('necessidade','desejo','poupanca')),
    is_sistema BOOLEAN DEFAULT false,
    ordem INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== TRANSACTIONS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".transacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    conta_id UUID NOT NULL REFERENCES "personal-finance".contas(id),
    conta_destino_id UUID REFERENCES "personal-finance".contas(id),
    categoria_id UUID REFERENCES "personal-finance".categorias(id),
    data DATE NOT NULL,
    valor DECIMAL(14,2) NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa','transferencia')),
    descricao TEXT,
    comerciante TEXT,
    notas TEXT,
    tags TEXT[] DEFAULT '{}',
    is_recorrente BOOLEAN DEFAULT false,
    recorrente_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== BUDGETS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".orcamentos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    metodo TEXT DEFAULT 'zero_based' CHECK (metodo IN ('zero_based','50_30_20','custom')),
    periodo TEXT DEFAULT 'mensal' CHECK (periodo IN ('mensal','quinzenal','semanal')),
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".orcamento_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    orcamento_id UUID NOT NULL REFERENCES "personal-finance".orcamentos(id) ON DELETE CASCADE,
    categoria_id UUID NOT NULL REFERENCES "personal-finance".categorias(id),
    valor_planejado DECIMAL(14,2) NOT NULL,
    periodo_mes TEXT NOT NULL,
    valor_gasto DECIMAL(14,2) DEFAULT 0,
    rollover DECIMAL(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== GOALS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".metas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('reserva_emergencia','aposentadoria','viagem','imovel','educacao','outro')),
    valor_alvo DECIMAL(14,2) NOT NULL,
    valor_atual DECIMAL(14,2) DEFAULT 0,
    data_alvo DATE,
    conta_vinculada_id UUID REFERENCES "personal-finance".contas(id),
    prioridade TEXT DEFAULT 'media' CHECK (prioridade IN ('alta','media','baixa')),
    status TEXT DEFAULT 'ativa' CHECK (status IN ('ativa','pausada','concluida','cancelada')),
    icone TEXT DEFAULT '🎯',
    cor TEXT DEFAULT '#10b981',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".meta_contribuicoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    meta_id UUID NOT NULL REFERENCES "personal-finance".metas(id) ON DELETE CASCADE,
    valor DECIMAL(14,2) NOT NULL,
    data DATE NOT NULL,
    fonte TEXT DEFAULT 'manual' CHECK (fonte IN ('manual','automatica','transacao')),
    transacao_id UUID REFERENCES "personal-finance".transacoes(id),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== PORTFOLIOS / INVESTMENTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".carteiras (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    tipo TEXT DEFAULT 'geral' CHECK (tipo IN ('geral','renda_fixa','renda_variavel','cripto','internacional')),
    corretora TEXT,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".ativos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    nome TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN ('acao','fii','etf','cripto','renda_fixa','outro')),
    quantidade DECIMAL(18,8) DEFAULT 0,
    preco_medio DECIMAL(14,4) DEFAULT 0,
    preco_atual DECIMAL(14,4) DEFAULT 0,
    valor_atual DECIMAL(14,2) DEFAULT 0,
    ganho_perda DECIMAL(14,2) DEFAULT 0,
    ganho_perda_pct DECIMAL(8,4) DEFAULT 0,
    setor TEXT,
    last_update TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".operacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    ativo_id UUID REFERENCES "personal-finance".ativos(id),
    ticker TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('compra','venda','dividendo','jcp','desdobramento','grupamento')),
    data DATE NOT NULL,
    quantidade DECIMAL(18,8),
    preco_unitario DECIMAL(14,4),
    taxas DECIMAL(14,2) DEFAULT 0,
    valor_total DECIMAL(14,2) NOT NULL,
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== WATCHLISTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".watchlists (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    nome TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "personal-finance".watchlist_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    watchlist_id UUID NOT NULL REFERENCES "personal-finance".watchlists(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    nome TEXT,
    alerta_preco_acima DECIMAL(14,4),
    alerta_preco_abaixo DECIMAL(14,4),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== RECURRING =====================
CREATE TABLE IF NOT EXISTS "personal-finance".recorrentes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    conta_id UUID REFERENCES "personal-finance".contas(id),
    nome TEXT NOT NULL,
    valor DECIMAL(14,2) NOT NULL,
    categoria_id UUID REFERENCES "personal-finance".categorias(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa')),
    frequencia TEXT NOT NULL CHECK (frequencia IN ('diario','semanal','quinzenal','mensal','bimestral','trimestral','semestral','anual')),
    dia_vencimento INT,
    proxima_data DATE,
    is_automatico BOOLEAN DEFAULT false,
    comerciante TEXT,
    lembrete_dias INT DEFAULT 3,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== PATRIMONY SNAPSHOTS =====================
CREATE TABLE IF NOT EXISTS "personal-finance".patrimonio_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    data DATE NOT NULL,
    total_ativos DECIMAL(14,2) DEFAULT 0,
    total_passivos DECIMAL(14,2) DEFAULT 0,
    patrimonio_liquido DECIMAL(14,2) DEFAULT 0,
    detalhamento JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== MONTHLY SUMMARIES =====================
CREATE TABLE IF NOT EXISTS "personal-finance".resumos_mensais (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_by UUID,
    mes TEXT NOT NULL,
    receita_total DECIMAL(14,2) DEFAULT 0,
    despesa_total DECIMAL(14,2) DEFAULT 0,
    fluxo_liquido DECIMAL(14,2) DEFAULT 0,
    taxa_poupanca DECIMAL(6,2) DEFAULT 0,
    top_categorias JSONB DEFAULT '[]',
    retorno_investimentos DECIMAL(14,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT resumos_mensais_org_id_mes_key UNIQUE (org_id, mes)
);

-- ===================== ALOCACAO ALVO =====================
CREATE TABLE IF NOT EXISTS "personal-finance".alocacao_alvo (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    carteira_id UUID NOT NULL REFERENCES "personal-finance".carteiras(id) ON DELETE CASCADE,
    classe_ativo TEXT NOT NULL,
    percentual_alvo DECIMAL(5,2) NOT NULL,
    percentual_atual DECIMAL(5,2) DEFAULT 0,
    limite_desvio DECIMAL(5,2) DEFAULT 5.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ===================== ROW LEVEL SECURITY =====================
ALTER TABLE "personal-finance".contas ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".categorias ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".transacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".orcamentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".orcamento_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".metas ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".meta_contribuicoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".carteiras ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".ativos ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".operacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".watchlist_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".recorrentes ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".patrimonio_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".resumos_mensais ENABLE ROW LEVEL SECURITY;
ALTER TABLE "personal-finance".alocacao_alvo ENABLE ROW LEVEL SECURITY;

-- All policies use the platform-level `public.current_org_id()` helper.
-- Parent tables filter directly on `org_id`; child tables traverse to parent.

CREATE POLICY contas_org_scoped ON "personal-finance".contas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY categorias_org_scoped ON "personal-finance".categorias
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY transacoes_org_scoped ON "personal-finance".transacoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY orcamentos_org_scoped ON "personal-finance".orcamentos
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY orcamento_itens_org_scoped ON "personal-finance".orcamento_itens
    FOR ALL TO authenticated
    USING (orcamento_id IN (SELECT id FROM "personal-finance".orcamentos WHERE org_id = public.current_org_id()))
    WITH CHECK (orcamento_id IN (SELECT id FROM "personal-finance".orcamentos WHERE org_id = public.current_org_id()));

CREATE POLICY metas_org_scoped ON "personal-finance".metas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY meta_contribuicoes_org_scoped ON "personal-finance".meta_contribuicoes
    FOR ALL TO authenticated
    USING (meta_id IN (SELECT id FROM "personal-finance".metas WHERE org_id = public.current_org_id()))
    WITH CHECK (meta_id IN (SELECT id FROM "personal-finance".metas WHERE org_id = public.current_org_id()));

CREATE POLICY carteiras_org_scoped ON "personal-finance".carteiras
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY ativos_org_scoped ON "personal-finance".ativos
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY operacoes_org_scoped ON "personal-finance".operacoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY watchlists_org_scoped ON "personal-finance".watchlists
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY watchlist_itens_org_scoped ON "personal-finance".watchlist_itens
    FOR ALL TO authenticated
    USING (watchlist_id IN (SELECT id FROM "personal-finance".watchlists WHERE org_id = public.current_org_id()))
    WITH CHECK (watchlist_id IN (SELECT id FROM "personal-finance".watchlists WHERE org_id = public.current_org_id()));

CREATE POLICY recorrentes_org_scoped ON "personal-finance".recorrentes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY patrimonio_org_scoped ON "personal-finance".patrimonio_snapshots
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY resumos_org_scoped ON "personal-finance".resumos_mensais
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY alocacao_org_scoped ON "personal-finance".alocacao_alvo
    FOR ALL TO authenticated
    USING (carteira_id IN (SELECT id FROM "personal-finance".carteiras WHERE org_id = public.current_org_id()))
    WITH CHECK (carteira_id IN (SELECT id FROM "personal-finance".carteiras WHERE org_id = public.current_org_id()));

-- ===================== INDEXES =====================
-- org_id (one per parent table) + business-relevant composites.
CREATE INDEX IF NOT EXISTS idx_contas_org_id ON "personal-finance".contas(org_id);
CREATE INDEX IF NOT EXISTS idx_categorias_org_id ON "personal-finance".categorias(org_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_org_id ON "personal-finance".transacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_org_data ON "personal-finance".transacoes(org_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_orcamentos_org_id ON "personal-finance".orcamentos(org_id);
CREATE INDEX IF NOT EXISTS idx_metas_org_id ON "personal-finance".metas(org_id);
CREATE INDEX IF NOT EXISTS idx_carteiras_org_id ON "personal-finance".carteiras(org_id);
CREATE INDEX IF NOT EXISTS idx_ativos_org_id ON "personal-finance".ativos(org_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_org_id ON "personal-finance".operacoes(org_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_org_id ON "personal-finance".watchlists(org_id);
CREATE INDEX IF NOT EXISTS idx_recorrentes_org_id ON "personal-finance".recorrentes(org_id);
CREATE INDEX IF NOT EXISTS idx_patrimonio_snapshots_org_id ON "personal-finance".patrimonio_snapshots(org_id);
CREATE INDEX IF NOT EXISTS idx_patrimonio_org_data ON "personal-finance".patrimonio_snapshots(org_id, data DESC);
CREATE INDEX IF NOT EXISTS idx_resumos_mensais_org_id ON "personal-finance".resumos_mensais(org_id);

-- FK indexes (child tables + cross-references)
CREATE INDEX IF NOT EXISTS idx_alocacao_alvo_carteira_id ON "personal-finance".alocacao_alvo(carteira_id);
CREATE INDEX IF NOT EXISTS idx_categorias_categoria_pai_id ON "personal-finance".categorias(categoria_pai_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_conta ON "personal-finance".transacoes(conta_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_conta_destino_id ON "personal-finance".transacoes(conta_destino_id);
CREATE INDEX IF NOT EXISTS idx_transacoes_categoria ON "personal-finance".transacoes(categoria_id);
CREATE INDEX IF NOT EXISTS idx_meta_contribuicoes_meta_id ON "personal-finance".meta_contribuicoes(meta_id);
CREATE INDEX IF NOT EXISTS idx_meta_contribuicoes_transacao_id ON "personal-finance".meta_contribuicoes(transacao_id);
CREATE INDEX IF NOT EXISTS idx_metas_conta_vinculada_id ON "personal-finance".metas(conta_vinculada_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_ativo_id ON "personal-finance".operacoes(ativo_id);
CREATE INDEX IF NOT EXISTS idx_orcamento_itens_orcamento_id ON "personal-finance".orcamento_itens(orcamento_id);
CREATE INDEX IF NOT EXISTS idx_orcamento_itens_categoria_id ON "personal-finance".orcamento_itens(categoria_id);
CREATE INDEX IF NOT EXISTS idx_recorrentes_conta_id ON "personal-finance".recorrentes(conta_id);
CREATE INDEX IF NOT EXISTS idx_recorrentes_categoria_id ON "personal-finance".recorrentes(categoria_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_itens_watchlist_id ON "personal-finance".watchlist_itens(watchlist_id);

-- ===================== TIMESTAMPS TRIGGER =====================
CREATE OR REPLACE FUNCTION "personal-finance".set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = "personal-finance", public;

DROP TRIGGER IF EXISTS set_contas_updated_at ON "personal-finance".contas;
CREATE TRIGGER set_contas_updated_at BEFORE UPDATE ON "personal-finance".contas
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_transacoes_updated_at ON "personal-finance".transacoes;
CREATE TRIGGER set_transacoes_updated_at BEFORE UPDATE ON "personal-finance".transacoes
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_ativos_updated_at ON "personal-finance".ativos;
CREATE TRIGGER set_ativos_updated_at BEFORE UPDATE ON "personal-finance".ativos
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_carteiras_updated_at ON "personal-finance".carteiras;
CREATE TRIGGER set_carteiras_updated_at BEFORE UPDATE ON "personal-finance".carteiras
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_metas_updated_at ON "personal-finance".metas;
CREATE TRIGGER set_metas_updated_at BEFORE UPDATE ON "personal-finance".metas
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_recorrentes_updated_at ON "personal-finance".recorrentes;
CREATE TRIGGER set_recorrentes_updated_at BEFORE UPDATE ON "personal-finance".recorrentes
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();
DROP TRIGGER IF EXISTS set_orcamento_itens_updated_at ON "personal-finance".orcamento_itens;
CREATE TRIGGER set_orcamento_itens_updated_at BEFORE UPDATE ON "personal-finance".orcamento_itens
    FOR EACH ROW EXECUTE FUNCTION "personal-finance".set_updated_at();

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/seed/backend/migrations/001_seed.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- Seed Product schema
-- Schema: seed
-- Description: Minimal product schema that proves the entire shared stack works.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = seed, public;

CREATE SCHEMA IF NOT EXISTS seed;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA seed TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA seed TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA seed TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE seed.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE seed.status_pagina ENABLE ROW LEVEL SECURITY;

-- Note: this policy intentionally does NOT use `rls_subquery_policy` — that
-- helper always emits `TO authenticated`, but `todos_veem_producao` is an
-- anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON seed.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE seed.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE seed.invitations ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(seed, "invitations", "invitations_select_own_org",
--   "SELECT", using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")`
-- output (whitespace-normalized). The scaffold's regression test enforces this.
CREATE POLICY "invitations_select_own_org" ON seed.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_seed_invitations_org ON seed.invitations(org_id);
CREATE INDEX idx_seed_invitations_token ON seed.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO seed.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/therapy-platform/backend/migrations/001_therapy_platform.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- =====================================================================
-- Therapy Platform — Consolidated Schema Migration
-- All therapy objects live in the `therapy` schema.
-- Core platform tables stay in `public`.
-- Run this once on a fresh Supabase project (after core migration).
-- =====================================================================

-- -----------------------------------------------------------------
-- 0. SCHEMA + PERMISSIONS
-- -----------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS therapy;

GRANT USAGE ON SCHEMA therapy TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA therapy TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA therapy TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA therapy TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA therapy TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- -----------------------------------------------------------------
-- 1. HELPER FUNCTIONS
-- -----------------------------------------------------------------

-- Generic updated_at trigger
CREATE OR REPLACE FUNCTION therapy.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = therapy, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- Role helper: returns the current user's role from JWT claims
CREATE OR REPLACE FUNCTION therapy.current_user_role()
  RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = therapy, public
AS $$ SELECT COALESCE((SELECT current_setting('request.jwt.claims', true))::json->'user_metadata'->>'role', 'patient'); $$;

-- Clinic helper: returns the current user's clinic_id from JWT claims
CREATE OR REPLACE FUNCTION therapy.current_clinic_id()
  RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = therapy, public
AS $$ SELECT ((SELECT current_setting('request.jwt.claims', true))::json->'user_metadata'->>'clinic_id')::uuid; $$;

-- -----------------------------------------------------------------
-- 2. TABLES (39 total)
-- -----------------------------------------------------------------

-- ======================== Identity (3) ========================

CREATE TABLE IF NOT EXISTS therapy.clinics (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    cnpj TEXT,
    responsible_person TEXT,
    contact_email TEXT,
    phone TEXT,
    logo_url TEXT,
    description TEXT,
    tagline TEXT,
    specialties_offered TEXT[],
    is_approved BOOLEAN DEFAULT false,
    approved_at TIMESTAMPTZ,
    approved_by UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS therapy.therapist_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    clinic_id UUID REFERENCES therapy.clinics(id),
    crp TEXT NOT NULL,
    bio TEXT,
    specialties TEXT[],
    approaches TEXT[],
    photo_url TEXT,
    default_session_price DECIMAL(10,2),
    session_duration_minutes INT DEFAULT 50,
    is_approved BOOLEAN DEFAULT false,
    approved_at TIMESTAMPTZ,
    approved_by UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS therapy.patient_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    current_therapist_id UUID,
    origin TEXT NOT NULL DEFAULT 'platform' CHECK (origin IN ('platform', 'platform_assigned', 'clinic', 'therapist')),
    clinic_id UUID REFERENCES therapy.clinics(id),
    assigned_by_admin_id UUID,
    assigned_at TIMESTAMPTZ,
    phone TEXT,
    photo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true
);

-- ======================== Clinic Config (3) ========================

CREATE TABLE IF NOT EXISTS therapy.clinic_settings (
    clinic_id UUID PRIMARY KEY REFERENCES therapy.clinics(id),
    bank_name TEXT,
    bank_agency TEXT,
    bank_account TEXT,
    pix_key TEXT,
    notification_email_to TEXT,
    default_commission_pct_clinic_sourced DECIMAL(5,2) DEFAULT 30.00,
    default_commission_pct_therapist_sourced DECIMAL(5,2) DEFAULT 10.00
);

CREATE TABLE IF NOT EXISTS therapy.clinic_therapist_config (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id),
    therapist_id UUID NOT NULL,
    pricing_policy TEXT NOT NULL DEFAULT 'therapist_controls' CHECK (pricing_policy IN ('clinic_controls', 'therapist_controls')),
    commission_override_clinic_sourced DECIMAL(5,2),
    commission_override_therapist_sourced DECIMAL(5,2),
    clinic_set_default_price DECIMAL(10,2),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(clinic_id, therapist_id)
);

CREATE TABLE IF NOT EXISTS therapy.clinic_branding (
    clinic_id UUID PRIMARY KEY REFERENCES therapy.clinics(id),
    primary_color TEXT DEFAULT '#8b5cf6',
    secondary_color TEXT DEFAULT '#6d28d9',
    logo_url TEXT,
    favicon_url TEXT
);

-- ======================== Commission + Pricing (2) ========================

CREATE TABLE IF NOT EXISTS therapy.platform_commission_overrides (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('clinic', 'therapist')),
    target_id UUID NOT NULL,
    custom_commission_pct DECIMAL(5,2) NOT NULL,
    set_by_admin_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(target_type, target_id)
);

CREATE TABLE IF NOT EXISTS therapy.patient_pricing (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    clinic_id UUID,
    custom_price DECIMAL(10,2) NOT NULL,
    set_by TEXT NOT NULL CHECK (set_by IN ('therapist', 'clinic_admin', 'platform_admin')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(therapist_id, patient_id)
);

-- ======================== Therapist Config (1) ========================

CREATE TABLE IF NOT EXISTS therapy.therapist_settings (
    therapist_id UUID PRIMARY KEY,
    bank_name TEXT,
    bank_agency TEXT,
    bank_account TEXT,
    pix_key TEXT,
    openai_api_key TEXT,
    google_connected BOOLEAN DEFAULT false,
    google_refresh_token TEXT,
    notification_email_to TEXT
);

-- ======================== Scheduling (3) ========================

CREATE TABLE IF NOT EXISTS therapy.availability_slots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    day_of_week INT CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_recurring BOOLEAN DEFAULT true,
    specific_date DATE,
    is_blocked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.recurring_schedules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    clinic_id UUID,
    frequency TEXT NOT NULL DEFAULT 'weekly' CHECK (frequency IN ('weekly', 'biweekly', 'monthly', 'custom')),
    custom_interval_weeks INT,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 50,
    start_date DATE NOT NULL,
    end_condition TEXT NOT NULL DEFAULT 'indefinite' CHECK (end_condition IN ('indefinite', 'after_n_occurrences', 'on_date')),
    end_after_n INT,
    end_on_date DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'ended')),
    created_by_type TEXT NOT NULL CHECK (created_by_type IN ('therapist', 'clinic_admin', 'patient_request')),
    created_by_user_id UUID NOT NULL,
    approved_by_user_id UUID,
    paused_at TIMESTAMPTZ,
    resumed_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    total_completed INT DEFAULT 0,
    total_absences INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    clinic_id UUID,
    recurring_schedule_id UUID REFERENCES therapy.recurring_schedules(id),
    patient_origin TEXT NOT NULL DEFAULT 'platform' CHECK (patient_origin IN ('clinic_sourced', 'therapist_sourced', 'independent', 'platform_assigned')),
    session_price_applied DECIMAL(10,2),
    platform_fee_pct_applied DECIMAL(5,2),
    clinic_commission_pct_applied DECIMAL(5,2),
    scheduled_start TIMESTAMPTZ NOT NULL,
    scheduled_end TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'in_progress', 'paused', 'completed', 'cancelled', 'late_cancelled', 'no_show', 'payment_pending', 'payment_failed')),
    video_room_id UUID,
    meeting_link TEXT,
    google_event_id TEXT,
    payment_id TEXT,
    is_auto_generated BOOLEAN DEFAULT false,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    patient_attended BOOLEAN,
    therapist_attended BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Video / Session (5) ========================

CREATE TABLE IF NOT EXISTS therapy.video_rooms (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL UNIQUE,
    livekit_room_name TEXT,
    room_token TEXT,
    meeting_url TEXT NOT NULL,
    accessible_from TIMESTAMPTZ NOT NULL,
    accessible_until TIMESTAMPTZ NOT NULL,
    reopen_until TIMESTAMPTZ,
    reopen_count INT DEFAULT 0,
    reopen_button_visible_until TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'waiting', 'active', 'paused', 'closed', 'auto_finalized', 'reopened')),
    total_pauses INT DEFAULT 0,
    therapist_joined_at TIMESTAMPTZ,
    patient_joined_at TIMESTAMPTZ,
    session_started_at TIMESTAMPTZ,
    session_ended_at TIMESTAMPTZ,
    last_paused_at TIMESTAMPTZ,
    last_resumed_at TIMESTAMPTZ,
    last_reopened_at TIMESTAMPTZ,
    auto_finalized_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.session_audio_segments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_room_id UUID NOT NULL REFERENCES therapy.video_rooms(id) ON DELETE CASCADE,
    segment_number INT NOT NULL,
    segment_type TEXT NOT NULL DEFAULT 'initial' CHECK (segment_type IN ('initial', 'resumed', 'reopened')),
    audio_file_url TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    transcription_text TEXT,
    is_transcribed BOOLEAN DEFAULT false,
    download_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.session_interruptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_room_id UUID NOT NULL REFERENCES therapy.video_rooms(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('pause', 'resume', 'disconnect', 'reconnect', 'reopen', 'end')),
    participant_type TEXT NOT NULL CHECK (participant_type IN ('therapist', 'patient', 'system')),
    participant_user_id UUID,
    reason TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    interruption_duration_seconds INT
);

CREATE TABLE IF NOT EXISTS therapy.session_records (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL UNIQUE,
    combined_transcript_text TEXT,
    therapist_notes_private TEXT,
    total_segments INT DEFAULT 1,
    ai_generated_at TIMESTAMPTZ,
    audio_deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.session_observations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
    observation_text TEXT NOT NULL,
    is_initial BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

-- ======================== Clinical / AI (5) ========================

CREATE TABLE IF NOT EXISTS therapy.session_summary_versions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
    track TEXT NOT NULL CHECK (track IN ('base', 'clinical')),
    version_number INT NOT NULL,
    summary TEXT NOT NULL,
    key_points TEXT[],
    tags TEXT[],
    source TEXT NOT NULL DEFAULT 'ai_generated' CHECK (source IN ('ai_generated', 'ai_auto_fallback', 'manual_edit')),
    observation_snapshot_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.patient_session_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.clinical_longitudinal_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    version_number INT NOT NULL,
    narrative_summary TEXT NOT NULL,
    recurring_themes TEXT[],
    progress_timeline TEXT[],
    unresolved_topics TEXT[],
    observation_insights TEXT,
    session_count_at_generation INT NOT NULL,
    clinical_summary_version_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.patient_longitudinal_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    version_number INT NOT NULL,
    narrative_summary TEXT NOT NULL,
    recurring_themes TEXT[],
    progress_reflection TEXT[],
    ongoing_topics TEXT[],
    session_count_at_generation INT NOT NULL,
    base_summary_version_ids UUID[],
    patient_note_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.patient_longitudinal_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    longitudinal_analysis_id UUID REFERENCES therapy.clinical_longitudinal_analyses(id),
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Financial (6) ========================

CREATE TABLE IF NOT EXISTS therapy.wallets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id UUID NOT NULL,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('patient', 'therapist', 'clinic')),
    balance DECIMAL(14,2) NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT now(),
    UNIQUE(owner_id, owner_type)
);

CREATE TABLE IF NOT EXISTS therapy.wallet_movements (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    wallet_id UUID NOT NULL REFERENCES therapy.wallets(id),
    type TEXT NOT NULL CHECK (type IN ('credit', 'debit')),
    amount DECIMAL(10,2) NOT NULL,
    reference_type TEXT NOT NULL CHECK (reference_type IN ('session_commission', 'voluntary_transfer', 'withdrawal', 'refund', 'top_up', 'no_show_fee')),
    reference_id UUID,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    patient_origin TEXT NOT NULL,
    gross_amount DECIMAL(10,2) NOT NULL,
    platform_fee_pct DECIMAL(5,2) NOT NULL,
    platform_fee_amount DECIMAL(10,2) NOT NULL,
    clinic_commission_pct DECIMAL(5,2),
    clinic_share_amount DECIMAL(10,2),
    therapist_share_amount DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pre_authorized' CHECK (status IN ('pre_authorized', 'captured', 'refunded', 'failed', 'released')),
    gateway_ref TEXT,
    pre_authorized_at TIMESTAMPTZ,
    captured_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.clinic_transfers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id),
    therapist_id UUID NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    reason TEXT NOT NULL,
    initiated_by_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.payouts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    recipient_id UUID NOT NULL,
    recipient_type TEXT NOT NULL CHECK (recipient_type IN ('patient', 'therapist', 'clinic')),
    amount DECIMAL(10,2) NOT NULL,
    fee_pct DECIMAL(5,2) NOT NULL DEFAULT 2.00,
    fee_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    bank_details_snapshot JSONB,
    requested_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.refund_requests (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    transaction_id UUID NOT NULL REFERENCES therapy.transactions(id),
    appointment_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    reviewed_by_admin_id UUID,
    review_response TEXT,
    refund_amount DECIMAL(10,2) NOT NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Reviews (3) ========================

CREATE TABLE IF NOT EXISTS therapy.reviews (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    star_rating INT NOT NULL CHECK (star_rating BETWEEN 1 AND 5),
    review_text TEXT,
    tags TEXT[],
    is_flagged BOOLEAN DEFAULT false,
    flagged_by_therapist_id UUID,
    flagged_reason TEXT,
    is_hidden BOOLEAN DEFAULT false,
    hidden_by_admin_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(patient_id, therapist_id)
);

CREATE TABLE IF NOT EXISTS therapy.clinic_reviews (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id),
    star_rating INT NOT NULL CHECK (star_rating BETWEEN 1 AND 5),
    review_text TEXT,
    tags TEXT[],
    is_flagged BOOLEAN DEFAULT false,
    flagged_by_clinic_admin_id UUID,
    flagged_reason TEXT,
    is_hidden BOOLEAN DEFAULT false,
    hidden_by_admin_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(patient_id, clinic_id)
);

CREATE TABLE IF NOT EXISTS therapy.review_responses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    review_id UUID REFERENCES therapy.reviews(id),
    clinic_review_id UUID REFERENCES therapy.clinic_reviews(id),
    responder_id UUID NOT NULL,
    response_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CHECK (review_id IS NOT NULL OR clinic_review_id IS NOT NULL)
);

-- ======================== Messaging (5) ========================

CREATE TABLE IF NOT EXISTS therapy.conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'human' CHECK (mode IN ('human', 'ai_managed', 'hybrid')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_message_at TIMESTAMPTZ,
    is_archived BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS therapy.conversation_participants (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES therapy.conversations(id) ON DELETE CASCADE,
    participant_type TEXT NOT NULL CHECK (participant_type IN ('user', 'clinic', 'platform_support')),
    participant_id UUID,
    clinic_id UUID,
    last_read_message_id UUID,
    is_muted BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,
    is_blocked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(conversation_id, participant_id, participant_type)
);

CREATE TABLE IF NOT EXISTS therapy.messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES therapy.conversations(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL CHECK (sender_type IN ('user', 'clinic_entity', 'platform_support', 'ai_agent')),
    sender_user_id UUID,
    sender_clinic_id UUID,
    message_type TEXT NOT NULL DEFAULT 'text' CHECK (message_type IN ('text', 'system', 'ai', 'image', 'audio')),
    content TEXT,
    file_url TEXT,
    file_type TEXT,
    file_size INT,
    ai_processed_content TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.message_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES therapy.conversations(id),
    message_id UUID REFERENCES therapy.messages(id),
    reported_by_user_id UUID NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'resolved')),
    reviewed_by_admin_id UUID,
    resolution TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.user_blocks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    blocker_user_id UUID NOT NULL,
    blocked_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(blocker_user_id, blocked_user_id)
);

-- ======================== Config (2) ========================

CREATE TABLE IF NOT EXISTS therapy.platform_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.platform_settings_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    setting_key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    changed_by_admin_id UUID NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Action Log (1) ========================

CREATE TABLE IF NOT EXISTS therapy.action_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    tipo_acao TEXT NOT NULL,
    tipo_entidade TEXT NOT NULL,
    entidade_id TEXT,
    descricao TEXT,
    detalhes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 3. INDEXES
-- -----------------------------------------------------------------

-- Identity
CREATE INDEX IF NOT EXISTS idx_therapist_profiles_clinic_id ON therapy.therapist_profiles(clinic_id);
CREATE INDEX IF NOT EXISTS idx_therapist_profiles_is_approved ON therapy.therapist_profiles(is_approved);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_current_therapist ON therapy.patient_profiles(current_therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_clinic_id ON therapy.patient_profiles(clinic_id);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_origin ON therapy.patient_profiles(origin);

-- Clinic Config
CREATE INDEX IF NOT EXISTS idx_clinic_therapist_config_clinic ON therapy.clinic_therapist_config(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_therapist_config_therapist ON therapy.clinic_therapist_config(therapist_id);

-- Commission + Pricing
CREATE INDEX IF NOT EXISTS idx_platform_commission_target ON therapy.platform_commission_overrides(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_patient_pricing_therapist ON therapy.patient_pricing(therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_pricing_patient ON therapy.patient_pricing(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_pricing_clinic ON therapy.patient_pricing(clinic_id);

-- Scheduling
CREATE INDEX IF NOT EXISTS idx_availability_therapist ON therapy.availability_slots(therapist_id);
CREATE INDEX IF NOT EXISTS idx_availability_clinic ON therapy.availability_slots(clinic_id);
CREATE INDEX IF NOT EXISTS idx_availability_day ON therapy.availability_slots(day_of_week);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_therapist_status ON therapy.recurring_schedules(therapist_id, status);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_patient ON therapy.recurring_schedules(patient_id);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_clinic ON therapy.recurring_schedules(clinic_id);
CREATE INDEX IF NOT EXISTS idx_appointments_therapist_start ON therapy.appointments(therapist_id, scheduled_start);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON therapy.appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_clinic ON therapy.appointments(clinic_id);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON therapy.appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_recurring ON therapy.appointments(recurring_schedule_id);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled_start ON therapy.appointments(scheduled_start);

-- Video / Session
CREATE INDEX IF NOT EXISTS idx_video_rooms_appointment ON therapy.video_rooms(appointment_id);
CREATE INDEX IF NOT EXISTS idx_video_rooms_status ON therapy.video_rooms(status);
CREATE INDEX IF NOT EXISTS idx_session_audio_segments_room ON therapy.session_audio_segments(video_room_id);
CREATE INDEX IF NOT EXISTS idx_session_interruptions_room ON therapy.session_interruptions(video_room_id);
CREATE INDEX IF NOT EXISTS idx_session_records_appointment ON therapy.session_records(appointment_id);
CREATE INDEX IF NOT EXISTS idx_session_observations_record ON therapy.session_observations(session_record_id);

-- Clinical / AI
CREATE INDEX IF NOT EXISTS idx_session_summary_versions_record_track ON therapy.session_summary_versions(session_record_id, track);
CREATE INDEX IF NOT EXISTS idx_patient_session_notes_record ON therapy.patient_session_notes(session_record_id);
CREATE INDEX IF NOT EXISTS idx_patient_session_notes_patient ON therapy.patient_session_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_clinical_longitudinal_patient ON therapy.clinical_longitudinal_analyses(patient_id);
CREATE INDEX IF NOT EXISTS idx_clinical_longitudinal_therapist ON therapy.clinical_longitudinal_analyses(therapist_id);
CREATE INDEX IF NOT EXISTS idx_clinical_longitudinal_clinic ON therapy.clinical_longitudinal_analyses(clinic_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_patient ON therapy.patient_longitudinal_analyses(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_therapist ON therapy.patient_longitudinal_analyses(therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_notes_patient ON therapy.patient_longitudinal_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_notes_therapist ON therapy.patient_longitudinal_notes(therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_notes_analysis ON therapy.patient_longitudinal_notes(longitudinal_analysis_id);

-- Financial
CREATE INDEX IF NOT EXISTS idx_wallets_owner ON therapy.wallets(owner_id, owner_type);
CREATE INDEX IF NOT EXISTS idx_wallet_movements_wallet_created ON therapy.wallet_movements(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_movements_reference ON therapy.wallet_movements(reference_type, reference_id);
CREATE INDEX IF NOT EXISTS idx_transactions_appointment ON therapy.transactions(appointment_id);
CREATE INDEX IF NOT EXISTS idx_transactions_patient ON therapy.transactions(patient_id);
CREATE INDEX IF NOT EXISTS idx_transactions_therapist ON therapy.transactions(therapist_id);
CREATE INDEX IF NOT EXISTS idx_transactions_clinic ON therapy.transactions(clinic_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON therapy.transactions(status);
CREATE INDEX IF NOT EXISTS idx_clinic_transfers_clinic ON therapy.clinic_transfers(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_transfers_therapist ON therapy.clinic_transfers(therapist_id);
CREATE INDEX IF NOT EXISTS idx_payouts_recipient ON therapy.payouts(recipient_id, recipient_type);
CREATE INDEX IF NOT EXISTS idx_payouts_status ON therapy.payouts(status);
CREATE INDEX IF NOT EXISTS idx_refund_requests_transaction ON therapy.refund_requests(transaction_id);
CREATE INDEX IF NOT EXISTS idx_refund_requests_patient ON therapy.refund_requests(patient_id);
CREATE INDEX IF NOT EXISTS idx_refund_requests_status ON therapy.refund_requests(status);

-- Reviews
CREATE INDEX IF NOT EXISTS idx_reviews_therapist ON therapy.reviews(therapist_id);
CREATE INDEX IF NOT EXISTS idx_reviews_patient ON therapy.reviews(patient_id);
CREATE INDEX IF NOT EXISTS idx_reviews_clinic ON therapy.reviews(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_reviews_clinic ON therapy.clinic_reviews(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_reviews_patient ON therapy.clinic_reviews(patient_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_review ON therapy.review_responses(review_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_clinic_review ON therapy.review_responses(clinic_review_id);

-- Messaging
CREATE INDEX IF NOT EXISTS idx_conversation_participants_conversation ON therapy.conversation_participants(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_user ON therapy.conversation_participants(participant_id);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_clinic ON therapy.conversation_participants(clinic_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON therapy.messages(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON therapy.messages(sender_user_id);
CREATE INDEX IF NOT EXISTS idx_message_reports_conversation ON therapy.message_reports(conversation_id);
CREATE INDEX IF NOT EXISTS idx_message_reports_status ON therapy.message_reports(status);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker ON therapy.user_blocks(blocker_user_id);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON therapy.user_blocks(blocked_user_id);

-- Config
CREATE INDEX IF NOT EXISTS idx_platform_settings_history_key ON therapy.platform_settings_history(setting_key);

-- Action Log
CREATE INDEX IF NOT EXISTS idx_action_log_user ON therapy.action_log(user_id);
CREATE INDEX IF NOT EXISTS idx_action_log_entidade ON therapy.action_log(tipo_entidade, entidade_id);
CREATE INDEX IF NOT EXISTS idx_action_log_created ON therapy.action_log(created_at DESC);

-- -----------------------------------------------------------------
-- 4. UPDATED_AT TRIGGERS
-- -----------------------------------------------------------------

-- clinics
CREATE OR REPLACE TRIGGER set_updated_at_clinics
    BEFORE UPDATE ON therapy.clinics
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- therapist_profiles
CREATE OR REPLACE TRIGGER set_updated_at_therapist_profiles
    BEFORE UPDATE ON therapy.therapist_profiles
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_profiles
CREATE OR REPLACE TRIGGER set_updated_at_patient_profiles
    BEFORE UPDATE ON therapy.patient_profiles
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- clinic_therapist_config
CREATE OR REPLACE TRIGGER set_updated_at_clinic_therapist_config
    BEFORE UPDATE ON therapy.clinic_therapist_config
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- platform_commission_overrides
CREATE OR REPLACE TRIGGER set_updated_at_platform_commission_overrides
    BEFORE UPDATE ON therapy.platform_commission_overrides
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_pricing
CREATE OR REPLACE TRIGGER set_updated_at_patient_pricing
    BEFORE UPDATE ON therapy.patient_pricing
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- recurring_schedules
CREATE OR REPLACE TRIGGER set_updated_at_recurring_schedules
    BEFORE UPDATE ON therapy.recurring_schedules
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- appointments
CREATE OR REPLACE TRIGGER set_updated_at_appointments
    BEFORE UPDATE ON therapy.appointments
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- session_observations
CREATE OR REPLACE TRIGGER set_updated_at_session_observations
    BEFORE UPDATE ON therapy.session_observations
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_session_notes
CREATE OR REPLACE TRIGGER set_updated_at_patient_session_notes
    BEFORE UPDATE ON therapy.patient_session_notes
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_longitudinal_notes
CREATE OR REPLACE TRIGGER set_updated_at_patient_longitudinal_notes
    BEFORE UPDATE ON therapy.patient_longitudinal_notes
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- refund_requests
CREATE OR REPLACE TRIGGER set_updated_at_refund_requests
    BEFORE UPDATE ON therapy.refund_requests
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- reviews
CREATE OR REPLACE TRIGGER set_updated_at_reviews
    BEFORE UPDATE ON therapy.reviews
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- clinic_reviews
CREATE OR REPLACE TRIGGER set_updated_at_clinic_reviews
    BEFORE UPDATE ON therapy.clinic_reviews
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- review_responses
CREATE OR REPLACE TRIGGER set_updated_at_review_responses
    BEFORE UPDATE ON therapy.review_responses
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- conversations
CREATE OR REPLACE TRIGGER set_updated_at_conversations
    BEFORE UPDATE ON therapy.conversations
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- messages
CREATE OR REPLACE TRIGGER set_updated_at_messages
    BEFORE UPDATE ON therapy.messages
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- platform_settings
CREATE OR REPLACE TRIGGER set_updated_at_platform_settings
    BEFORE UPDATE ON therapy.platform_settings
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- -----------------------------------------------------------------
-- 5. ROW LEVEL SECURITY
-- -----------------------------------------------------------------

-- Enable RLS on all tables
ALTER TABLE therapy.clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.therapist_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_therapist_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_branding ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.platform_commission_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_pricing ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.therapist_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.availability_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.recurring_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.video_rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_audio_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_interruptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_summary_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_session_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinical_longitudinal_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_longitudinal_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_longitudinal_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.wallet_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.refund_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.review_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.conversation_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.message_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.user_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.platform_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.platform_settings_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.action_log ENABLE ROW LEVEL SECURITY;

-- Service role bypass on all tables (backend handles authorization in Python)
CREATE POLICY "service_role_bypass" ON therapy.clinics FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.therapist_profiles FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_profiles FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_therapist_config FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_branding FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.platform_commission_overrides FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_pricing FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.therapist_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.availability_slots FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.recurring_schedules FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.appointments FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.video_rooms FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_audio_segments FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_interruptions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_records FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_observations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_summary_versions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_session_notes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinical_longitudinal_analyses FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_longitudinal_analyses FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_longitudinal_notes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.wallets FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.wallet_movements FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.transactions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_transfers FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.payouts FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.refund_requests FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.reviews FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_reviews FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.review_responses FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.conversations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.conversation_participants FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.messages FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.message_reports FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.user_blocks FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.platform_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.platform_settings_history FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.action_log FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Role-based RLS policies (replace blanket authenticated_access)
-- Helpers: (SELECT therapy.current_user_role()), (SELECT therapy.current_clinic_id()), (SELECT auth.uid())

-- ======================== clinics ========================
CREATE POLICY "clinics_select" ON therapy.clinics FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR id = (SELECT therapy.current_clinic_id())
    OR is_approved = true
);
CREATE POLICY "clinics_insert" ON therapy.clinics FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) IN ('platform_admin', 'clinic_admin')
);
CREATE POLICY "clinics_update" ON therapy.clinics FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR (id = (SELECT therapy.current_clinic_id()) AND (SELECT therapy.current_user_role()) = 'clinic_admin')
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR (id = (SELECT therapy.current_clinic_id()) AND (SELECT therapy.current_user_role()) = 'clinic_admin')
);
CREATE POLICY "clinics_delete" ON therapy.clinics FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== therapist_profiles ========================
CREATE POLICY "therapist_profiles_select" ON therapy.therapist_profiles FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
    OR clinic_id = (SELECT therapy.current_clinic_id())
    OR (is_approved = true AND is_active = true)
);
CREATE POLICY "therapist_profiles_write" ON therapy.therapist_profiles FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
);

-- ======================== patient_profiles ========================
CREATE POLICY "patient_profiles_select" ON therapy.patient_profiles FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.patient_id = patient_profiles.user_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);
CREATE POLICY "patient_profiles_write" ON therapy.patient_profiles FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
);

-- ======================== appointments ========================
CREATE POLICY "appointments_select" ON therapy.appointments FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "appointments_write" ON therapy.appointments FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "appointments_update" ON therapy.appointments FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "appointments_delete" ON therapy.appointments FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);

-- ======================== availability_slots ========================
CREATE POLICY "availability_slots_select" ON therapy.availability_slots FOR SELECT TO authenticated USING (true);
CREATE POLICY "availability_slots_write" ON therapy.availability_slots FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
);
CREATE POLICY "availability_slots_update" ON therapy.availability_slots FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
);
CREATE POLICY "availability_slots_delete" ON therapy.availability_slots FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== recurring_schedules ========================
CREATE POLICY "recurring_schedules_access" ON therapy.recurring_schedules FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);

-- ======================== video_rooms ========================
CREATE POLICY "video_rooms_access" ON therapy.video_rooms FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = video_rooms.appointment_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = video_rooms.appointment_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
);

-- ======================== session_records ========================
CREATE POLICY "session_records_access" ON therapy.session_records FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = session_records.appointment_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = session_records.appointment_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== session_observations ========================
CREATE POLICY "session_observations_access" ON therapy.session_observations FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_observations.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_observations.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== session_audio_segments ========================
CREATE POLICY "session_audio_segments_access" ON therapy.session_audio_segments FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.video_rooms vr
        JOIN therapy.appointments a ON a.id = vr.appointment_id
        WHERE vr.id = session_audio_segments.video_room_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.video_rooms vr
        JOIN therapy.appointments a ON a.id = vr.appointment_id
        WHERE vr.id = session_audio_segments.video_room_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== session_summary_versions ========================
CREATE POLICY "session_summary_versions_access" ON therapy.session_summary_versions FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_summary_versions.session_record_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_summary_versions.session_record_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
);

-- ======================== session_interruptions ========================
CREATE POLICY "session_interruptions_access" ON therapy.session_interruptions FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_user_id = (SELECT auth.uid())
);

-- ======================== patient_session_notes ========================
CREATE POLICY "patient_session_notes_access" ON therapy.patient_session_notes FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = patient_session_notes.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = patient_session_notes.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== clinical_longitudinal_analyses ========================
CREATE POLICY "clinical_longitudinal_analyses_access" ON therapy.clinical_longitudinal_analyses FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);

-- ======================== patient_longitudinal_analyses ========================
CREATE POLICY "patient_longitudinal_analyses_access" ON therapy.patient_longitudinal_analyses FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== patient_longitudinal_notes ========================
CREATE POLICY "patient_longitudinal_notes_access" ON therapy.patient_longitudinal_notes FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== wallets ========================
CREATE POLICY "wallets_select" ON therapy.wallets FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR owner_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND owner_type = 'clinic' AND owner_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "wallets_write" ON therapy.wallets FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "wallets_update" ON therapy.wallets FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "wallets_delete" ON therapy.wallets FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== wallet_movements ========================
CREATE POLICY "wallet_movements_select" ON therapy.wallet_movements FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.wallets w
        WHERE w.id = wallet_movements.wallet_id
          AND w.owner_id = (SELECT auth.uid())
    )
);
CREATE POLICY "wallet_movements_write" ON therapy.wallet_movements FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== transactions ========================
CREATE POLICY "transactions_select" ON therapy.transactions FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "transactions_write" ON therapy.transactions FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "transactions_update" ON therapy.transactions FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_transfers ========================
CREATE POLICY "clinic_transfers_access" ON therapy.clinic_transfers FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== payouts ========================
CREATE POLICY "payouts_access" ON therapy.payouts FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR recipient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR recipient_id = (SELECT auth.uid())
);

-- ======================== refund_requests ========================
CREATE POLICY "refund_requests_access" ON therapy.refund_requests FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== reviews ========================
CREATE POLICY "reviews_select" ON therapy.reviews FOR SELECT TO authenticated USING (true);
CREATE POLICY "reviews_write" ON therapy.reviews FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "reviews_update" ON therapy.reviews FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "reviews_delete" ON therapy.reviews FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_reviews ========================
CREATE POLICY "clinic_reviews_select" ON therapy.clinic_reviews FOR SELECT TO authenticated USING (true);
CREATE POLICY "clinic_reviews_write" ON therapy.clinic_reviews FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "clinic_reviews_update" ON therapy.clinic_reviews FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "clinic_reviews_delete" ON therapy.clinic_reviews FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== review_responses ========================
CREATE POLICY "review_responses_access" ON therapy.review_responses FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR responder_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR responder_id = (SELECT auth.uid())
);

-- ======================== conversations ========================
CREATE POLICY "conversations_access" ON therapy.conversations FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = conversations.id
          AND cp.participant_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = conversations.id
          AND cp.participant_id = (SELECT auth.uid())
    )
);

-- ======================== messages ========================
CREATE POLICY "messages_access" ON therapy.messages FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = messages.conversation_id
          AND cp.participant_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = messages.conversation_id
          AND cp.participant_id = (SELECT auth.uid())
    )
);

-- ======================== conversation_participants ========================
CREATE POLICY "conversation_participants_access" ON therapy.conversation_participants FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp2
        WHERE cp2.conversation_id = conversation_participants.conversation_id
          AND cp2.participant_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp2
        WHERE cp2.conversation_id = conversation_participants.conversation_id
          AND cp2.participant_id = (SELECT auth.uid())
    )
);

-- ======================== message_reports ========================
CREATE POLICY "message_reports_access" ON therapy.message_reports FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR reported_by_user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR reported_by_user_id = (SELECT auth.uid())
);

-- ======================== user_blocks ========================
CREATE POLICY "user_blocks_access" ON therapy.user_blocks FOR ALL TO authenticated USING (
    blocker_user_id = (SELECT auth.uid())
) WITH CHECK (
    blocker_user_id = (SELECT auth.uid())
);

-- ======================== clinic_settings ========================
CREATE POLICY "clinic_settings_select" ON therapy.clinic_settings FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR clinic_id = (SELECT therapy.current_clinic_id())
);
CREATE POLICY "clinic_settings_write" ON therapy.clinic_settings FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_settings_update" ON therapy.clinic_settings FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_settings_delete" ON therapy.clinic_settings FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_branding ========================
CREATE POLICY "clinic_branding_select" ON therapy.clinic_branding FOR SELECT TO authenticated USING (true);
CREATE POLICY "clinic_branding_write" ON therapy.clinic_branding FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_branding_update" ON therapy.clinic_branding FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_branding_delete" ON therapy.clinic_branding FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_therapist_config ========================
CREATE POLICY "clinic_therapist_config_access" ON therapy.clinic_therapist_config FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== therapist_settings ========================
CREATE POLICY "therapist_settings_access" ON therapy.therapist_settings FOR ALL TO authenticated USING (
    therapist_id = (SELECT auth.uid())
) WITH CHECK (
    therapist_id = (SELECT auth.uid())
);

-- ======================== patient_pricing ========================
CREATE POLICY "patient_pricing_access" ON therapy.patient_pricing FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);

-- ======================== platform_commission_overrides ========================
CREATE POLICY "platform_commission_overrides_access" ON therapy.platform_commission_overrides FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== platform_settings ========================
CREATE POLICY "platform_settings_select" ON therapy.platform_settings FOR SELECT TO authenticated USING (true);
CREATE POLICY "platform_settings_write" ON therapy.platform_settings FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "platform_settings_update" ON therapy.platform_settings FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "platform_settings_delete" ON therapy.platform_settings FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== platform_settings_history ========================
CREATE POLICY "platform_settings_history_select" ON therapy.platform_settings_history FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== action_log ========================
CREATE POLICY "action_log_select" ON therapy.action_log FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
);
CREATE POLICY "action_log_insert" ON therapy.action_log FOR INSERT TO authenticated WITH CHECK (
    user_id = (SELECT auth.uid())
);

-- -----------------------------------------------------------------
-- 6. SEED DATA — Platform Settings
-- -----------------------------------------------------------------

INSERT INTO therapy.platform_settings (key, value) VALUES
    ('app_name', 'Therapy Platform'),
    ('global_commission_rate', '10.00'),
    ('session_pre_access_minutes', '15'),
    ('session_post_access_minutes', '45'),
    ('session_reopen_duration_minutes', '50'),
    ('session_reopen_button_visibility_minutes', '60'),
    ('refund_enabled', 'false'),
    ('refund_window_days', '7'),
    ('cancellation_cutoff_hours', '24'),
    ('withdrawal_min_amount', '10.00'),
    ('withdrawal_fee_pct', '2.00'),
    ('audio_retention_hours', '24'),
    ('longitudinal_min_sessions', '4'),
    ('message_notification_delay_minutes', '5'),
    ('no_show_charge_pct', '50.00'),
    ('ai_prompt_transcription_instructions', 'Transcreva o audio da sessao de terapia em portugues brasileiro. Identifique os falantes como Terapeuta e Paciente.'),
    ('ai_prompt_base_summary', 'Voce e um assistente que resume sessoes de terapia para o paciente. Gere um resumo conciso e factual da sessao baseado apenas na transcricao. Nao inclua interpretacoes clinicas. Use um tom acolhedor e acessivel em portugues brasileiro.'),
    ('ai_prompt_clinical_summary', 'Voce e um assistente clinico para terapeutas. Gere um resumo clinico da sessao baseado na transcricao e nas observacoes do terapeuta. Inclua insights clinicos, padroes observados e pontos de atencao. Use linguagem tecnica apropriada em portugues brasileiro.'),
    ('ai_prompt_longitudinal_clinical', 'Voce e um assistente clinico. Sintetize todos os resumos clinicos e observacoes em uma analise longitudinal abrangente do caso. Identifique temas recorrentes, progresso, topicos nao resolvidos e insights clinicos. Use linguagem tecnica em portugues brasileiro.'),
    ('ai_prompt_longitudinal_patient', 'Voce e um assistente pessoal de jornada terapeutica. Sintetize os resumos das sessoes e as anotacoes pessoais do paciente em uma visao geral da jornada terapeutica. Use a segunda pessoa (voce) e um tom acolhedor e reflexivo. Ajude o paciente a perceber seus padroes e evolucao. Em portugues brasileiro.'),
    ('ai_prompt_tag_generation', 'Gere tags tematicas relevantes para esta sessao de terapia baseado no conteudo. Retorne como uma lista JSON de strings. Maximo 8 tags. Em portugues.')
ON CONFLICT (key) DO NOTHING;

-- -----------------------------------------------------------------
-- 7. PRODUCT SEED
-- -----------------------------------------------------------------

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Plataforma de Terapia',
    'therapy-platform',
    'Plataforma online de terapia: video, agendamento, prontuario digital e gestao financeira',
    '🧠',
    'http://localhost:8095',
    '#8b5cf6',
    true
) ON CONFLICT (slug) DO NOTHING;

-- -----------------------------------------------------------------
-- 8. FINAL GRANTS (ensure all objects have correct permissions)
-- -----------------------------------------------------------------

GRANT ALL ON ALL TABLES IN SCHEMA therapy TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA therapy TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA therapy TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA therapy TO anon, authenticated, service_role;

-- -----------------------------------------------------------------
-- DONE. Therapy platform schema is fully set up.
-- -----------------------------------------------------------------

COMMIT;

-- ────────────────────────────────────────────────────────────────────────────
-- products/youtube-crawler/backend/migrations/001_seed.sql
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

-- ============================================================================
-- YouTube Crawler schema
-- Schema: youtube_crawler
-- Description: Minimal product schema that proves the entire shared stack works.
--
-- Future migrations should use the canonical helpers from
-- `noctusai_lib.domain.sql_templates` (set_search_path, updated_at_function,
-- updated_at_trigger, rls_subquery_policy) so the conventions cannot drift.
-- ============================================================================

SET search_path = youtube_crawler, public;

CREATE SCHEMA IF NOT EXISTS youtube_crawler;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA youtube_crawler TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA youtube_crawler TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA youtube_crawler TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA youtube_crawler GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA youtube_crawler GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE youtube_crawler.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE youtube_crawler.status_pagina ENABLE ROW LEVEL SECURITY;

-- Note: this policy intentionally does NOT use `rls_subquery_policy` — that
-- helper always emits `TO authenticated`, but `todos_veem_producao` is an
-- anonymous-readable policy (anon role too).
CREATE POLICY "todos_veem_producao" ON youtube_crawler.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations
-- ============================================================================

CREATE TABLE youtube_crawler.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE youtube_crawler.invitations ENABLE ROW LEVEL SECURITY;

-- Matches `rls_subquery_policy(youtube_crawler, "invitations", "invitations_select_own_org",
--   "SELECT", using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid")`
-- output (whitespace-normalized). The scaffold's regression test enforces this.
CREATE POLICY "invitations_select_own_org" ON youtube_crawler.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_youtube_crawler_invitations_org ON youtube_crawler.invitations(org_id);
CREATE INDEX idx_youtube_crawler_invitations_token ON youtube_crawler.invitations(token);


-- ============================================================================
-- Seed pages
-- ============================================================================

INSERT INTO youtube_crawler.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

COMMIT;

