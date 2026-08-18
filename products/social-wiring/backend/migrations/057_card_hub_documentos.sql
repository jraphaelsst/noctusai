-- ============================================================================
-- Migration 057 -- social_wiring: card documents, LGPD-complete (lead-card-hub
-- Phase 2, contract §2 "057 -- documents, LGPD-complete", ruling S2 / D5).
--
-- Object RLS + per-type retention + delete-on-request + access log land in
-- THIS migration, not a follow-up -- ruling S2 is explicit: "no attachments
-- now, governance later".
--
-- WHAT THIS FILE ADDS BEYOND THE CONTRACT'S LITERAL TWO TABLES
-- --------------------------------------------------------------
-- The contract asks for retention to be "derived from `tipo_documento` by a
-- table-driven policy, not by a hardcoded `if`" but doesn't name the table.
-- `cliente_documento_tipos` is that table -- a small, org-independent
-- taxonomy (document type -> LGPD category -> retention window -> whether
-- upload is currently enabled). It is genuinely table-driven: enabling the
-- withheld RG/CPF-class types after the data-category intake is filed
-- becomes a data change (`ativo = true`), never a code deploy. It has no
-- `org_id` -- unlike every other table in this migration, this one is a
-- platform-wide taxonomy shared by every org, not per-tenant data -- flagged
-- explicitly here rather than silently deviating from the "every table gets
-- org_id" convention the rest of this file follows.
--
-- 🔴 THE CONSERVATIVE DEFAULT LIST (contract §2, final paragraph)
-- ------------------------------------------------------------------
-- RG/CPF-bearing types are seeded with `ativo = false` -- the upload
-- endpoint refuses any `tipo_documento` that isn't `ativo`. This migration
-- does NOT enable them; that is a deliberate, data-only follow-up gated on
-- the `noctus.dev.lgpd_flag` intake this slice files (see the delivery
-- note for the notification string).
--
-- STORAGE: bucket `social-wiring-documentos` (private, `public = false`).
-- Path shape `{org_id}/clientes/{cliente_id}/{document_id}` -- object RLS
-- below scopes on the FIRST path segment via `storage.foldername(name)`,
-- mirroring `erp-imobiliario`'s `011_storage_buckets.sql` /
-- `035_rls_storage_current_org_id.sql`, using `public.current_org_id()`
-- directly (that function already exists in this project -- 011 -- so the
-- erp migration's `SELECT org_id FROM noctus_users` subquery workaround,
-- itself only needed because it predated a trusted helper, is unnecessary
-- here).
--
-- ✅ APPLIED to the live Supabase project 2026-08-18 (user green-lit), after a
-- BEGIN…probe…ROLLBACK dry run against the live schema. Verified post-apply.
-- Applied state is recorded in `products/social-wiring/backend/migrations/APPLIED.md`
-- — do NOT trust this header alone; see that file for why it exists.
--
-- FORWARD-ONLY, IDEMPOTENT. (Historical note, now superseded by the stamp
-- above: MIGRATION FILE ONLY -- not applied to any
-- database by this change. Apply via `noctus.dev.migrate_product` only
-- after the tech-lead has an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. cliente_documento_tipos -- the table-driven retention/allow-list policy
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cliente_documento_tipos (
    tipo_documento  TEXT PRIMARY KEY,
    categoria_lgpd  TEXT NOT NULL,
    -- NULL = no automatic-expiry policy defined for this type yet (the
    -- sweep skips it, rather than treating NULL as "expire immediately").
    retencao_dias   INTEGER,
    -- RG/CPF-class (or equivalent government identity documents). Every
    -- row seeded below with `identidade = true` also ships `ativo = false`
    -- -- see the header.
    identidade      BOOLEAN NOT NULL DEFAULT false,
    -- Whether upload is currently allowed for this type. The upload
    -- endpoint's allow-list check is `ativo = true`, full stop -- no
    -- separate hardcoded list in application code.
    ativo           BOOLEAN NOT NULL DEFAULT true,
    descricao       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.cliente_documento_tipos ENABLE ROW LEVEL SECURITY;

-- No `org_id` column (see header) -- readable by every authenticated user,
-- platform-wide, same as reading an enum.
DROP POLICY IF EXISTS "cliente_documento_tipos_select_authenticated" ON social_wiring.cliente_documento_tipos;
CREATE POLICY "cliente_documento_tipos_select_authenticated" ON social_wiring.cliente_documento_tipos
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cliente_documento_tipos_service_role" ON social_wiring.cliente_documento_tipos;
CREATE POLICY "cliente_documento_tipos_service_role" ON social_wiring.cliente_documento_tipos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Conservative default catalogue (contract §2, final paragraph). RG/CPF
-- and other identity documents are DELIBERATELY seeded `ativo = false`.
-- `ON CONFLICT DO NOTHING` -- re-running this migration never resets a
-- type a human has since enabled/disabled by hand.
INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('contrato',            'contratual',        1825, false, true,  'Contratos e aditivos'),
    ('proposta',             'contratual',        1095, false, true,  'Propostas comerciais'),
    ('comprovante_pagamento','financeiro',        1825, false, true,  'Comprovantes de pagamento'),
    ('comprovante_endereco', 'cadastral',          730, false, true,  'Comprovante de endereço'),
    ('planta_imovel',        'operacional',       NULL, false, true,  'Plantas e croquis do imóvel'),
    ('foto_imovel',          'operacional',       NULL, false, true,  'Fotos do imóvel'),
    ('outro',                'nao_classificado',   365, false, true,  'Outro documento não classificado'),
    -- Withheld until the LGPD data-category intake (noctus.dev.lgpd_flag)
    -- is filed and a human flips `ativo = true` -- see header.
    ('rg',                   'identidade',        1825, true,  false, 'RG -- retenção pendente de intake LGPD'),
    ('cpf',                  'identidade',        1825, true,  false, 'CPF -- retenção pendente de intake LGPD')
ON CONFLICT (tipo_documento) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. cliente_documentos
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cliente_documentos (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    cliente_id             UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    storage_path           TEXT NOT NULL,
    nome_original          TEXT NOT NULL,
    mime_type              TEXT NOT NULL,
    tamanho_bytes          BIGINT NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_documento         TEXT NOT NULL REFERENCES social_wiring.cliente_documento_tipos(tipo_documento),
    categoria_lgpd         TEXT NOT NULL,
    retencao_ate           DATE,
    enviado_por            UUID,
    deleted_at             TIMESTAMPTZ,
    delete_motivo          TEXT,
    delete_solicitado_por  UUID,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_cliente
    ON social_wiring.cliente_documentos (cliente_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_org
    ON social_wiring.cliente_documentos (org_id);
-- The retention sweep's read path: every non-deleted document past its
-- retention date.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_retencao
    ON social_wiring.cliente_documentos (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;

ALTER TABLE social_wiring.cliente_documentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_documentos_select_own_org" ON social_wiring.cliente_documentos;
CREATE POLICY "cliente_documentos_select_own_org" ON social_wiring.cliente_documentos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_documentos_service_role" ON social_wiring.cliente_documentos;
CREATE POLICY "cliente_documentos_service_role" ON social_wiring.cliente_documentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. cliente_documento_acessos -- the access log, append-only
-- ----------------------------------------------------------------------------
-- Every view/download/delete appends here (application-level contract --
-- see `app/modules/card_hub/services_documentos.py`). No UPDATE/DELETE
-- policy is granted to ANY role but `service_role` -- an access log a
-- normal role can edit is not an access log. `authenticated` gets SELECT
-- only; this schema's backend always writes through the service-role admin
-- client (same shape as every other table above), so no `authenticated`
-- INSERT policy is needed for the live path, and its absence is exactly
-- what makes "append-only for everyone but service_role" literally true
-- rather than aspirational.
CREATE TABLE IF NOT EXISTS social_wiring.cliente_documento_acessos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    documento_id  UUID NOT NULL REFERENCES social_wiring.cliente_documentos(id) ON DELETE CASCADE,
    usuario_id    UUID,
    acao          TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_documento_acessos_documento
    ON social_wiring.cliente_documento_acessos (documento_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documento_acessos_org
    ON social_wiring.cliente_documento_acessos (org_id);

ALTER TABLE social_wiring.cliente_documento_acessos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_documento_acessos_select_own_org" ON social_wiring.cliente_documento_acessos;
CREATE POLICY "cliente_documento_acessos_select_own_org" ON social_wiring.cliente_documento_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_documento_acessos_service_role" ON social_wiring.cliente_documento_acessos;
CREATE POLICY "cliente_documento_acessos_service_role" ON social_wiring.cliente_documento_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. Storage bucket + object-level RLS
-- ----------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('social-wiring-documentos', 'social-wiring-documentos', false)
ON CONFLICT (id) DO NOTHING;

-- Path shape `{org_id}/clientes/{cliente_id}/{document_id}` -- the first
-- path segment is the org id, matching `erp-imobiliario`'s
-- `(storage.foldername(name))[1]` convention. Not merely a hard-to-guess
-- path (contract §2): this is a genuine RLS predicate, evaluated by
-- Postgres on every access, not an obscurity property of the path string.
DROP POLICY IF EXISTS "sw_documentos_storage_select" ON storage.objects;
CREATE POLICY "sw_documentos_storage_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'social-wiring-documentos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_documentos_storage_insert" ON storage.objects;
CREATE POLICY "sw_documentos_storage_insert" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'social-wiring-documentos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_documentos_storage_update" ON storage.objects;
CREATE POLICY "sw_documentos_storage_update" ON storage.objects
    FOR UPDATE TO authenticated
    USING (
        bucket_id = 'social-wiring-documentos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_documentos_storage_delete" ON storage.objects;
CREATE POLICY "sw_documentos_storage_delete" ON storage.objects
    FOR DELETE TO authenticated
    USING (
        bucket_id = 'social-wiring-documentos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_documentos_storage_service" ON storage.objects;
CREATE POLICY "sw_documentos_storage_service" ON storage.objects
    FOR ALL TO service_role
    USING (bucket_id = 'social-wiring-documentos')
    WITH CHECK (bucket_id = 'social-wiring-documentos');
