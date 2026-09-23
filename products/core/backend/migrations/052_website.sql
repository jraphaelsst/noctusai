-- ============================================================================
-- 052_website — noctusai.com public website: settings, leads, activities,
-- first-party analytics events
-- ============================================================================
--
-- Source: `products/core/frontend/src/website/docs/15-api-contract.md`
-- (§1 · Database), authored by the tech-lead before dispatch
-- (skill `noc-contract-first`). Every shape below is verbatim from that
-- contract — do not rename a column without bumping the contract doc.
--
-- SCHEMA: `public` (core's schema — see `app/main.py`'s
-- `create_product_app(schema="public", ...)`), so no `SET search_path`
-- prelude is needed (matches every other core migration, e.g. 030/031).
--
-- RLS: all four tables ship `ENABLE ROW LEVEL SECURITY` with **no**
-- anon/authenticated policies — access is backend-only via the
-- service-role client (`get_admin_client()`), which bypasses RLS at the
-- connection level. Per `KB § PATTERNS/backend/database-rls.md`, every
-- table also gets an EXPLICIT, literally-named `service_role_bypass`
-- policy (the platform convention the keeper detector
-- `check_admin_endpoint_service_role_bypass` looks for) — this does NOT
-- open anon/authenticated access; the policy is `TO service_role` only.
--
-- ROLE: `noctus_users.role` is free TEXT (no CHECK constraint exists in
-- `001_noctusai_core.sql` to extend — verified before writing this
-- migration). `'marketing'` is simply a new value application code
-- assigns; no DDL change needed for the column itself.
--
-- `public.is_website_editor(uid)` — SECURITY DEFINER helper (admin OR
-- marketing), mirrors the `SET search_path = public` convention used by
-- every other SECURITY DEFINER helper in this schema (RLS
-- self-reference-recursion pattern, `KB § PATTERNS/backend/database-rls.md`
-- § RLS self-reference recursion) even though nothing here currently
-- calls it from inside an RLS policy — a future policy that does will
-- not need a second helper written.
--
-- IDEMPOTENT: every statement is `IF NOT EXISTS` / `CREATE OR REPLACE` /
-- `DROP POLICY IF EXISTS` + re-create.
--
-- NOT applied by this branch — the tech-lead applies it at deploy via
-- `noctus.dev.migrate_product(product="core", confirm=True)`.
-- ============================================================================

-- ─── website_settings ───────────────────────────────────────────────────
-- Append-only version ledger. `current` = the row with `max(version)`.
-- Version 0 (no rows yet) is NOT stored here — the service reads
-- `SERVE_SPA_DIR/_site/settings.defaults.json` (the FE build's
-- `src/website/content/defaults.ts`, emitted at build time) and treats it
-- as version 0 in-process. The BE never hardcodes defaults (contract §2).
CREATE TABLE IF NOT EXISTS public.website_settings (
    id          BIGSERIAL PRIMARY KEY,
    version     INT NOT NULL UNIQUE,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  UUID NULL REFERENCES public.noctus_users(id)
);

CREATE INDEX IF NOT EXISTS ix_website_settings_version
    ON public.website_settings (version DESC);

ALTER TABLE public.website_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON public.website_settings;
CREATE POLICY "service_role_bypass" ON public.website_settings FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── website_leads ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.website_leads (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            TEXT NOT NULL CHECK (source IN ('waitlist', 'brief', 'contact', 'signup_intent')),
    name              TEXT NOT NULL,
    email             TEXT NULL,
    phone_e164        TEXT NULL,
    company           TEXT NULL,
    profile           TEXT NULL CHECK (profile IN ('smb', 'enterprise', 'developer', 'solo') OR profile IS NULL),
    product_interest  TEXT[] NOT NULL DEFAULT '{}',
    message           TEXT NULL,
    locale            TEXT NOT NULL DEFAULT 'pt-BR' CHECK (locale IN ('pt-BR', 'en')),
    utm               JSONB NOT NULL DEFAULT '{}',
    landing_path      TEXT NULL,
    referrer          TEXT NULL,
    -- {marketing: bool, text_version: str, at: iso, ip_hash: str} — LGPD proof.
    consent           JSONB NOT NULL,
    stage             TEXT NOT NULL DEFAULT 'novo' CHECK (
                          stage IN ('novo', 'contatado', 'qualificado', 'proposta', 'ganho', 'perdido', 'descartado')
                      ),
    owner_user_id     UUID NULL REFERENCES public.noctus_users(id),
    owner_agent       TEXT NULL,
    score             INT NULL,
    next_action       TEXT NULL,
    next_action_at    TIMESTAMPTZ NULL,
    lost_reason       TEXT NULL,
    -- lower(email) or phone_e164 — NOT unique; a repeat submission merges
    -- into the same lead by appending a `form_submit` activity, never a
    -- second row (contract §3, "Side effects of POST /leads").
    dedupe_key        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_website_leads_dedupe_key ON public.website_leads (dedupe_key);
CREATE INDEX IF NOT EXISTS ix_website_leads_created_at ON public.website_leads (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_website_leads_stage ON public.website_leads (stage);
CREATE INDEX IF NOT EXISTS ix_website_leads_source ON public.website_leads (source);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE OR REPLACE TRIGGER set_updated_at_website_leads
    BEFORE UPDATE ON public.website_leads
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.website_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON public.website_leads;
CREATE POLICY "service_role_bypass" ON public.website_leads FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── website_lead_activities ────────────────────────────────────────────
-- Append-only timeline. `fanout_failed` is the "never silent" contract
-- (10-conversion-and-leads.md § Fan-out): every notify/WAHA/webhook
-- failure lands here with `{channel, error}` instead of vanishing.
CREATE TABLE IF NOT EXISTS public.website_lead_activities (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id   uuid NOT NULL REFERENCES public.website_leads(id) ON DELETE CASCADE,
    at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind      TEXT NOT NULL CHECK (kind IN (
                  'created', 'form_submit', 'note', 'stage_change', 'whatsapp_out',
                  'whatsapp_in', 'email_out', 'call', 'agent_action', 'handoff', 'fanout_failed'
              )),
    -- 'user:<uuid>' | 'agent:<name>' | 'system'
    actor     TEXT NOT NULL,
    payload   JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_website_lead_activities_lead_id ON public.website_lead_activities (lead_id, at DESC);

ALTER TABLE public.website_lead_activities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON public.website_lead_activities;
CREATE POLICY "service_role_bypass" ON public.website_lead_activities FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── website_events ─────────────────────────────────────────────────────
-- First-party analytics (contract §3, `POST /api/website/events`). NO PII
-- — see `12-privacy-lgpd-tracking.md` § First-party events.
CREATE TABLE IF NOT EXISTS public.website_events (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    anon_id     TEXT NULL,
    session_id  TEXT NULL,
    event       TEXT NOT NULL,
    path        TEXT NULL,
    props       JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_website_events_at ON public.website_events (at DESC);
CREATE INDEX IF NOT EXISTS ix_website_events_event ON public.website_events (event, at DESC);

ALTER TABLE public.website_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_bypass" ON public.website_events;
CREATE POLICY "service_role_bypass" ON public.website_events FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── is_website_editor(uid) ─────────────────────────────────────────────
-- admin OR marketing. SECURITY DEFINER + locked search_path per the
-- platform's RLS-self-reference-recursion-avoidance convention (queries
-- `noctus_users` directly, never through a policy on itself).
CREATE OR REPLACE FUNCTION public.is_website_editor(uid uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, public
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.noctus_users
        WHERE id = uid AND role IN ('admin', 'marketing')
    );
$$;
