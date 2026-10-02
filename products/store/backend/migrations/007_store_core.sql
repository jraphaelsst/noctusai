-- Migration: store_core — store v1 data model (contract §1).
-- Tables: landing_settings (versioned ledger), pedidos, webhook_eventos.
-- Every table: RLS ON + `service_role_bypass` ONLY. The product's backend
-- reads/writes through the admin (service-role) client exclusively; no
-- browser role (anon / authenticated) ever touches these tables directly,
-- so they get NO policy and NO grant.
-- Forward-only + idempotent. NOT applied by this file's author — the
-- tech-lead applies via noctus.dev.migrate_product.

SET search_path = store, public;

-- ---------------------------------------------------------------------------
-- 0. Drop the scaffold's `example` skeleton table (replaced by the real model).
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS store.examples;

-- ---------------------------------------------------------------------------
-- 1. updated_at helper (once per schema)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION store.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = store, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- ---------------------------------------------------------------------------
-- 2. landing_settings — append-only versioned ledger (shape of core
--    052_website.sql `website_settings`). Current = max(version). A write is
--    an INSERT of version+1; the PK makes two concurrent writers collide
--    (23505 -> 409) instead of silently overwriting each other.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS store.landing_settings (
    version     INTEGER PRIMARY KEY CHECK (version >= 1),
    data        JSONB NOT NULL,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE store.landing_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON store.landing_settings;
CREATE POLICY "service_role_bypass" ON store.landing_settings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Version 1 = DEFAULT_SETTINGS (app/services/settings_service.py). The two
-- are kept identical by tests/services/test_settings_service.py, which
-- parses THIS literal and compares it to the Python defaults.
INSERT INTO store.landing_settings (version, data, created_by)
VALUES (
    1,
    $json${
  "product_name": "Contrato Blindado de Compra e Venda",
  "price_cents": 4700,
  "items": [
    {"label": "Contrato À Vista (Word + PDF)", "anchor_cents": 9700},
    {"label": "Contrato Financiado (Word + PDF)", "anchor_cents": 9700},
    {"label": "Contrato Parcelado com confissão de dívida", "anchor_cents": 12700},
    {"label": "Lista de 14 certidões e documentos", "anchor_cents": 4700}
  ],
  "guarantee_days": 7,
  "author": {
    "name": "Gilson",
    "role": "corretor de imóveis",
    "bio": "O Gilson acompanha negociações de compra e venda do sinal à entrega das chaves. Este modelo nasceu dos contratos assinados nessas negociações, reunidos em um só texto e transformados em um modelo genérico que qualquer pessoa pode preencher.",
    "has_photo": false
  },
  "checkout_enabled": true
}$json$::jsonb,
    NULL
)
ON CONFLICT (version) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. pedidos — one row per checkout attempt. `token` is the buyer's only
--    handle (32-byte urlsafe); `cpf` is digits only.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS store.pedidos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token               TEXT NOT NULL UNIQUE,
    nome                TEXT NOT NULL,
    email               TEXT NOT NULL,
    cpf                 TEXT NOT NULL,
    valor_cents         INTEGER NOT NULL CHECK (valor_cents > 0),
    produto             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'pago', 'reembolsado', 'falhou')),
    gateway             TEXT,
    gateway_charge_id   TEXT,
    checkout_url        TEXT,
    pago_em             TIMESTAMPTZ,
    email_enviado_em    TIMESTAMPTZ,
    email_erro          TEXT,
    downloads           INTEGER NOT NULL DEFAULT 0 CHECK (downloads >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE store.pedidos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON store.pedidos;
CREATE POLICY "service_role_bypass" ON store.pedidos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_store_pedidos_status_created
    ON store.pedidos (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_store_pedidos_created
    ON store.pedidos (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_store_pedidos_gateway_charge
    ON store.pedidos (gateway_charge_id) WHERE gateway_charge_id IS NOT NULL;

CREATE OR REPLACE TRIGGER set_updated_at_pedidos
    BEFORE UPDATE ON store.pedidos
    FOR EACH ROW EXECUTE FUNCTION store.set_updated_at();

-- ---------------------------------------------------------------------------
-- 4. webhook_eventos — the seed event-inbox table
--    (noctusai_lib.domain.payments.make_event_inbox). The PK IS the
--    idempotency guarantee: a replayed delivery violates it and is dropped.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS store.webhook_eventos (
    gateway     TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (gateway, event_id)
);

ALTER TABLE store.webhook_eventos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON store.webhook_eventos;
CREATE POLICY "service_role_bypass" ON store.webhook_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 5. No browser-role grants. 001's default privileges hand `authenticated`
--    table DML on every future table; with RLS on and no policy that is a
--    deny, but the grant itself is revoked so the intent is explicit and
--    survives a later policy slip. `anon` never had one.
-- ---------------------------------------------------------------------------
REVOKE ALL ON store.landing_settings, store.pedidos, store.webhook_eventos FROM anon, authenticated;
GRANT ALL ON store.landing_settings, store.pedidos, store.webhook_eventos TO service_role;

-- ---------------------------------------------------------------------------
-- 6. Page-status rows (feature flags). `nome_pagina` is the NAV ROUTE KEY the
--    frontend joins on (`admin`, `vendas`), not the URL path. The scaffold's
--    `dashboard` / `equipe` pages do not exist in this product any more.
-- ---------------------------------------------------------------------------
DELETE FROM store.status_pagina WHERE nome_pagina IN ('dashboard', 'equipe');

INSERT INTO store.status_pagina (nome_pagina, status, descricao) VALUES
    ('admin',  'producao', 'Página de vendas (editor da landing)'),
    ('vendas', 'producao', 'Vendas (pedidos)')
ON CONFLICT (nome_pagina) DO NOTHING;
