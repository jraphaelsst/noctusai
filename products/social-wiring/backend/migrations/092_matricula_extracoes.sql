-- 092_matricula_extracoes.sql — Extrator de Matrículas, ported from erp.
--
-- Renumbered 090 -> 092 before apply: a parallel branch landed
-- `090_um_card_por_lead.sql` and that one is ALREADY APPLIED in production,
-- so it owns 090. This file had not been applied anywhere, which is what
-- makes renumbering it (rather than it) the safe half of the collision.
--
-- WHY THIS EXISTS
-- ---------------
-- `erp-imobiliario` is being retired and its matrícula text-extraction
-- workflow moves here whole. This is the schema half: one table holding one
-- row per uploaded PDF, its status lifecycle, and the transcribed text.
--
-- 🔴 NOT the same table as `imovel_documentos` (075/079). That one stores a
-- document ATTACHED TO AN IMÓVEL and has structured fields read off it
-- (`imovel_hub.matricula_extracao_service`). This one is an upload history
-- for raw full-text transcription of an arbitrary PDF, attached to nothing.
-- Same domain word, different workflow — see
-- `app/modules/matriculas/__init__.py`.
--
-- 🔴 THE ORG HARDENING IS ADOPTED FROM THE START, not after the incident.
-- ERP shipped this table in its 009 sourcing `org_id` from the app (which
-- read it off the JWT `user_metadata`), while RLS derived the org from the
-- DB. The two drift trivially: a freshly-provisioned user has the org in
-- `public.noctus_users` but NOT yet in their JWT, so the app omitted the
-- NOT NULL column and the upload 500'd. ERP's 038 fixed it nine migrations
-- later by defaulting the column from the DB. That default is here in the
-- FIRST migration instead: `org_id DEFAULT public.current_org_id()`, the
-- same trusted source RLS reads. The application never names the org on a
-- write, so it can never name the wrong one.
--
-- NOT ported from ERP 038: `public.is_platform_admin()` and the cross-org
-- bypass policy it powers. That is a platform-wide primitive this schema
-- does not have and this port has no need for; adding it here would be a
-- security-surface decision smuggled in as a table migration.
--
-- RLS shape: the org-scoped-SELECT + org-scoped-write pair
-- `social_wiring.notification_recipients` (001) uses, plus a service_role
-- policy for the recovery sweep (`app/modules/matriculas/
-- extracao_scheduler.py`), which runs detached with no user session.
--
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE
-- / DROP POLICY IF EXISTS + CREATE POLICY / ON CONFLICT DO NOTHING).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ── updated_at trigger function ───────────────────────────────────────────
-- Named for nothing in particular ON PURPOSE. This schema already carries
-- THREE identical bodies under area names — `set_updated_at_scheduling`,
-- `set_updated_at_media_creation`, `touch_imoveis_updated_at` — each
-- `NEW.updated_at = now()`. Adding a fourth area-named copy is the shape
-- the DRY rule forbids at N=3, so this migration adds the ONE canonical
-- name instead and uses it. The three existing copies are NOT migrated onto
-- it here (their tables belong to other slices); that is filed as a
-- scoped-improvement, not done silently as a drive-by.
CREATE OR REPLACE FUNCTION social_wiring.set_updated_at()
  RETURNS trigger
  LANGUAGE plpgsql
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;


-- ── The table ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.matricula_extracoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- DEFAULT from the DB-derived org, never from the app. See the header.
    org_id         UUID NOT NULL DEFAULT public.current_org_id(),
    user_id        UUID NOT NULL,
    nome_arquivo   TEXT NOT NULL,
    tamanho_bytes  INTEGER,
    num_paginas    INTEGER,
    texto_extraido TEXT,
    status         TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    erro_mensagem  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent for a re-application onto a table created by an earlier run of
-- this same file (CREATE TABLE IF NOT EXISTS would skip the DEFAULT above).
ALTER TABLE social_wiring.matricula_extracoes
  ALTER COLUMN org_id SET DEFAULT public.current_org_id();

ALTER TABLE social_wiring.matricula_extracoes ENABLE ROW LEVEL SECURITY;


-- ── RLS ───────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "matricula_extracoes_select_own_org"
    ON social_wiring.matricula_extracoes;
CREATE POLICY "matricula_extracoes_select_own_org"
    ON social_wiring.matricula_extracoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

-- The request path (upload / delete) writes through the CALLER's token, so
-- RLS — not application code — is what decides which org a row lands in and
-- which rows a delete can reach. WITH CHECK is what makes the column
-- DEFAULT above defence-in-depth rather than the only lock.
DROP POLICY IF EXISTS "matricula_extracoes_write_own_org"
    ON social_wiring.matricula_extracoes;
CREATE POLICY "matricula_extracoes_write_own_org"
    ON social_wiring.matricula_extracoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

-- The background extraction and the hourly recovery sweep both run detached
-- from any user session, so they have no `auth.uid()` and cannot satisfy the
-- policy above. Every write they make carries an explicit `org_id`
-- predicate in application code — see `app/modules/matriculas/service.py`.
DROP POLICY IF EXISTS "matricula_extracoes_service_role"
    ON social_wiring.matricula_extracoes;
CREATE POLICY "matricula_extracoes_service_role"
    ON social_wiring.matricula_extracoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Indexes — driven by the actual filter surface ─────────────────────────
-- The history list is org-scoped and ordered by `created_at DESC`; the
-- composite serves both halves of that single query.
CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_org_created
    ON social_wiring.matricula_extracoes(org_id, created_at DESC);
-- The recovery sweep reads non-terminal rows by `updated_at`. Partial, so it
-- indexes only the handful of rows that are ever in flight rather than the
-- whole history.
CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_stale
    ON social_wiring.matricula_extracoes(updated_at)
    WHERE status IN ('pendente', 'processando');


-- ── updated_at ────────────────────────────────────────────────────────────
-- `updated_at` is not cosmetic here: it is what the recovery sweep reads to
-- decide a row has been stuck in `processando` past STALE_APOS. Without this
-- trigger the sweep would compare against a timestamp that never moves and
-- would sweep rows that are actively being worked on.
CREATE OR REPLACE TRIGGER set_updated_at_matricula_extracoes
    BEFORE UPDATE ON social_wiring.matricula_extracoes
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at();


-- ── Sidebar visibility ────────────────────────────────────────────────────
-- 'producao', NOT 'desenvolvimento'. 036 documents the 12-day live defect
-- this decision turns on: `status_pagina`'s original single policy was
-- `USING (status = 'producao')`, so a 'desenvolvimento' row was returned to
-- NOBODY and the FE's own dev/owner branch was dead code. 036 added an
-- additive policy so dev/owner/admin CAN see such rows — but the end user
-- this page ships for is not necessarily any of those, and for her a
-- 'desenvolvimento' row is still an invisible sidebar entry.
--
-- 🔴 `nome_pagina` must stay exactly 'matriculas' — it is matched against
-- the `route: "matriculas"` key in App.tsx's NAV_GROUPS. A mismatch is the
-- same silent failure in a different place: the page and its route work if
-- you type the URL, and the sidebar link never appears.
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('matriculas', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
