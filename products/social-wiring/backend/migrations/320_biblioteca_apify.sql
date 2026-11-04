-- 320_biblioteca_apify.sql — Biblioteca de virais: Apify as the (transitional) ingestion source.
--
-- Owner decision 2026-11-04: until Meta verifies noc, public Instagram profiles are read through Apify
-- (apify/instagram-scraper). Business Discovery stays in the code behind setting `biblioteca_fonte`.
-- Contract: projects/core-studio-build/specs/apify-biblioteca-contract.md section 2.
--
--   1. cs_virais.video_url / video_url_em — the video CDN URL the scraper returned and when, so a
--      re-transcription within ~24 h needs no re-scrape (the URL expires; past that the job re-syncs).
--   2. cs_perfis_monitorados.status accepts 'sem_credencial' (no Apify token) and 'sem_orcamento'
--      (daily result cap reached) — visible states, never a silent skip.
--   3. cs_apify_uso — one row per billed scrape (results + USD when the response exposes it); the daily
--      per-org cap sums `resultados` of the UTC day. service_role only (worker-written).
-- FORWARD-ONLY, idempotent. MIGRATION FILE ONLY — not applied by this change.
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS video_url TEXT;
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS video_url_em TIMESTAMPTZ;

ALTER TABLE social_wiring.cs_perfis_monitorados DROP CONSTRAINT IF EXISTS cs_perfis_monitorados_status_check;
ALTER TABLE social_wiring.cs_perfis_monitorados ADD CONSTRAINT cs_perfis_monitorados_status_check
    CHECK (status IN ('aguardando', 'ativo', 'pausado', 'nao_encontrado', 'sem_conta', 'erro',
                      'sem_credencial', 'sem_orcamento'));

-- Viral inputs (owner decision 2026-11-04): e_viral = views floor AND er_views AND er_seguidores. Stored raw so
-- a future auto-detection can re-score without re-scraping. NULL = not computable (hidden likes / no views / no followers).
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS er_views NUMERIC;
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS er_seguidores NUMERIC;
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS seguidores_no_fetch BIGINT;

CREATE TABLE IF NOT EXISTS social_wiring.cs_apify_uso (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    perfil_id  UUID REFERENCES social_wiring.cs_perfis_monitorados (id) ON DELETE SET NULL,
    resultados INTEGER NOT NULL CHECK (resultados >= 0),
    usd        NUMERIC(14, 6),
    run_id     TEXT,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_apify_uso IS
    'Migration 320 - one row per Apify scrape (billed results); drives the per-org daily cap. usd NULL = not exposed by the run.';
CREATE INDEX IF NOT EXISTS cs_apify_uso_org_dia_idx ON social_wiring.cs_apify_uso (org_id, criado_em DESC);

ALTER TABLE social_wiring.cs_apify_uso ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_apify_uso_service_role" ON social_wiring.cs_apify_uso;
CREATE POLICY "cs_apify_uso_service_role"
    ON social_wiring.cs_apify_uso
    FOR ALL TO service_role USING (true) WITH CHECK (true);
-- Service-role only: usage rows are written by the worker; no end-user read path.
REVOKE ALL ON social_wiring.cs_apify_uso FROM anon, authenticated;
