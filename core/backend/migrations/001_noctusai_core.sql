-- ============================================================
-- NoctusAI Core — Database Schema
-- Run this in the Supabase SQL Editor
-- ============================================================

-------------------------------------------------
-- 1. ORGANIZATIONS (tenants)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS organizations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    plano TEXT NOT NULL DEFAULT 'free',        -- free | starter | pro | enterprise
    owner_id UUID,                              -- Supabase auth user who created it
    logo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_organizations_slug ON organizations(slug);

-------------------------------------------------
-- 2. NOCTUS USERS (platform-level profiles)
-------------------------------------------------
CREATE TABLE IF NOT EXISTS noctus_users (
    id UUID PRIMARY KEY,                        -- matches Supabase auth.users.id
    email TEXT NOT NULL,
    nome TEXT NOT NULL,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'user',           -- admin | manager | user
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_noctus_users_org ON noctus_users(org_id);
CREATE INDEX idx_noctus_users_email ON noctus_users(email);

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

CREATE INDEX idx_products_slug ON products(slug);

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
    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(org_id, product_id)
);

CREATE INDEX idx_licenses_org ON licenses(org_id);
CREATE INDEX idx_licenses_product ON licenses(product_id);

-------------------------------------------------
-- 5. RLS Policies
-------------------------------------------------

-- Enable RLS on all tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE noctus_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE licenses ENABLE ROW LEVEL SECURITY;

-- Products are readable by all authenticated users
CREATE POLICY "products_read_all" ON products
    FOR SELECT TO authenticated
    USING (true);

-- Users can read their own org
CREATE POLICY "org_read_own" ON organizations
    FOR SELECT TO authenticated
    USING (id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));

-- Users can read their own profile
CREATE POLICY "users_read_own" ON noctus_users
    FOR SELECT TO authenticated
    USING (id = auth.uid() OR org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));

-- Users can read licenses for their org
CREATE POLICY "licenses_read_own_org" ON licenses
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT org_id FROM noctus_users WHERE id = auth.uid()));

-- Service role bypasses all policies (used by backend)
-- (This is automatic in Supabase for service_role key)

-------------------------------------------------
-- 6. Seed: ERP Imobiliário product
-------------------------------------------------
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
