-- Migration: 074_transcription_api
-- Schema: public (core)
-- Contract: products/core/projects/transcription-api/CONTRACT.md  §1 auth · §3 quota RPC · §4 data
-- Precedent: products/social-wiring/projects/core-studio/specs/transcription-contract.md §3 (reservar_transcricao)
--
-- WHAT (slice A of the platform async transcription API). Core had NONE of api_tokens /
-- api_token_audit / jobs before this file (verified 2026-10-10), so all three are created here;
-- platform_settings already exists (001) and only gets its kill-switch row.
--   1. public.api_tokens + public.api_token_audit   (SEED-1 shape, = agents 007; service-role only)
--   2. public.jobs + claim_next_job/fail_job/complete_job/extend_lease  (seed jobs.sql.template)
--   3. public.transcricoes_api                       (RLS on, service-role only)
--   4. public.reservar_transcricao_api(...)          (atomic quota reservation)
--   5. private storage bucket core-transcricoes
--   6. platform_settings.transcricao_api_habilitada = false  (kill switch, ships OFF)
-- Re-runnable: every statement is IF NOT EXISTS / OR REPLACE / ON CONFLICT / DROP-then-CREATE POLICY.
SET search_path = public, public;

-- ── 1. api_tokens + api_token_audit (SEED-1 shape) ─────────────────────────────
CREATE TABLE IF NOT EXISTS public.api_tokens (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    label               TEXT NOT NULL,
    token_hash          TEXT NOT NULL UNIQUE,
    token_prefix        TEXT NOT NULL,
    scopes              TEXT[] NOT NULL DEFAULT '{}',
    created_by          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,
    principal_agent_id  UUID,
    issuer              TEXT,
    human_personal      BOOLEAN NOT NULL DEFAULT false,
    minted_by           UUID
);
ALTER TABLE public.api_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.api_tokens;
CREATE POLICY "service_role_bypass" ON public.api_tokens
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_api_tokens_org ON public.api_tokens(org_id) WHERE revoked_at IS NULL;
-- (token_hash is already UNIQUE as a column constraint; no second partial unique index needed.)

CREATE TABLE IF NOT EXISTS public.api_token_audit (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_token_id  UUID NOT NULL REFERENCES public.api_tokens(id),
    org_id        UUID NOT NULL,
    method        TEXT NOT NULL,
    path          TEXT NOT NULL,
    status        INTEGER NOT NULL,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.api_token_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.api_token_audit;
CREATE POLICY "service_role_bypass" ON public.api_token_audit
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_api_token_audit_org ON public.api_token_audit(org_id);
CREATE INDEX IF NOT EXISTS idx_api_token_audit_token ON public.api_token_audit(api_token_id);

-- ── 2. jobs (seed domain/jobs/migrations/jobs.sql.template, schema = public) ───
CREATE TABLE IF NOT EXISTS public.jobs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type              TEXT NOT NULL,
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'running', 'completed', 'failed', 'dead_letter')),
    retry_count       INT NOT NULL DEFAULT 0,
    max_retries       INT NOT NULL DEFAULT 3,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_for     TIMESTAMPTZ,
    dedupe_key        TEXT,
    worker_id         TEXT,
    lease_expires_at  TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_dedupe_key ON public.jobs (dedupe_key);
CREATE INDEX IF NOT EXISTS ix_jobs_status_scheduled ON public.jobs (status, scheduled_for, created_at);
CREATE INDEX IF NOT EXISTS ix_jobs_status_lease ON public.jobs (status, lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_jobs_type ON public.jobs (type);

CREATE OR REPLACE FUNCTION public.claim_next_job(
    p_worker_id     TEXT,
    p_job_types     TEXT[] DEFAULT NULL,
    p_lease_seconds NUMERIC DEFAULT 600
) RETURNS SETOF public.jobs
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
BEGIN
    RETURN QUERY
    UPDATE public.jobs
    SET status = 'running',
        worker_id = p_worker_id,
        lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
        updated_at = v_now
    WHERE id = (
        SELECT id
        FROM public.jobs
        WHERE (
                (status = 'pending' AND (scheduled_for IS NULL OR scheduled_for <= v_now))
                OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at <= v_now)
              )
          AND (p_job_types IS NULL OR type = ANY (p_job_types))
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION public.fail_job(
    p_job_id              UUID,
    p_error               TEXT,
    p_max_retries         INT,
    p_backoff_seconds     NUMERIC,
    p_backoff_multiplier  NUMERIC,
    p_max_backoff_seconds NUMERIC,
    p_dead_letter         BOOLEAN DEFAULT FALSE
) RETURNS SETOF public.jobs
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
BEGIN
    RETURN QUERY
    UPDATE public.jobs
    SET status = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN 'dead_letter'
            ELSE 'pending'
        END,
        retry_count = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN retry_count
            ELSE retry_count + 1
        END,
        scheduled_for = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN scheduled_for
            ELSE v_now + make_interval(
                secs => LEAST(
                    p_backoff_seconds * (p_backoff_multiplier ^ retry_count),
                    p_max_backoff_seconds
                )
            )
        END,
        last_error = p_error,
        worker_id = NULL,
        lease_expires_at = NULL,
        updated_at = v_now
    WHERE id = p_job_id
    RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_job(
    p_job_id UUID
) RETURNS SETOF public.jobs
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.jobs
    SET status = 'completed',
        worker_id = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_job_id AND status <> 'completed'
    RETURNING *;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT * FROM public.jobs WHERE id = p_job_id AND status = 'completed';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.extend_lease(
    p_job_id        UUID,
    p_worker_id     TEXT,
    p_lease_seconds NUMERIC DEFAULT 600
) RETURNS SETOF public.jobs
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.jobs
    SET lease_expires_at = now() + make_interval(secs => p_lease_seconds),
        updated_at = now()
    WHERE id = p_job_id AND status = 'running' AND worker_id = p_worker_id
    RETURNING *;
END;
$$;

ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.jobs;
CREATE POLICY "service_role_bypass" ON public.jobs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- The queue RPCs live in an API-exposed schema: only the backend (service_role) may call them.
REVOKE EXECUTE ON FUNCTION public.claim_next_job(TEXT, TEXT[], NUMERIC) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.fail_job(UUID, TEXT, INT, NUMERIC, NUMERIC, NUMERIC, BOOLEAN) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.complete_job(UUID) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.extend_lease(UUID, TEXT, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_next_job(TEXT, TEXT[], NUMERIC) TO service_role;
GRANT EXECUTE ON FUNCTION public.fail_job(UUID, TEXT, INT, NUMERIC, NUMERIC, NUMERIC, BOOLEAN) TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_job(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.extend_lease(UUID, TEXT, NUMERIC) TO service_role;

-- ── 3. transcricoes_api (CONTRACT §4) ──────────────────────────────────────────
-- storage_path / bytes / formato / expira_em are nullable: the quota RPC inserts the row
-- (na_fila) BEFORE the audio is stored; the router fills them right after.
CREATE TABLE IF NOT EXISTS public.transcricoes_api (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    caller_kind           TEXT NOT NULL CHECK (caller_kind IN ('token', 'user')),
    caller_id             UUID NOT NULL,
    rotulo                TEXT,
    idioma                TEXT NOT NULL DEFAULT 'pt',
    storage_path          TEXT,
    bytes                 BIGINT,
    duracao_s             NUMERIC NOT NULL,
    formato               TEXT,
    status                TEXT NOT NULL DEFAULT 'na_fila'
                              CHECK (status IN ('na_fila', 'processando', 'concluida', 'falhou', 'cancelada')),
    texto                 TEXT,
    segmentos             JSONB,
    erro_codigo           TEXT,
    modelo                TEXT,
    rtf                   NUMERIC,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    iniciado_em           TIMESTAMPTZ,
    concluido_em          TIMESTAMPTZ,
    expira_em             TIMESTAMPTZ,
    audio_apagado_em      TIMESTAMPTZ,
    minutos_reembolsados  BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_transcricoes_api_caller ON public.transcricoes_api (caller_kind, caller_id, criado_em);
CREATE INDEX IF NOT EXISTS ix_transcricoes_api_org ON public.transcricoes_api (org_id, criado_em);
CREATE INDEX IF NOT EXISTS ix_transcricoes_api_status ON public.transcricoes_api (status, criado_em);

ALTER TABLE public.transcricoes_api ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.transcricoes_api;
CREATE POLICY "service_role_bypass" ON public.transcricoes_api
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── 4. reservar_transcricao_api (CONTRACT §3) ──────────────────────────────────
-- Atomic quota check + insert. Returns jsonb:
--   {"ok": true,  "id": "<uuid>"}
--   {"ok": false, "codigo": "<limite_envios_hora|cota_diaria_chamador|limite_em_andamento|
--                              cota_diaria_org|capacidade_diaria|fila_cheia>", "retry_after_s": <int>}
-- Rolling MINUTE sums exclude refunded rows (minutos_reembolsados); submission and in-flight
-- counts do not (a refunded failure still counts as an attempt in the hourly burst limit).
-- Locks (always taken in this order): global -> org -> caller, so the global and per-org caps are
-- race-free too, not only the per-caller ones.
CREATE OR REPLACE FUNCTION public.reservar_transcricao_api(
    p_caller_kind TEXT,
    p_caller_id   UUID,
    p_org_id      UUID,
    p_duracao_s   NUMERIC
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    -- Limits (CONTRACT §3) -- declared once, here.
    c_caller_envios_hora   CONSTANT int     := 20;
    c_caller_min_dia       CONSTANT numeric := 180;
    c_caller_em_andamento  CONSTANT int     := 3;
    c_org_min_dia          CONSTANT numeric := 300;
    c_global_min_dia       CONSTANT numeric := 600;
    c_fila_max             CONSTANT int     := 20;

    v_min       numeric := p_duracao_s / 60.0;
    v_now       timestamptz := now();
    v_n         int;
    v_sum       numeric;
    v_oldest    timestamptz;
    v_id        uuid;
BEGIN
    IF p_caller_kind IS NULL OR p_caller_kind NOT IN ('token', 'user')
       OR p_caller_id IS NULL OR p_org_id IS NULL
       OR p_duracao_s IS NULL OR p_duracao_s <= 0 THEN
        RAISE EXCEPTION 'reservar_transcricao_api: argumentos invalidos';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('transcricao_api:global', 0));
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricao_api:org:' || p_org_id::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricao_api:caller:' || p_caller_kind || ':' || p_caller_id::text, 0));

    -- per caller: in flight
    SELECT count(*) INTO v_n FROM public.transcricoes_api
     WHERE caller_kind = p_caller_kind AND caller_id = p_caller_id
       AND status IN ('na_fila', 'processando');
    IF v_n >= c_caller_em_andamento THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_em_andamento', 'retry_after_s', 30);
    END IF;

    -- per caller: submissions / rolling hour
    SELECT count(*), min(criado_em) INTO v_n, v_oldest FROM public.transcricoes_api
     WHERE caller_kind = p_caller_kind AND caller_id = p_caller_id
       AND criado_em > v_now - interval '1 hour';
    IF v_n >= c_caller_envios_hora THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_envios_hora',
            'retry_after_s', GREATEST(1, ceil(extract(epoch FROM (v_oldest + interval '1 hour' - v_now)))::int));
    END IF;

    -- per caller: minutes / rolling 24h
    SELECT COALESCE(sum(duracao_s), 0) / 60.0, min(criado_em) INTO v_sum, v_oldest FROM public.transcricoes_api
     WHERE caller_kind = p_caller_kind AND caller_id = p_caller_id
       AND criado_em > v_now - interval '24 hours' AND NOT minutos_reembolsados;
    IF v_sum + v_min > c_caller_min_dia THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_chamador',
            'retry_after_s', GREATEST(1, ceil(extract(epoch FROM (COALESCE(v_oldest, v_now) + interval '24 hours' - v_now)))::int));
    END IF;

    -- per org: minutes / rolling 24h
    SELECT COALESCE(sum(duracao_s), 0) / 60.0, min(criado_em) INTO v_sum, v_oldest FROM public.transcricoes_api
     WHERE org_id = p_org_id
       AND criado_em > v_now - interval '24 hours' AND NOT minutos_reembolsados;
    IF v_sum + v_min > c_org_min_dia THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_org',
            'retry_after_s', GREATEST(1, ceil(extract(epoch FROM (COALESCE(v_oldest, v_now) + interval '24 hours' - v_now)))::int));
    END IF;

    -- global: minutes / rolling 24h
    SELECT COALESCE(sum(duracao_s), 0) / 60.0, min(criado_em) INTO v_sum, v_oldest FROM public.transcricoes_api
     WHERE criado_em > v_now - interval '24 hours' AND NOT minutos_reembolsados;
    IF v_sum + v_min > c_global_min_dia THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'capacidade_diaria',
            'retry_after_s', GREATEST(1, ceil(extract(epoch FROM (COALESCE(v_oldest, v_now) + interval '24 hours' - v_now)))::int));
    END IF;

    -- global: queue depth
    SELECT count(*) INTO v_n FROM public.transcricoes_api WHERE status = 'na_fila';
    IF v_n >= c_fila_max THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'fila_cheia', 'retry_after_s', 30);
    END IF;

    INSERT INTO public.transcricoes_api (org_id, caller_kind, caller_id, duracao_s, status)
    VALUES (p_org_id, p_caller_kind, p_caller_id, p_duracao_s, 'na_fila')
    RETURNING id INTO v_id;

    RETURN jsonb_build_object('ok', true, 'id', v_id);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.reservar_transcricao_api(TEXT, UUID, UUID, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reservar_transcricao_api(TEXT, UUID, UUID, NUMERIC) TO service_role;

-- ── 5. Private bucket (never public; access is signed URLs / service-role only) ─
INSERT INTO storage.buckets (id, name, public)
VALUES ('core-transcricoes', 'core-transcricoes', false)
ON CONFLICT (id) DO UPDATE SET public = false;

-- ── 6. Kill switch (ships OFF; flipped by the owner in slice F) ─────────────────
INSERT INTO public.platform_settings (key, value, description, is_secret) VALUES
    ('transcricao_api_habilitada', 'false',
     'Platform transcription API kill switch (CONTRACT transcription-api §3). false = submit 503 transcricao_desativada.', false)
ON CONFLICT (key) DO NOTHING;
