-- ============================================================================
-- Migration 371 -- social_wiring: imovel_video_youtube -- the ONE published YouTube video of an imóvel
-- ============================================================================
-- WHY
-- ---
-- Project `julia-videos-prontos-youtube` (2026-11-27): when Julia publishes an imóvel's standard (horizontal) video on
-- YouTube, the property needs to know it -- other modules read it, later the public property page embeds it. Shorts
-- never go here. A user can also set / replace / clear it by hand, and a later backfill imports the URLs Vista already
-- holds (`origem = 'vista'`).
--
-- WHERE: NOT a column on `social_wiring.imoveis` -- that table is a Vista mirror and may hold ONLY Vista columns
-- (`imoveis_service._assert_so_vista`). Our own data keys to `imovel_registry (org_id, codigo_canonical)` (migration 063),
-- exactly like `imovel_notas` (315): a property leaves the Vista catalog when it is sold, and the row must survive that.
--
-- ONE ROW per (org, código): REPLACE semantics (owner: the newest wins). Every set / replace / clear also appends an
-- `imovel_historico` row (`video_youtube_definido` / `video_youtube_removido`, the previous URL in `valor_anterior`), so
-- the lifecycle is measurable without an extra `_eventos` table -- the action register is that table.
-- measurable: lifecycle events land in social_wiring.imovel_historico (video_youtube_definido / video_youtube_removido)
--
-- `youtube_url` is GENERATED from the id -- one derivation, never a second stored copy that can drift.
-- Written by the backend only (`app/services/imovel_video_youtube_service.py`); read through the API.
--
-- FORWARD-ONLY, IDEMPOTENT. Backward-compatible with the previous image (a new table + a widened CHECK).
-- ============================================================================

SET search_path = social_wiring, public;
SET lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS social_wiring.imovel_video_youtube (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid        NOT NULL,
    codigo           text        NOT NULL,
    youtube_video_id text        NOT NULL,
    youtube_url      text        GENERATED ALWAYS AS ('https://www.youtube.com/watch?v=' || youtube_video_id) STORED,
    upload_job_id    uuid        NULL,
    origem           text        NOT NULL,
    definido_por     uuid        NULL,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    atualizado_em    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT imovel_video_youtube_org_codigo_uq UNIQUE (org_id, codigo),
    -- A YouTube video id is 11 characters of [A-Za-z0-9_-]; the service validates first (422), this is the backstop.
    CONSTRAINT imovel_video_youtube_id_check CHECK (youtube_video_id ~ '^[A-Za-z0-9_-]{11}$'),
    CONSTRAINT imovel_video_youtube_origem_check CHECK (origem IN ('julia', 'manual', 'vista')),
    CONSTRAINT imovel_video_youtube_imovel_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical) ON DELETE CASCADE,
    CONSTRAINT imovel_video_youtube_upload_job_fk
        FOREIGN KEY (upload_job_id)
        REFERENCES social_wiring.upload_jobs (id) ON DELETE SET NULL
);

-- The FK column to upload_jobs gets its own index (ON DELETE SET NULL scans it); (org_id, codigo) is covered by the UNIQUE.
CREATE INDEX IF NOT EXISTS imovel_video_youtube_upload_job_idx
    ON social_wiring.imovel_video_youtube (upload_job_id) WHERE upload_job_id IS NOT NULL;

COMMENT ON TABLE social_wiring.imovel_video_youtube IS 'tier:org';

ALTER TABLE social_wiring.imovel_video_youtube ENABLE ROW LEVEL SECURITY;

-- Backend-mediated (GET/PUT/DELETE /api/imoveis/{codigo}/video-youtube): no browser-role grant or policy (a direct
-- PostgREST grant would be a browser-grant finding for no benefit). The service role reads and writes it, org-scoped.
DROP POLICY IF EXISTS "imovel_video_youtube_service_role" ON social_wiring.imovel_video_youtube;
CREATE POLICY "imovel_video_youtube_service_role"
    ON social_wiring.imovel_video_youtube
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON social_wiring.imovel_video_youtube FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON social_wiring.imovel_video_youtube TO service_role;

-- The action register learns the two video actions (349's inline CHECK is named imovel_historico_acao_check).
ALTER TABLE social_wiring.imovel_historico DROP CONSTRAINT IF EXISTS imovel_historico_acao_check;
ALTER TABLE social_wiring.imovel_historico ADD CONSTRAINT imovel_historico_acao_check CHECK (acao IN (
    'campo_atualizado', 'vista_prevaleceu', 'enviado_ao_vista', 'envio_vista_falhou',
    'aprovacao_pendente', 'aprovacao_decidida', 'video_youtube_definido', 'video_youtube_removido'));

RESET lock_timeout;
