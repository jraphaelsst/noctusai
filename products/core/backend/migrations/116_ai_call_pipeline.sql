-- Migration: 116_ai_call_pipeline
-- Schema: public (core)
-- Project: agentic-architecture, slice seed-llm-call-pipeline.
--
-- WHAT (one change, three seed-level capabilities that share the central ledger `public.ai_usage`, core 091):
--   1. TRACING. `ai_usage` gains trace_id / span_id / parent_span_id / latency_ms / prompt_version: every LLM call
--      row IS its span (tokens, cache-read tokens, model, cost already there). `public.ai_trace_spans` holds the
--      NON-LLM spans (tool calls, guardrail verdicts, internal steps) of the same traces. The view
--      `public.ai_trace_timeline` unions both, ordered by trace: that is the query surface
--      (`select * from ai_trace_timeline where trace_id = '...' order by started_at`).
--   2. SPEND GUARD. `public.ai_spend_window(org, product, feature, hours)` = rolling-window actual spend read from
--      `ai_usage` (the seed per-surface guard `llm/spend_guard.py` calls it; one aggregate, not a paged row scan).
--      The view `public.ai_spend_24h_by_surface` is the REPORT the owner/steward reads to choose per-surface limits.
--      No limit exists in the database: limits are seed configuration, default = none (observe/report only).
--
-- Backward compatible with the previous image: ADDITIVE only (nullable columns without default = metadata-only
-- ALTER, no rewrite; new table/function/views). The OLD image keeps inserting ai_usage rows without the new columns.
-- ORDER: apply this migration BEFORE the new image (the new image's ledger insert names the new columns; it also
-- degrades to storing them under `extra` if the columns are missing, loudly, so no billing row is ever lost).
-- Re-runnable: IF NOT EXISTS / OR REPLACE / DROP-then-CREATE.
-- NOC-REMEDIATE[ai-trace-spans-retention]: add a purge for ai_trace_spans (tool/guardrail rows only; ai_usage is billing and stays) once real volume is measured — 2026-12-09
SET search_path = public, public;
SET lock_timeout = '5s';

-- ── 1a. ai_usage: the LLM-call span ───────────────────────────────────────────────────────────────────────────
ALTER TABLE public.ai_usage
    ADD COLUMN IF NOT EXISTS trace_id       TEXT CHECK (trace_id IS NULL OR length(trace_id) BETWEEN 1 AND 64),
    ADD COLUMN IF NOT EXISTS span_id        TEXT CHECK (span_id IS NULL OR length(span_id) BETWEEN 1 AND 64),
    ADD COLUMN IF NOT EXISTS parent_span_id TEXT CHECK (parent_span_id IS NULL OR length(parent_span_id) BETWEEN 1 AND 64),
    ADD COLUMN IF NOT EXISTS latency_ms     INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    ADD COLUMN IF NOT EXISTS prompt_version TEXT CHECK (prompt_version IS NULL OR length(prompt_version) <= 200);

CREATE INDEX IF NOT EXISTS ix_ai_usage_trace
    ON public.ai_usage (trace_id, created_at)
    WHERE trace_id IS NOT NULL;

-- ── 1b. ai_trace_spans: tool / guardrail / internal spans ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ai_trace_spans (
    id               BIGSERIAL PRIMARY KEY,
    trace_id         TEXT NOT NULL CHECK (length(trace_id) BETWEEN 1 AND 64),
    span_id          TEXT NOT NULL CHECK (length(span_id) BETWEEN 1 AND 64),
    parent_span_id   TEXT CHECK (parent_span_id IS NULL OR length(parent_span_id) BETWEEN 1 AND 64),
    kind             TEXT NOT NULL CHECK (kind IN ('tool', 'guardrail', 'internal')),
    name             TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_ms       INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    status           TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error', 'blocked')),
    guardrail_verdict TEXT CHECK (guardrail_verdict IS NULL OR length(guardrail_verdict) <= 80),
    org_id           UUID,
    product          TEXT CHECK (product IS NULL OR length(product) <= 200),
    agent_key        TEXT CHECK (agent_key IS NULL OR length(agent_key) <= 200),
    conversation_id  TEXT CHECK (conversation_id IS NULL OR length(conversation_id) <= 200),
    prompt_version   TEXT CHECK (prompt_version IS NULL OR length(prompt_version) <= 200),
    attributes       JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ai_trace_spans_span_unique UNIQUE (trace_id, span_id)
);
-- Non-LLM spans of an AI trace (tool call, guardrail verdict, internal step). Counts, names, ids and timings only — never prompt/response/tool payload text.
COMMENT ON TABLE public.ai_trace_spans IS 'tier:service';
CREATE INDEX IF NOT EXISTS ix_ai_trace_spans_trace ON public.ai_trace_spans (trace_id, started_at);
CREATE INDEX IF NOT EXISTS ix_ai_trace_spans_org_started ON public.ai_trace_spans (org_id, started_at DESC);

ALTER TABLE public.ai_trace_spans ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ai_trace_spans FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.ai_trace_spans TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.ai_trace_spans_id_seq TO service_role;
DROP POLICY IF EXISTS "service_role_bypass" ON public.ai_trace_spans;
CREATE POLICY "service_role_bypass" ON public.ai_trace_spans FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── 1c. the unified trace view ───────────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS public.ai_trace_timeline;
CREATE VIEW public.ai_trace_timeline WITH (security_invoker = true) AS
    SELECT u.trace_id, u.span_id, u.parent_span_id, 'llm'::text AS kind,
           u.model AS name,
           u.created_at - make_interval(secs => COALESCE(u.latency_ms, 0)::double precision / 1000.0) AS started_at,
           u.latency_ms, u.status, NULL::text AS guardrail_verdict,
           u.org_id, u.product, u.agent_key, u.conversation_id, u.prompt_version,
           u.provider, u.model, u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cost_usd,
           u.extra AS attributes
      FROM public.ai_usage u
     WHERE u.trace_id IS NOT NULL
    UNION ALL
    SELECT s.trace_id, s.span_id, s.parent_span_id, s.kind,
           s.name,
           s.started_at, s.latency_ms, s.status, s.guardrail_verdict,
           s.org_id, s.product, s.agent_key, s.conversation_id, s.prompt_version,
           NULL::text, NULL::text, NULL::integer, NULL::integer, NULL::integer, NULL::numeric,
           s.attributes
      FROM public.ai_trace_spans s;
COMMENT ON VIEW public.ai_trace_timeline IS 'tier:service';
REVOKE ALL ON public.ai_trace_timeline FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.ai_trace_timeline TO service_role;

-- ── 2a. rolling-window actual spend (the seed per-surface guard's read) ───────────────────────────────────────
CREATE OR REPLACE FUNCTION public.ai_spend_window(
    p_org_id  UUID,
    p_product TEXT DEFAULT NULL,
    p_feature TEXT DEFAULT NULL,
    p_hours   INTEGER DEFAULT 24
) RETURNS NUMERIC
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT COALESCE(SUM(cost_usd), 0)
      FROM public.ai_usage
     WHERE org_id = p_org_id
       AND created_at > now() - make_interval(hours => p_hours)
       AND (p_product IS NULL OR product = p_product)
       AND (p_feature IS NULL OR feature = p_feature);
$$;
REVOKE ALL ON FUNCTION public.ai_spend_window(UUID, TEXT, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ai_spend_window(UUID, TEXT, TEXT, INTEGER) TO service_role;

-- ── 2b. the report the owner/steward reads to pick per-surface limits ─────────────────────────────────────────
DROP VIEW IF EXISTS public.ai_spend_24h_by_surface;
CREATE VIEW public.ai_spend_24h_by_surface WITH (security_invoker = true) AS
    SELECT org_id, product, feature, purpose,
           count(*)                                   AS calls,
           round(sum(cost_usd), 6)                    AS cost_usd_24h,
           round(sum(cost_usd) FILTER (WHERE status <> 'ok'), 6) AS cost_usd_failed_24h,
           max(created_at)                            AS last_call_at
      FROM public.ai_usage
     WHERE created_at > now() - interval '24 hours'
     GROUP BY org_id, product, feature, purpose;
COMMENT ON VIEW public.ai_spend_24h_by_surface IS 'tier:service';
REVOKE ALL ON public.ai_spend_24h_by_surface FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.ai_spend_24h_by_surface TO service_role;
