-- ============================================================
-- Schema lock — pin name resolution to community, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = community, public;

-- ============================================================================
-- Migration 008 — Module 2: Checkout + Pagamentos + Assinaturas
--
-- Contract: community-m2-contract.md (2026-09-16), INCLUDING the
-- SECURITY AMENDMENTS + PRODUCT DECISIONS sections, which override the
-- base spec. Depends on migration 007 (drops the anon write policies
-- migration 006 shipped) — see amendment A6.
--
-- Reuses `noctusai_lib.integrations.payments` / `.checkout` /
-- `.webhook_events` (gateway I/O) and `noctusai_lib.domain.payments`
-- (subscription state machine + EventInbox idempotency). No new gateway
-- adapter — see the contract's "Reuse — do NOT rebuild" section.
--
-- `updated_at` auto-touch follows the platform convention, reusing the
-- SAME `community.set_updated_at()` function migration 006 defined
-- (idempotent CREATE OR REPLACE there; not redefined here).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- plano_gateway_refs — maps a manager-made tier to each gateway's own object
-- ----------------------------------------------------------------------------

CREATE TABLE community.plano_gateway_refs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    plano_id UUID NOT NULL REFERENCES community.planos(id) ON DELETE CASCADE,
    gateway TEXT NOT NULL CHECK (gateway IN ('stripe', 'asaas')),
    ref_externo TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT plano_gateway_refs_plano_gateway_unique UNIQUE (plano_id, gateway)
);

ALTER TABLE community.plano_gateway_refs ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_plano_gateway_refs
    BEFORE UPDATE ON community.plano_gateway_refs
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "plano_gateway_refs_select_own_org" ON community.plano_gateway_refs
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "plano_gateway_refs_insert_own_org" ON community.plano_gateway_refs
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "plano_gateway_refs_update_own_org" ON community.plano_gateway_refs
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "plano_gateway_refs_delete_own_org" ON community.plano_gateway_refs
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- No anon policy, no anon grant (see the schema-wide REVOKE at the
-- bottom of this file — amendment A7).

-- ----------------------------------------------------------------------------
-- assinaturas
-- ----------------------------------------------------------------------------

CREATE TABLE community.assinaturas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    membro_id UUID NOT NULL REFERENCES community.membros(id) ON DELETE CASCADE,
    plano_id UUID NOT NULL REFERENCES community.planos(id),
    gateway TEXT NOT NULL CHECK (gateway IN ('stripe', 'asaas')),
    assinatura_externa_id TEXT NULL,
    cliente_externo_id TEXT NULL,
    estado TEXT NOT NULL
        CHECK (estado IN ('iniciada', 'ativa', 'inadimplente', 'pausada', 'cancelada')),
    metodo TEXT NOT NULL CHECK (metodo IN ('cartao', 'pix', 'boleto')),
    ciclo TEXT NOT NULL CHECK (ciclo IN ('mensal', 'anual')),
    iniciada_em TIMESTAMPTZ,
    ativa_em TIMESTAMPTZ,
    cancelada_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Amendment A13: a PARTIAL unique index (not a plain column UNIQUE
-- constraint) — `assinatura_externa_id` is NULL for a freshly-created
-- Stripe hosted-checkout session (the Subscription resource doesn't
-- exist yet) and a bare UNIQUE constraint treats every NULL as
-- non-equal to every other NULL in standard SQL semantics ANYWAY, so
-- this is belt-and-suspenders explicitness matching the contract's
-- literal instruction, not a behavior change from a column constraint.
CREATE UNIQUE INDEX assinaturas_gateway_externa_unique
    ON community.assinaturas (gateway, assinatura_externa_id)
    WHERE assinatura_externa_id IS NOT NULL;

CREATE INDEX idx_community_assinaturas_org_membro ON community.assinaturas(org_id, membro_id);
CREATE INDEX idx_community_assinaturas_org_estado ON community.assinaturas(org_id, estado);

ALTER TABLE community.assinaturas ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_assinaturas
    BEFORE UPDATE ON community.assinaturas
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "assinaturas_select_own_org" ON community.assinaturas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "assinaturas_insert_own_org" ON community.assinaturas
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "assinaturas_update_own_org" ON community.assinaturas
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "assinaturas_delete_own_org" ON community.assinaturas
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- No anon policy, no anon grant. Both the public `POST /api/checkout`
-- write and the webhook handlers' writes go through the SERVICE-ROLE
-- client (bypasses RLS entirely, same convention as
-- `resolve_public_org_id()` / `PublicAplicacoesService` in module 1) —
-- never through an anon-scoped RLS policy.

-- ----------------------------------------------------------------------------
-- pagamentos
-- ----------------------------------------------------------------------------

CREATE TABLE community.pagamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    assinatura_id UUID NULL REFERENCES community.assinaturas(id) ON DELETE SET NULL,
    membro_id UUID NOT NULL REFERENCES community.membros(id) ON DELETE CASCADE,
    gateway TEXT NOT NULL,
    cobranca_externa_id TEXT NOT NULL,
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos >= 0),
    metodo TEXT NOT NULL CHECK (metodo IN ('cartao', 'pix', 'boleto')),
    estado TEXT NOT NULL CHECK (estado IN ('pendente', 'pago', 'falhou', 'estornado')),
    pago_em TIMESTAMPTZ NULL,
    vencimento TIMESTAMPTZ NULL,
    url_fatura TEXT NULL,
    pix_payload TEXT NULL,
    pix_imagem_base64 TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pagamentos_gateway_cobranca_unique UNIQUE (gateway, cobranca_externa_id)
);

CREATE INDEX idx_community_pagamentos_org_membro ON community.pagamentos(org_id, membro_id);
CREATE INDEX idx_community_pagamentos_org_assinatura ON community.pagamentos(org_id, assinatura_id);

ALTER TABLE community.pagamentos ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_pagamentos
    BEFORE UPDATE ON community.pagamentos
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "pagamentos_select_own_org" ON community.pagamentos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "pagamentos_insert_own_org" ON community.pagamentos
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "pagamentos_update_own_org" ON community.pagamentos
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "pagamentos_delete_own_org" ON community.pagamentos
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- No anon policy, no anon grant. `pagamentos` carries `pix_payload` /
-- `pix_imagem_base64` / `url_fatura` — exactly the fields amendment A7's
-- threat model names.

-- ----------------------------------------------------------------------------
-- webhook_eventos — the EventInbox table (amendment A12)
--
-- Shape matches `noctusai_lib.domain.payments.event_inbox.
-- RealSupabaseEventInbox`'s documented expectation EXACTLY (see that
-- module's docstring) — consumed via
-- `make_event_inbox(schema_name="community", table_name="webhook_eventos")`,
-- NOT the seed's own default `table_name="payment_gateway_events"`.
--
-- No `org_id` column: an inbox row identifies a webhook DELIVERY
-- (gateway, event_id), not an org-scoped business record, so an
-- org-scoped policy is structurally impossible here. RLS is enabled
-- with ZERO policies — deny-by-default for every role except
-- `service_role` (which bypasses RLS unconditionally); both webhook
-- routes already use the service-role client, matching A12's
-- "service-role-only writer" requirement without any extra grant.
--
-- Retention (amendment A11): 90 days. No cleanup job ships in this
-- migration — see the NOC-REMEDIATE marker below.
-- ----------------------------------------------------------------------------

CREATE TABLE community.webhook_eventos (
    gateway TEXT NOT NULL,
    event_id TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (gateway, event_id)
);

ALTER TABLE community.webhook_eventos ENABLE ROW LEVEL SECURITY;
-- Deliberately NO CREATE POLICY statement here — zero policies + RLS
-- enabled means every non-service-role caller gets zero rows and every
-- write is rejected. See the module docstring above.

-- NOC-REMEDIATE[webhook-inbox-retention]: no scheduled job yet purges
-- `community.webhook_eventos` rows older than 90 days (amendment A11).
-- This product has no existing cron/scheduler wiring to hang a cleanup
-- job off; batch with the next scheduler-enabled slice. — 2026-09-16

-- ============================================================================
-- Amendment A7 — least-privilege grants, and prove RLS is on.
--
-- Migration 001 (seed skeleton, see `001_community.sql`) ran:
--   GRANT ALL ON ALL TABLES IN SCHEMA community TO anon, authenticated, service_role;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA community GRANT ALL ON TABLES TO anon, ...;
-- — a blanket grant that means EVERY new table in this schema
-- (including the four above) inherits full anon privileges automatically,
-- regardless of whether any policy actually grants anon access. "No anon
-- policy" then protects a table only for as long as RLS stays enabled on
-- it — one forgotten `ENABLE ROW LEVEL SECURITY` is instant anonymous
-- read/write via `/rest/v1`. Two independent defenses:
--
-- (a) Revoke the blanket anon grant SCHEMA-WIDE — covers every table
--     migrations 006/007/008 created AND every future one, closing the
--     "one forgotten table" gap at the grant level, not per-table.
--     Nothing needs to be re-granted to anon: both this product's
--     public routes (`GET/POST /api/aplicacoes/*`, `POST /api/checkout`,
--     `POST /api/webhooks/*`) already go through the SERVICE-ROLE client
--     (`get_admin_client()`), which bypasses grants and RLS entirely —
--     migration 007's own comment already established this for
--     `aplicacoes`; there has never been an anon PostgREST consumer in
--     this product.
-- (b) Assert, per table this migration creates, that
--     `pg_class.relrowsecurity` is true — failing the migration
--     (RAISE EXCEPTION, not a warning) if RLS is somehow not active,
--     so a future refactor that drops an `ENABLE ROW LEVEL SECURITY`
--     line is caught at migration time, not discovered via an
--     anonymous read in production.
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA community FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA community REVOKE ALL ON TABLES FROM anon;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'plano_gateway_refs', 'assinaturas', 'pagamentos', 'webhook_eventos'
    ]
    LOOP
        IF NOT (
            SELECT relrowsecurity FROM pg_class
            WHERE oid = ('community.' || tbl)::regclass
        ) THEN
            RAISE EXCEPTION 'migration 008: RLS is not enabled on community.%', tbl;
        END IF;
    END LOOP;
END $$;
