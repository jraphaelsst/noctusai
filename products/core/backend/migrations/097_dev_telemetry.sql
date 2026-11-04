-- 097: dev telemetry — how our own development work uses the machine and Claude (owner, 2026-11-04).
--
-- Owner: "measure work … seed this as a frequent workflow/pattern/evaluation so we keep track as how our usage is
-- going, say it per cost, machine usage, tokens, chars and everything that's essential for a job" and "keep track of
-- os data so we can keep track and measure and decide on usage". The dashboard reads these tables directly (real
-- data, prototype-first), then the page becomes code in core admin / the platform-observability organ.
--
-- Writer: `noctus.dev.usage_eval action=sync` on the developer's machine (service role), idempotent upserts.
-- Sources: Claude Code transcripts (~/.claude/projects/**.jsonl: per-request usage, deduped by message id) and the
-- hardware-admission log (~/.noctus/hw-admission.ndjson: `sample` and `ran` rows, owned by noctus.dev.hw_admission).
-- Deliberately NOT public.ai_usage: that is the product LLM ledger (org-attributed, credit-charged); Claude Code
-- dev usage is subscription-equivalent cost and must never enter product cost or credit numbers.
-- LGPD: no prompt/response text — counts only.
-- RLS on, no policies: service role / owner SQL only.

CREATE TABLE IF NOT EXISTS public.dev_telemetry_claude (
    host               text        NOT NULL,
    bucket             timestamptz NOT NULL,          -- 5-minute bucket start (UTC)
    session_id         text        NOT NULL,
    agent_id           text        NOT NULL DEFAULT '', -- '' = the main session; otherwise the subagent id
    project            text        NOT NULL,          -- the ~/.claude/projects/<dir> the transcript lives in
    model              text        NOT NULL,
    requests           integer     NOT NULL DEFAULT 0,
    input_tokens       bigint      NOT NULL DEFAULT 0,
    output_tokens      bigint      NOT NULL DEFAULT 0,
    thinking_tokens    bigint      NOT NULL DEFAULT 0,
    cache_read_tokens  bigint      NOT NULL DEFAULT 0,
    cache_write_tokens bigint      NOT NULL DEFAULT 0,
    cost_usd           numeric(12,6) NOT NULL DEFAULT 0, -- API-list-price equivalent (seed estimate_cost_usd)
    prompt_chars       bigint      NOT NULL DEFAULT 0, -- typed user text
    output_chars       bigint      NOT NULL DEFAULT 0, -- assistant text + thinking + tool-call input
    tool_result_chars  bigint      NOT NULL DEFAULT 0,
    tool_calls         integer     NOT NULL DEFAULT 0,
    price_version      text        NOT NULL DEFAULT 'unpriced',
    synced_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (host, bucket, session_id, agent_id, model)
);

CREATE TABLE IF NOT EXISTS public.dev_telemetry_os (
    host             text        NOT NULL,
    ts               timestamptz NOT NULL,
    phase            text,
    overloaded       boolean,
    busy_slots       integer,
    cpu_idle_pct     numeric(5,1),
    reclaimable_mb   integer,
    swapout_per_s    numeric(10,1),
    load_1m          numeric(6,2),
    cpu_cores        integer,
    claude_sessions  integer,
    extra            jsonb       NOT NULL DEFAULT '{}'::jsonb,
    synced_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (host, ts)
);

CREATE TABLE IF NOT EXISTS public.dev_telemetry_jobs (
    host                 text        NOT NULL,
    ts                   timestamptz NOT NULL,      -- admission time
    job                  text        NOT NULL,      -- <kind>:<target>
    kind                 text        NOT NULL,
    target               text        NOT NULL,
    event                text        NOT NULL,      -- ran | not_admitted
    phase                text,
    admitted             boolean,
    waited_s             numeric(10,1),
    duration_s           numeric(10,1),
    children_peak_rss_mb numeric(10,1),
    exit_code            integer,
    metrics              jsonb       NOT NULL DEFAULT '{}'::jsonb,
    synced_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (host, ts, job, event)
);

-- Phase changes / experiment windows (e.g. the 2026-11-04 slot trial), so every chart can split before/after.
CREATE TABLE IF NOT EXISTS public.dev_telemetry_marks (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host      text        NOT NULL,
    ts        timestamptz NOT NULL,
    kind      text        NOT NULL CHECK (kind IN ('phase_change', 'window_start', 'window_end', 'note')),
    label     text        NOT NULL,
    payload   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (host, ts, kind, label)
);

CREATE INDEX IF NOT EXISTS dev_telemetry_claude_bucket_idx ON public.dev_telemetry_claude (bucket);
CREATE INDEX IF NOT EXISTS dev_telemetry_os_ts_idx ON public.dev_telemetry_os (ts);
CREATE INDEX IF NOT EXISTS dev_telemetry_jobs_ts_idx ON public.dev_telemetry_jobs (ts);

ALTER TABLE public.dev_telemetry_claude ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dev_telemetry_os     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dev_telemetry_jobs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dev_telemetry_marks  ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.dev_telemetry_claude IS 'Dev telemetry: Claude Code usage per host x 5-min bucket x session/agent x model (tokens, API-equivalent cost, chars, tool calls). Written by noctus.dev.usage_eval. Counts only, no text.';
COMMENT ON TABLE public.dev_telemetry_os IS 'Dev telemetry: OS samples from the hardware-admission sampler (CPU idle, reclaimable memory, swap-out, load, claude sessions). Written by noctus.dev.usage_eval.';
COMMENT ON TABLE public.dev_telemetry_jobs IS 'Dev telemetry: heavy job admissions/runs through the hardware-admission slot. Written by noctus.dev.usage_eval.';
COMMENT ON TABLE public.dev_telemetry_marks IS 'Dev telemetry: phase changes and experiment windows used to split before/after.';
