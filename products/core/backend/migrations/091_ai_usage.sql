-- Migration: 091_ai_usage
-- Schema: public (core)
-- Roadmap: project-history/roadmaps/product-agents-platform-2026-10.md — decision D25.
--
-- WHAT: ONE central, complete, attributed, priced LLM usage ledger — the
-- foundation per-org → per-product billing reads (the prepaid credit wallet
-- is the next slice; it fills the reserved `charged_credits` column).
--
--   1. public.ai_usage — one row per LLM call of EVERY product (core included),
--      written by `noctusai_lib.integrations.llm.ledger.CentralUsageSink`
--      (service role). Attribution: org → product → feature → purpose /
--      user / conversation / agent (`attribution.py`). Priced at WRITE time
--      from the effective model catalog (`price_version` says which rate
--      card), converted to BRL at the latest stored BCB PTAX (`fx_rate`).
--      status: ok | partial (a stream cut short, tokens may be estimated —
--      `extra.tokens_estimated`) | error (the provider call raised).
--   2. Append-only: UPDATE / DELETE refused by trigger for EVERY role,
--      service role included — with exactly ONE exception, the wallet's
--      write-once of `charged_credits` (NULL → value, every other column
--      unchanged).
--   3. Access: authenticated SELECT only; RLS = members of the row's org
--      (active `org_memberships`) + platform admins; no authenticated /
--      anon write grant at all. Writes: service role INSERT.
--
-- Replaces the per-product `<schema>.llm_usage` tables as the read source
-- (core admin `/api/admin/llm-usage`, the seed `/api/llm/usage`, the budget
-- guard, social-wiring custos) and the two hand-kept product→schema maps.
--
-- LGPD: identifiers, counts and prices only — never prompt / response text.
-- Re-runnable: IF NOT EXISTS / OR REPLACE / DROP-then-CREATE.
SET search_path = public, public;

-- ── 1. table ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ai_usage (
    id                   BIGSERIAL PRIMARY KEY,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    org_id               UUID,
    product              TEXT NOT NULL CHECK (length(product) BETWEEN 1 AND 200),
    feature              TEXT CHECK (feature IS NULL OR length(feature) <= 200),
    purpose              TEXT CHECK (purpose IS NULL OR length(purpose) <= 200),
    user_id              UUID,
    conversation_id      TEXT CHECK (conversation_id IS NULL OR length(conversation_id) <= 200),
    agent_key            TEXT CHECK (agent_key IS NULL OR length(agent_key) <= 200),
    provider             TEXT NOT NULL CHECK (length(provider) BETWEEN 1 AND 40),
    model                TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    model_version        TEXT,
    operation            TEXT NOT NULL
                             CHECK (operation IN ('chat', 'embedding', 'audio', 'vision', 'image_edit')),
    batch                BOOLEAN NOT NULL DEFAULT false,
    input_tokens         INTEGER CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens        INTEGER CHECK (output_tokens IS NULL OR output_tokens >= 0),
    cache_read_tokens    INTEGER CHECK (cache_read_tokens IS NULL OR cache_read_tokens >= 0),
    cache_write_tokens   INTEGER CHECK (cache_write_tokens IS NULL OR cache_write_tokens >= 0),
    image_input_tokens   INTEGER CHECK (image_input_tokens IS NULL OR image_input_tokens >= 0),
    image_output_tokens  INTEGER CHECK (image_output_tokens IS NULL OR image_output_tokens >= 0),
    cost_usd             NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    fx_rate              NUMERIC(12, 5) NOT NULL CHECK (fx_rate > 0),
    cost_brl             NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (cost_brl >= 0),
    price_version        TEXT NOT NULL CHECK (length(price_version) BETWEEN 1 AND 80),
    status               TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'partial', 'error')),
    request_id           TEXT CHECK (request_id IS NULL OR length(request_id) <= 200),
    extra                JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Reserved for the prepaid credit wallet (next slice): written once,
    -- NULL → value, by the wallet's debit. NULL = not yet charged.
    charged_credits      NUMERIC(18, 6) CHECK (charged_credits IS NULL OR charged_credits >= 0)
);

COMMENT ON TABLE public.ai_usage IS
    'Central LLM usage ledger (D25): one row per call of every product, attributed + priced at write time. '
    'Append-only (trigger); only charged_credits may be written once. Written by CentralUsageSink (service role). '
    'LGPD: no prompt/response text.';

-- ── 2. indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_ai_usage_org_created
    ON public.ai_usage (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_org_product_created
    ON public.ai_usage (org_id, product, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_created
    ON public.ai_usage (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_usage_uncharged
    ON public.ai_usage (org_id, id)
    WHERE charged_credits IS NULL;

-- ── 3. append-only guard ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.guard_ai_usage_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    -- The ONE allowed write after insert: the wallet stamps charged_credits
    -- once (NULL → value) and nothing else changes.
    IF TG_OP = 'UPDATE'
       AND OLD.charged_credits IS NULL
       AND NEW.charged_credits IS NOT NULL
       AND (to_jsonb(NEW) - 'charged_credits') = (to_jsonb(OLD) - 'charged_credits') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'ai_usage_append_only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION public.guard_ai_usage_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_ai_usage_append_only ON public.ai_usage;
CREATE TRIGGER guard_ai_usage_append_only
    BEFORE UPDATE OR DELETE ON public.ai_usage
    FOR EACH ROW EXECUTE FUNCTION public.guard_ai_usage_append_only();

-- TRUNCATE is not a row event — refuse it with a statement trigger too.
DROP TRIGGER IF EXISTS guard_ai_usage_no_truncate ON public.ai_usage;
CREATE TRIGGER guard_ai_usage_no_truncate
    BEFORE TRUNCATE ON public.ai_usage
    FOR EACH STATEMENT EXECUTE FUNCTION public.guard_ai_usage_append_only();

-- ── 4. access ───────────────────────────────────────────────────────────────────
ALTER TABLE public.ai_usage ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ai_usage FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.ai_usage TO authenticated;
REVOKE ALL ON public.ai_usage FROM service_role;
GRANT SELECT, INSERT ON public.ai_usage TO service_role;
GRANT UPDATE (charged_credits) ON public.ai_usage TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.ai_usage_id_seq TO service_role;

DROP POLICY IF EXISTS "service_role_bypass" ON public.ai_usage;
CREATE POLICY "service_role_bypass" ON public.ai_usage
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS ai_usage_member_read ON public.ai_usage;
CREATE POLICY ai_usage_member_read ON public.ai_usage
    FOR SELECT TO authenticated
    USING (
        org_id IN (
            SELECT m.org_id FROM public.org_memberships m
            WHERE m.user_id = (SELECT auth.uid()) AND m.status = 'active'
        )
    );

DROP POLICY IF EXISTS ai_usage_platform_admin_read ON public.ai_usage;
CREATE POLICY ai_usage_platform_admin_read ON public.ai_usage
    FOR SELECT TO authenticated
    USING ((SELECT public.is_platform_admin()));
