-- 112: "Uso e custo de IA" (core /admin/uso) — contract products/core/docs/ai-usage-contract.md §2.
--
-- Two sources, never summed: (a) Anthropic Admin usage/cost analytics, synced by the core scheduler job
-- `anthropic_usage_snapshot`; (b) our own ledger (dev_telemetry_claude + dev_deliveries).
-- TIER: platform. RLS on, NO policies, no browser grant: writes are service-role only, reads go through the
-- BE only (/api/admin/usage/ai/*). Never PostgREST-exposed to anon/authenticated.
--
-- Backward compatible with the previous image: only new tables + two defaulted columns on
-- dev_telemetry_claude (constant DEFAULT = no table rewrite). Idempotent (replay applies it twice).

SET lock_timeout = '5s';

-- ── Anthropic usage, one row per (day, 5-dimension key) ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ai_anthropic_usage_daily (
    day                 date        NOT NULL,
    dims_key            text        NOT NULL,        -- sha1 of model|workspace_id|api_key_id|service_tier|context_window
    model               text        NOT NULL DEFAULT '',
    workspace_id        text        NOT NULL DEFAULT '',
    api_key_id          text        NOT NULL DEFAULT '',
    service_tier        text        NOT NULL DEFAULT '',
    context_window      text        NOT NULL DEFAULT '',
    uncached_input      bigint      NOT NULL DEFAULT 0,
    cache_write_5m      bigint      NOT NULL DEFAULT 0,
    cache_write_1h      bigint      NOT NULL DEFAULT 0,
    cache_read          bigint      NOT NULL DEFAULT 0,
    output_tokens       bigint      NOT NULL DEFAULT 0,
    web_search_requests integer,
    requests            integer,
    data_refreshed_at   timestamptz NOT NULL,
    is_final            boolean     NOT NULL DEFAULT false,
    synced_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (day, dims_key)
);

-- ── Anthropic cost, decimal CENTS as the API returns them ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ai_anthropic_cost_daily (
    day                 date        NOT NULL,
    dims_key            text        NOT NULL,        -- sha1 of model|workspace_id|api_key_id|cost_type|token_type
    model               text        NOT NULL DEFAULT '',
    workspace_id        text        NOT NULL DEFAULT '',
    api_key_id          text        NOT NULL DEFAULT '',
    cost_type           text        NOT NULL DEFAULT '',
    token_type          text        NOT NULL DEFAULT '',
    amount_cents        numeric(20,6) NOT NULL,
    list_amount_cents   numeric(20,6),
    currency            text        NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    data_refreshed_at   timestamptz NOT NULL,
    is_final            boolean     NOT NULL DEFAULT false,
    synced_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (day, dims_key)
);

CREATE TABLE IF NOT EXISTS public.ai_anthropic_rate_limits (
    scope               text        NOT NULL CHECK (scope IN ('org', 'workspace')),
    workspace_id_key    text        NOT NULL DEFAULT '',   -- '' for the org scope
    model_group         text        NOT NULL,
    metric              text        NOT NULL,
    limit_value         integer     NOT NULL,
    synced_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, workspace_id_key, model_group, metric)
);

CREATE TABLE IF NOT EXISTS public.ai_source_sync_runs (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source              text        NOT NULL,
    endpoint            text        NOT NULL,
    window_from         date,
    window_to           date,
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text        NOT NULL CHECK (status IN ('ok', 'error', 'unavailable')),
    reason_code         text,
    http_status         integer,
    rows_written        integer,
    rows_deleted        integer,
    data_refreshed_at   timestamptz
);
CREATE INDEX IF NOT EXISTS ai_source_sync_runs_source_id_idx ON public.ai_source_sync_runs (source, id DESC);

-- ── Delivery scoreboard (ledger → rows), written by noctus.dev.usage_eval sync_deliveries ─────────────────
CREATE TABLE IF NOT EXISTS public.dev_deliveries (
    line_hash            text        PRIMARY KEY,
    slug                 text        NOT NULL,
    branch               text,
    sha                  text,
    agent                text        NOT NULL,
    model                text,
    planner_model        text,
    ts                   timestamptz NOT NULL,
    q                    jsonb,
    q_weighted           numeric(6,3),
    first_pass           boolean,
    rework_commits       integer,
    tokens               bigint,
    tool_uses            integer,
    wall_s_measured      numeric(12,3),
    wall_s_self_reported numeric(12,3),
    duration_minutes     numeric(10,2),
    outcome              text,
    cost_usd             numeric(12,6),
    cost_is_estimate     boolean     NOT NULL DEFAULT true,
    price_version        text,
    ambiente             text        NOT NULL DEFAULT 'local' CHECK (ambiente IN ('prod', 'local', 'ci')),
    origem               text        NOT NULL DEFAULT 'desconhecido' CHECK (origem IN ('api_key', 'assinatura', 'desconhecido')),
    ingested_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (slug, agent, ts)
);
CREATE INDEX IF NOT EXISTS dev_deliveries_ts_idx ON public.dev_deliveries (ts);

-- ── Expand only: where / how the Claude Code session ran ───────────────────────────────────────────────────
ALTER TABLE public.dev_telemetry_claude
    ADD COLUMN IF NOT EXISTS ambiente text NOT NULL DEFAULT 'local' CHECK (ambiente IN ('prod', 'local', 'ci'));
ALTER TABLE public.dev_telemetry_claude
    ADD COLUMN IF NOT EXISTS origem text NOT NULL DEFAULT 'desconhecido' CHECK (origem IN ('api_key', 'assinatura', 'desconhecido'));

-- ── RLS on, no policies, no browser grant, tier declared ───────────────────────────────────────────────────
ALTER TABLE public.ai_anthropic_usage_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_anthropic_cost_daily  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_anthropic_rate_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_source_sync_runs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dev_deliveries           ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.ai_anthropic_usage_daily FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ai_anthropic_cost_daily  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ai_anthropic_rate_limits FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.ai_source_sync_runs      FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.dev_deliveries           FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.ai_anthropic_usage_daily IS 'tier:platform';
COMMENT ON TABLE public.ai_anthropic_cost_daily  IS 'tier:platform';
COMMENT ON TABLE public.ai_anthropic_rate_limits IS 'tier:platform';
COMMENT ON TABLE public.ai_source_sync_runs      IS 'tier:platform';
COMMENT ON TABLE public.dev_deliveries           IS 'tier:platform';

-- ── Replace-window (ONE transaction per call): delete the window's days, insert the freshly pulled rows. ──
-- A bare upsert would keep rows a revision removed. SECURITY INVOKER: only a role that can already write the
-- table (service_role bypasses RLS) can use it; EXECUTE is not left to PUBLIC/anon/authenticated.
CREATE OR REPLACE FUNCTION public.ai_replace_anthropic_usage_window(p_from date, p_to date, p_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE d integer; w integer;
BEGIN
    DELETE FROM public.ai_anthropic_usage_daily WHERE day BETWEEN p_from AND p_to;
    GET DIAGNOSTICS d = ROW_COUNT;
    INSERT INTO public.ai_anthropic_usage_daily
        SELECT * FROM jsonb_populate_recordset(NULL::public.ai_anthropic_usage_daily, p_rows);
    GET DIAGNOSTICS w = ROW_COUNT;
    RETURN jsonb_build_object('deleted', d, 'written', w);
END $$;

CREATE OR REPLACE FUNCTION public.ai_replace_anthropic_cost_window(p_from date, p_to date, p_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE d integer; w integer;
BEGIN
    DELETE FROM public.ai_anthropic_cost_daily WHERE day BETWEEN p_from AND p_to;
    GET DIAGNOSTICS d = ROW_COUNT;
    INSERT INTO public.ai_anthropic_cost_daily
        SELECT * FROM jsonb_populate_recordset(NULL::public.ai_anthropic_cost_daily, p_rows);
    GET DIAGNOSTICS w = ROW_COUNT;
    RETURN jsonb_build_object('deleted', d, 'written', w);
END $$;

CREATE OR REPLACE FUNCTION public.ai_replace_anthropic_rate_limits(p_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE d integer; w integer;
BEGIN
    DELETE FROM public.ai_anthropic_rate_limits;
    GET DIAGNOSTICS d = ROW_COUNT;
    INSERT INTO public.ai_anthropic_rate_limits
        SELECT * FROM jsonb_populate_recordset(NULL::public.ai_anthropic_rate_limits, p_rows);
    GET DIAGNOSTICS w = ROW_COUNT;
    RETURN jsonb_build_object('deleted', d, 'written', w);
END $$;

REVOKE ALL ON FUNCTION public.ai_replace_anthropic_usage_window(date, date, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.ai_replace_anthropic_cost_window(date, date, jsonb)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.ai_replace_anthropic_rate_limits(jsonb)              FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ai_replace_anthropic_usage_window(date, date, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.ai_replace_anthropic_cost_window(date, date, jsonb)  TO service_role;
GRANT EXECUTE ON FUNCTION public.ai_replace_anthropic_rate_limits(jsonb)              TO service_role;
