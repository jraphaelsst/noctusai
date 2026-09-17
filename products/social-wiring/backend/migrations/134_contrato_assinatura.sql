-- ============================================================================
-- Migration 134 · social_wiring: e-signature envelopes for a contract version
--
-- `projects/signature-integration-CONTRACT.md` §2. The contract generator
-- (F5) ships a PDF + `.docx` and stops there — `status` ('enviado_assinatura'
-- / 'assinado') was a free-text dropdown with no behaviour behind it. This
-- migration adds the ONE table an envelope lives in
-- (`atendimento_contrato_assinaturas`) and widens `atendimento_contrato_
-- versoes.origem` so the signed copy that comes back can land as a normal
-- version row (`origem='assinado'`) instead of inventing a second artifact
-- shape for it.
--
-- ONE LIVE ENVELOPE PER CONTRACT
-- --------------------------------
-- A contract can be re-sent after a cancellation, but never has two envelopes
-- "in flight" at once — `atendimento_contrato_assinaturas_viva` is a PARTIAL
-- unique index on `contrato_id` scoped to `status IN ('pendente','parcial')`,
-- so a cancelled/expired envelope frees the contract for a new one without
-- ever risking two live envelopes racing the same version.
--
-- WHY A SECOND UNIQUE INDEX ON (provedor, external_id)
-- --------------------------------------------------------------------------
-- The webhook receiver's ONLY handle on which envelope fired is the
-- provider's own id — `(provedor, external_id)` is exactly what a webhook
-- lookup keys on, and uniqueness here is what makes a duplicate `criar_
-- envelope` response (a retried request against the provider, say) a loud
-- insert failure instead of two rows silently answering to the same
-- provider-side document.
--
-- WHY `atendimento_contrato_versoes.origem` GAINS 'assinado' RATHER THAN A
-- NEW TABLE FOR THE SIGNED COPY
-- --------------------------------------------------------------------------
-- The signed PDF is still just a contract version — same bucket, same
-- LGPD-logged read path (`atendimento_contrato_versao_acessos`), same
-- `numero` sequence every other version in this contract already uses. The
-- ONLY thing distinguishing it is provenance, which `origem` already exists
-- to carry ('upload' | 'gerado'). Migrations 112 and 120 each added a
-- per-origem CHECK that is EXHAUSTIVE over the two origins that existed at
-- the time (`(origem='gerado' AND ...) OR (origem='upload' AND ...)`) — an
-- 'assinado' row would satisfy NEITHER branch and be silently rejected by a
-- constraint this migration never intended to touch. Both are widened here
-- with the same rule an 'upload' row already gets: no context hash, no docx
-- sibling — the signed copy is a downloaded PDF, not a rendering.
--
-- RLS MIRRORS `atendimento_contratos` VERBATIM (106) — READ THE EXISTING
-- POLICY SHAPE, DO NOT INVENT A NEW ONE
-- --------------------------------------------------------------------------
-- `atendimento_contratos` and `atendimento_contrato_versoes` both carry
-- exactly two policies: `..._select_own_org` (SELECT, `authenticated`, scoped
-- by `org_id = public.current_org_id()`) and `..._service_role` (ALL,
-- `service_role`, unconditional). Neither ships an INSERT/UPDATE policy for
-- `authenticated` — every write on those tables already goes through
-- `card_hub.deps.get_card_hub_client()`'s admin (service-role) client, never
-- a user-scoped one. `atendimento_contrato_assinaturas` is written the same
-- way (the router's service layer, admin client) and the webhook receiver is
-- unauthenticated by design (contract §3.4) — it needs the SAME service-role
-- bypass, not a special-cased third policy. So this table gets the identical
-- two-policy shape, no more.
--
-- ADDITIVE ONLY. NO DATA TOUCHED. FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_contrato_assinaturas — one row per e-signature envelope
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_assinaturas (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  contrato_id uuid not null references social_wiring.atendimento_contratos(id),
  versao_id  uuid not null references social_wiring.atendimento_contrato_versoes(id),
  provedor text not null,
  external_id text not null,
  link_assinatura text not null,
  status text not null default 'pendente'
    check (status in ('pendente','parcial','concluido','cancelado','expirado')),
  signatarios jsonb not null default '[]'::jsonb,
  enviado_em timestamptz not null default now(),
  enviado_por uuid,
  concluido_em timestamptz,
  versao_assinada_id uuid references social_wiring.atendimento_contrato_versoes(id),
  cancelado_motivo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_contrato_assinaturas_contrato
  ON social_wiring.atendimento_contrato_assinaturas (org_id, contrato_id, created_at DESC);

-- ONE live envelope per contract; a cancelled/expired one may be superseded.
create unique index if not exists atendimento_contrato_assinaturas_viva
  on social_wiring.atendimento_contrato_assinaturas (contrato_id)
  where status in ('pendente','parcial');
create unique index if not exists atendimento_contrato_assinaturas_externo
  on social_wiring.atendimento_contrato_assinaturas (provedor, external_id);

ALTER TABLE social_wiring.atendimento_contrato_assinaturas ENABLE ROW LEVEL SECURITY;

-- Mirrors `atendimento_contratos_select_own_org` / `..._service_role`
-- (migration 106) verbatim — see this file's header.
DROP POLICY IF EXISTS "atendimento_contrato_assinaturas_select_own_org"
    ON social_wiring.atendimento_contrato_assinaturas;
CREATE POLICY "atendimento_contrato_assinaturas_select_own_org"
    ON social_wiring.atendimento_contrato_assinaturas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_contrato_assinaturas_service_role"
    ON social_wiring.atendimento_contrato_assinaturas;
CREATE POLICY "atendimento_contrato_assinaturas_service_role"
    ON social_wiring.atendimento_contrato_assinaturas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_contrato_versoes.origem gains 'assinado' — the signed copy
--    the webhook stores back is a normal version row, not a new artifact
--    shape (see this file's header).
-- ----------------------------------------------------------------------------
-- 106 declared the CHECK inline, so Postgres named it
-- `<table>_<column>_check`. Drop-then-add is the idempotent CHECK extension.
ALTER TABLE social_wiring.atendimento_contrato_versoes
    DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_origem_check;
ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD CONSTRAINT atendimento_contrato_versoes_origem_check
    CHECK (origem IN ('upload', 'gerado', 'assinado'));

-- 112's per-origem CHECK on `contexto_sha256` was exhaustive over the two
-- origins that existed then; 'assinado' gets the same rule 'upload' has — a
-- downloaded signed PDF has no rendering context to hash.
ALTER TABLE social_wiring.atendimento_contrato_versoes
    DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_contexto_por_origem;
ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD CONSTRAINT atendimento_contrato_versoes_contexto_por_origem
    CHECK (
        (origem = 'gerado' AND contexto_sha256 ~ '^[0-9a-f]{64}$')
        OR (origem = 'upload' AND contexto_sha256 IS NULL)
        OR (origem = 'assinado' AND contexto_sha256 IS NULL)
    );

-- 120's per-origem CHECK on the docx sibling was likewise exhaustive over
-- 'gerado'/'upload'; 'assinado' gets the same rule 'upload' has — no docx
-- sibling, it is a downloaded PDF, not a rendering.
ALTER TABLE social_wiring.atendimento_contrato_versoes
    DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_docx_por_origem;
ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD CONSTRAINT atendimento_contrato_versoes_docx_por_origem
    CHECK (
        (origem = 'gerado' AND docx_storage_path IS NOT NULL AND docx_tamanho_bytes IS NOT NULL)
        OR (origem = 'upload' AND docx_storage_path IS NULL AND docx_tamanho_bytes IS NULL)
        OR (origem = 'assinado' AND docx_storage_path IS NULL AND docx_tamanho_bytes IS NULL)
    ) NOT VALID;
-- No `VALIDATE CONSTRAINT` follows — mirrors 120's own posture: pre-existing
-- 'gerado' rows may predate the docx-sibling feature entirely, and this
-- migration has no reason to force a historical scan of them.

COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.origem IS
    'upload | gerado | assinado. ''assinado'' is the signed copy an '
    'e-signature webhook stores back — see migration 134 header.';

NOTIFY pgrst, 'reload schema';
