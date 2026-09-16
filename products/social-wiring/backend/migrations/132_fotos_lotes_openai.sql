-- 132_fotos_lotes_openai.sql -- social_wiring: Econômico provider batches
--
-- Edição de Fotos W4 (plan §1 "Speed", §6; projects/edicao-fotos/PROJECT.md
-- C8). Resolves NOC-REMEDIATE[fotos-lotes-openai-table] from
-- 123_fotos_core.sql: the owner chose to build Econômico now, so it works the
-- moment a batch-capable image model is priced in the catalog.
--
-- 1. `fotos_lotes_openai` -- one row per OpenAI Batch API job. The engine
--    (`noctusai_lib.domain.photo_editing`, `OpenAIBatchRecord`) writes it
--    with the service role:
--      * `status` is the ENGINE lifecycle: preparando -> enviado ->
--        concluido | falhou. `preparando` = the row and the photo
--        transitions exist but the provider has not confirmed the submit
--        yet (a crashed/retried `fotos.submit_openai_batch` resumes it).
--      * `openai_status` mirrors the provider's own status string
--        (validating / in_progress / finalizing / completed / failed /
--        expired / cancelling / cancelled) -- free text on purpose: the
--        vendor owns that vocabulary.
--      * `itens` is the frozen list of what was sent, one object per photo:
--        {foto_id, edicao_id, custom_id, tentativas, prompt}. It correlates
--        results to photos AND counts automatic retries.
--      * `consultas` counts `fotos.poll_openai_batch` rounds (5/15/30 min).
-- 2. `fotos_fotos.openai_batch_id` (a bare TEXT pointer since 123) gets the
--    FK the 123 header promised, onto `fotos_lotes_openai.openai_batch_id`
--    (UNIQUE, nullable -- NULL while `preparando`). ON DELETE SET NULL: the
--    photo outlives the provider-batch bookkeeping.
--
-- No costs and no AI verdict live here, so the row is visible under the
-- same batch-visibility rule as the photos (creator / org admin tier /
-- platform admin via `fotos_lote_visivel`). Writes are service-role only.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. fotos_lotes_openai
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_lotes_openai (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    lote_id          UUID NOT NULL REFERENCES social_wiring.fotos_lotes (id) ON DELETE CASCADE,
    modelo_id        TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'preparando'
        CHECK (status IN ('preparando', 'enviado', 'concluido', 'falhou')),
    openai_batch_id  TEXT UNIQUE,
    openai_status    TEXT,
    input_file_id    TEXT,
    output_file_id   TEXT,
    error_file_id    TEXT,
    itens            JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(itens) = 'array'),
    consultas        INTEGER NOT NULL DEFAULT 0 CHECK (consultas >= 0),
    erro             TEXT,
    submetido_at     TIMESTAMPTZ,
    concluido_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A row the provider accepted always carries the provider id.
    CHECK (status IN ('preparando', 'falhou') OR openai_batch_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_fotos_lotes_openai_lote
    ON social_wiring.fotos_lotes_openai (lote_id, created_at);
CREATE INDEX IF NOT EXISTS ix_fotos_lotes_openai_org
    ON social_wiring.fotos_lotes_openai (org_id);
-- The queue/health view: provider batches still in flight.
CREATE INDEX IF NOT EXISTS ix_fotos_lotes_openai_abertos
    ON social_wiring.fotos_lotes_openai (status)
    WHERE status IN ('preparando', 'enviado');

ALTER TABLE social_wiring.fotos_lotes_openai ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_lotes_openai_select_visivel" ON social_wiring.fotos_lotes_openai
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(lote_id));

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_lotes_openai
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. fotos_fotos.openai_batch_id -> fotos_lotes_openai.openai_batch_id
-- ----------------------------------------------------------------------------

ALTER TABLE social_wiring.fotos_fotos
    ADD CONSTRAINT fotos_fotos_openai_batch_id_fkey
    FOREIGN KEY (openai_batch_id)
    REFERENCES social_wiring.fotos_lotes_openai (openai_batch_id)
    ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_fotos_fotos_openai_batch
    ON social_wiring.fotos_fotos (openai_batch_id)
    WHERE openai_batch_id IS NOT NULL;

COMMENT ON TABLE social_wiring.fotos_lotes_openai IS
    'Edição de Fotos Econômico: one row per OpenAI Batch API job (engine-written, service role).';
