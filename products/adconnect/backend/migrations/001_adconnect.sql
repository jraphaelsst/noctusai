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
