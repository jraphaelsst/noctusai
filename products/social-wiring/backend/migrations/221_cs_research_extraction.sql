-- ============================================================================
-- Migration 221 · social_wiring: Minha Pesquisa wave 2 — Extrair + Assuntos
-- Virais: `cs_viral_topics`, `cs_extraction_jobs`, `cs_viral_topic_sources`,
-- `cs_extraction_post_runs`
-- ============================================================================
-- WHY
-- ---
-- Contract: projects/core-studio/specs/pesquisa-wave2-contract.md section 2.2.
-- Viral topics per marca (+ the posts behind them), user-facing extraction job
-- state (the queue row lives in social_wiring.jobs) and one row per
-- (job, tipo, post) so a post is never paid for twice.
-- "One active extraction per user" is enforced by a partial unique index, so
-- two concurrent submits cannot both pass.
--
-- CHECK enums mirror app/modules/media_creation/pesquisa_wave2_constants.py;
-- a test asserts they match.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'migration 221 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.cs_research_items') IS NULL THEN
    RAISE EXCEPTION 'migration 221 requires social_wiring.cs_research_items (migration 217) -- apply 217 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Viral topics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_viral_topics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id    UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    topic       TEXT NOT NULL CHECK (char_length(topic) BETWEEN 1 AND 255 AND topic = btrim(topic)),
    status      TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    origin      TEXT NOT NULL CHECK (origin IN ('manual', 'extraction')),
    total_plays BIGINT,
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_viral_topics IS
    'Migration 221 - Assuntos Virais, per marca. manual => approved with NULL total_plays; '
    'extraction => pending. total_plays = sum of source plays (NULLs skipped), recomputed by the service.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_viral_topics_marca_topic_uq
    ON social_wiring.cs_viral_topics (marca_id, lower(topic));

CREATE INDEX IF NOT EXISTS cs_viral_topics_marca_status_plays_idx
    ON social_wiring.cs_viral_topics (marca_id, status, total_plays DESC NULLS LAST);

-- ----------------------------------------------------------------------------
-- 2. Extraction jobs (user-facing state; queue row in social_wiring.jobs)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_extraction_jobs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id              UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    created_by            UUID NOT NULL,
    tipos                 TEXT[] NOT NULL
        CHECK (cardinality(tipos) BETWEEN 1 AND 2 AND tipos <@ ARRAY['pesquisa', 'assuntos_virais']::text[]),
    status                TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'completed_with_errors', 'failed', 'cancelled')),
    cancel_requested      BOOLEAN NOT NULL DEFAULT false,
    posts                 JSONB NOT NULL,
    total_tarefas         INTEGER NOT NULL DEFAULT 0,
    tarefas_processadas   INTEGER NOT NULL DEFAULT 0,
    tarefas_com_erro      INTEGER NOT NULL DEFAULT 0,
    step                  TEXT,
    itens_salvos          INTEGER NOT NULL DEFAULT 0,
    itens_ignorados       INTEGER NOT NULL DEFAULT 0,
    itens_descartados     INTEGER NOT NULL DEFAULT 0,
    assuntos_salvos       INTEGER NOT NULL DEFAULT 0,
    assuntos_ignorados    INTEGER NOT NULL DEFAULT 0,
    ja_extraidos_pulados  INTEGER NOT NULL DEFAULT 0,
    erro                  TEXT,
    queue_job_id          UUID,
    started_at            TIMESTAMPTZ,
    finished_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_extraction_jobs IS
    'Migration 221 - user-facing Pesquisa extraction job state; queue row lives in social_wiring.jobs '
    '(queue_job_id). One active (queued/running) job per user, enforced by cs_extraction_jobs_one_active_per_user_uq.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_extraction_jobs_one_active_per_user_uq
    ON social_wiring.cs_extraction_jobs (created_by)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS cs_extraction_jobs_org_created_idx
    ON social_wiring.cs_extraction_jobs (org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS cs_extraction_jobs_marca_created_idx
    ON social_wiring.cs_extraction_jobs (marca_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 3. Viral topic sources (the posts behind a topic)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_viral_topic_sources (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    topic_id      UUID NOT NULL REFERENCES social_wiring.cs_viral_topics (id) ON DELETE CASCADE,
    source_kind   TEXT NOT NULL CHECK (source_kind IN ('instagram_media', 'youtube_video', 'mc_post')),
    account_id    UUID,
    source_id     TEXT NOT NULL,
    url           TEXT,
    thumbnail_url TEXT,
    published_at  TIMESTAMPTZ,
    plays         BIGINT,
    likes         BIGINT,
    comments      BIGINT,
    excerpt       TEXT,
    extracao_id   UUID REFERENCES social_wiring.cs_extraction_jobs (id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_viral_topic_sources IS
    'Migration 221 - posts behind a viral topic (ver virais modal); metrics are a snapshot at extraction time.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_viral_topic_sources_post_uq
    ON social_wiring.cs_viral_topic_sources (topic_id, source_kind, coalesce(account_id::text, ''), source_id);

-- ----------------------------------------------------------------------------
-- 4. Per (job, tipo, post) runs: "Já extraído" badge + no double LLM spend
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_extraction_post_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id        UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    extracao_id     UUID NOT NULL REFERENCES social_wiring.cs_extraction_jobs (id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('pesquisa', 'assuntos_virais')),
    source_kind     TEXT NOT NULL CHECK (source_kind IN ('instagram_media', 'youtube_video', 'mc_post')),
    account_id      UUID,
    source_id       TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('done', 'failed', 'skipped')),
    motivo          TEXT CHECK (motivo IS NULL OR motivo IN ('sem_texto', 'llm_erro', 'cancelado')),
    itens_salvos    INTEGER NOT NULL DEFAULT 0,
    assuntos_salvos INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_extraction_post_runs IS
    'Migration 221 - one row per (job, tipo, post); drives the "Ja extraido" badge and resume-after-retry.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_extraction_post_runs_post_uq
    ON social_wiring.cs_extraction_post_runs (extracao_id, tipo, source_kind, coalesce(account_id::text, ''), source_id);

CREATE INDEX IF NOT EXISTS cs_extraction_post_runs_done_idx
    ON social_wiring.cs_extraction_post_runs (marca_id, tipo, source_kind, source_id)
    WHERE status = 'done';

-- ----------------------------------------------------------------------------
-- 5. updated_at triggers
-- ----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS set_updated_at_cs_viral_topics ON social_wiring.cs_viral_topics;
CREATE TRIGGER set_updated_at_cs_viral_topics
    BEFORE UPDATE ON social_wiring.cs_viral_topics
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_extraction_jobs ON social_wiring.cs_extraction_jobs;
CREATE TRIGGER set_updated_at_cs_extraction_jobs
    BEFORE UPDATE ON social_wiring.cs_extraction_jobs
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

-- ----------------------------------------------------------------------------
-- 6. RLS (same shape as 217: own-org authenticated, service_role ALL)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_viral_topics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_viral_topics_select_own_org" ON social_wiring.cs_viral_topics;
CREATE POLICY "cs_viral_topics_select_own_org"
    ON social_wiring.cs_viral_topics
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_viral_topics_write_own_org" ON social_wiring.cs_viral_topics;
CREATE POLICY "cs_viral_topics_write_own_org"
    ON social_wiring.cs_viral_topics
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_viral_topics_service_role" ON social_wiring.cs_viral_topics;
CREATE POLICY "cs_viral_topics_service_role"
    ON social_wiring.cs_viral_topics
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_viral_topic_sources ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_viral_topic_sources_select_own_org" ON social_wiring.cs_viral_topic_sources;
CREATE POLICY "cs_viral_topic_sources_select_own_org"
    ON social_wiring.cs_viral_topic_sources
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_viral_topic_sources_write_own_org" ON social_wiring.cs_viral_topic_sources;
CREATE POLICY "cs_viral_topic_sources_write_own_org"
    ON social_wiring.cs_viral_topic_sources
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_viral_topic_sources_service_role" ON social_wiring.cs_viral_topic_sources;
CREATE POLICY "cs_viral_topic_sources_service_role"
    ON social_wiring.cs_viral_topic_sources
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_extraction_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_extraction_jobs_select_own_org" ON social_wiring.cs_extraction_jobs;
CREATE POLICY "cs_extraction_jobs_select_own_org"
    ON social_wiring.cs_extraction_jobs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extraction_jobs_write_own_org" ON social_wiring.cs_extraction_jobs;
CREATE POLICY "cs_extraction_jobs_write_own_org"
    ON social_wiring.cs_extraction_jobs
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extraction_jobs_service_role" ON social_wiring.cs_extraction_jobs;
CREATE POLICY "cs_extraction_jobs_service_role"
    ON social_wiring.cs_extraction_jobs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_extraction_post_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_extraction_post_runs_select_own_org" ON social_wiring.cs_extraction_post_runs;
CREATE POLICY "cs_extraction_post_runs_select_own_org"
    ON social_wiring.cs_extraction_post_runs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extraction_post_runs_write_own_org" ON social_wiring.cs_extraction_post_runs;
CREATE POLICY "cs_extraction_post_runs_write_own_org"
    ON social_wiring.cs_extraction_post_runs
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extraction_post_runs_service_role" ON social_wiring.cs_extraction_post_runs;
CREATE POLICY "cs_extraction_post_runs_service_role"
    ON social_wiring.cs_extraction_post_runs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
