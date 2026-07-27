-- 033_meta_ads_leads.sql — Meta Lead-Ads (Instant Form) persistence
-- (roadmap `meta-ads-console-2026-07`, Phase 3): store the leads that
-- come from the operator's Meta campaigns so they can be consumed,
-- notified on, and enriched — beyond the live read-only view shipped
-- 2026-07-27.
--
-- DATA MODEL — "typed core + JSONB tail" (operator decision 2026-07-27):
-- the fields that are ALWAYS present and that we filter/dedupe/join on
-- (name/email/phone + campaign/form/platform/time) are promoted to real
-- typed columns; the VARIABLE per-form qualifying questions — which
-- differ form to form, plus hidden fields Meta injects (e.g. a `REF`
-- tracking code that is NOT in the form's question list) — live in a
-- single `answers JSONB` column with a GIN index. This keeps the common
-- fields queryable/indexable AND absorbs any shape a future form throws
-- at us WITHOUT a schema change. (Postgres `jsonb`, not stringified
-- text: same flexibility, but queryable in-place — `answers->>'k'`,
-- `answers ? 'k'`, `@>` — with no app-side JSON.parse.)
--
-- RLS shape mirrors 030_meta_ads.sql exactly: authenticated reads via
-- `public.current_org_id()` (SECURITY DEFINER, resolves the caller's org
-- from `public.noctus_users` — NEVER `auth.jwt()` / `user_metadata`, per
-- `memory/feedback_rls_never_key_on_user_metadata.md`); service_role ALL
-- for backend sync writes (admin client). Leads are workspace-global
-- (single System-User ad account), scoped to the configured
-- `META_ADS_ORG_ID` org, same as the ads_* tables.
--
-- PREREQUISITE: public.current_org_id() (011_rls_current_org_id.sql).
-- Forward-only + idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS).
--
-- `created_time` is Meta's lead SUBMISSION timestamp (tz-aware), NOT the
-- sync time — `synced_at` carries that. The lead `id` is Meta's own
-- globally-unique lead id (natural PK — upserts are idempotent on it).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ─── meta_ads_lead_forms ─────────────────────────────────────────────────
-- One row per (org, lead-gen form). Stores the form's FIELD SCHEMA
-- (`questions`) so the app can render answers with their labels/types and
-- map answer keys → questions WITHOUT re-hitting Graph. `leads_count` is
-- Meta's cumulative counter (available without `leads_retrieval`).
CREATE TABLE IF NOT EXISTS social_wiring.meta_ads_lead_forms (
    id            TEXT PRIMARY KEY,          -- Meta leadgen form id
    org_id        UUID NOT NULL,
    page_id       TEXT,
    name          TEXT,
    status        TEXT,
    locale        TEXT,
    leads_count   INTEGER,
    questions     JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{key,label,type,options}]
    created_time  TIMESTAMPTZ,
    synced_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw           JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.meta_ads_lead_forms ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "meta_ads_lead_forms_select_own_org" ON social_wiring.meta_ads_lead_forms;
CREATE POLICY "meta_ads_lead_forms_select_own_org" ON social_wiring.meta_ads_lead_forms
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "meta_ads_lead_forms_service_role" ON social_wiring.meta_ads_lead_forms;
CREATE POLICY "meta_ads_lead_forms_service_role" ON social_wiring.meta_ads_lead_forms
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_meta_ads_lead_forms_org_count
    ON social_wiring.meta_ads_lead_forms (org_id, leads_count DESC);

-- ─── meta_ads_leads ──────────────────────────────────────────────────────
-- One row per submitted lead. Typed core columns (promoted for
-- filter/dedupe/join) + `answers JSONB` for the variable questions +
-- hidden fields, GIN-indexed. `full_name`/`email`/`phone` are extracted
-- from `field_data` by the owning form's question TYPE (FULL_NAME / EMAIL
-- / PHONE) during ingest, so the promotion is robust to the label-vs-key
-- variance across forms.
CREATE TABLE IF NOT EXISTS social_wiring.meta_ads_leads (
    id             TEXT PRIMARY KEY,         -- Meta lead id (globally unique)
    org_id         UUID NOT NULL,
    form_id        TEXT,
    form_name      TEXT,
    ad_id          TEXT,
    adset_id       TEXT,
    campaign_id    TEXT,
    campaign_name  TEXT,
    platform       TEXT,
    is_organic     BOOLEAN,
    created_time   TIMESTAMPTZ,              -- Meta submission time
    -- promoted, searchable/dedupable contact fields:
    full_name      TEXT,
    email          TEXT,
    phone          TEXT,
    -- the variable long tail (qualifying questions + hidden fields):
    answers        JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw            JSONB,                     -- full Meta field_data payload
    synced_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.meta_ads_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "meta_ads_leads_select_own_org" ON social_wiring.meta_ads_leads;
CREATE POLICY "meta_ads_leads_select_own_org" ON social_wiring.meta_ads_leads
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "meta_ads_leads_service_role" ON social_wiring.meta_ads_leads;
CREATE POLICY "meta_ads_leads_service_role" ON social_wiring.meta_ads_leads
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Read patterns: recent-first per org, per-form, per-campaign.
CREATE INDEX IF NOT EXISTS idx_sw_meta_ads_leads_org_created
    ON social_wiring.meta_ads_leads (org_id, created_time DESC);
CREATE INDEX IF NOT EXISTS idx_sw_meta_ads_leads_org_form
    ON social_wiring.meta_ads_leads (org_id, form_id);
CREATE INDEX IF NOT EXISTS idx_sw_meta_ads_leads_org_campaign
    ON social_wiring.meta_ads_leads (org_id, campaign_id);
-- Query INSIDE the variable answers (indexed): `answers ? 'k'`, `@>`.
CREATE INDEX IF NOT EXISTS idx_sw_meta_ads_leads_answers_gin
    ON social_wiring.meta_ads_leads USING gin (answers);
