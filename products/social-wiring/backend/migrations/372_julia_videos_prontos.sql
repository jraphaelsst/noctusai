-- ============================================================================
-- Migration 372 · social_wiring: Julia "Vídeos Prontos" -- the editor's WhatsApp group as an entry point to the
-- EXISTING YouTube upload (project julia-videos-prontos-youtube, slice S2)
-- ============================================================================
-- WHY
-- ---
-- The video editor posts, in the org's WhatsApp group "Vídeos Prontos", a property code and the Drive folder with the
-- finished videos (code first, link first, or both in one message). Julia pairs them per sender, waits a short
-- debounce window and hands the folder to the existing `UploadService.queue_drive_folder_upload` +
-- `run_upload_job` (no upload / classification logic is duplicated: one `upload_jobs` row per video, the worker
-- decides the orientation).
--
--   1. `julia_videos_prontos_config` -- per org: which connection + group chat is the "Vídeos Prontos" group, the
--      privacy of the uploads, and the on/off switch. `ativo` defaults to FALSE and NO row is seeded: an org is
--      switched on by hand (the SQL is in the slice's delivery note).
--   2. `julia_videos_prontos_submissoes` -- one row per (code, folder) submission: the pairing slot while it waits
--      (`aguardando`, `versao` + `due_at` = the debounce), then its outcome. `status` is a CHECK enum:
--        aguardando -> processando -> concluido | parcial | falhou | no_videos_found ; aguardando -> incompleto
--        parcial | falhou -> processando (the ONE automatic retry, or a manual one)
--      Two partial UNIQUE indexes:
--        * one OPEN slot per (org, chat, sender) -- the pairing invariant under concurrent webhook deliveries;
--        * the duplicate-upload guard: one (org, code, folder) pair in processando / concluido / parcial. A pair
--          that ended `no_videos_found` / `falhou` / `incompleto` may be resubmitted. `aguardando` is deliberately
--          NOT in the guard: a slot fills field by field and must never fail its own merge; the handler refuses a
--          duplicate before it claims the slot and this index is the race backstop.
--   3. The status history: the seed transition-log primitive (`julia_video_pronto_events` + RPCs), rendered below --
--      every status change is one row-locked compare-and-set that writes state + event in ONE transaction
--      (EOA; never a hand-written history table). The Julia event bus (`julia_eventos`, `video_pronto_*`) carries the
--      same transitions for the timeline; the transition log is the measurable source.
--
-- Records -> metrics: submissions per org / day; time from first message to processing (created_at -> the
-- `upload_iniciado` event); outcome mix (concluido / parcial / falhou / no_videos_found / incompleto) per org and per
-- sender; automatic-retry recovery rate (parcial|falhou -> concluido after `tentativas_retry` = 1); videos per
-- submission (batch_id -> upload_jobs).
--
-- tier:org on both tables (service-role only: the API reads/writes through the service-role client after the
-- session's org is resolved; `authenticated` / `anon` get nothing).
-- Backward compatible with the previous image (N-1): two NEW tables and new functions, nothing existing altered.
-- FORWARD-ONLY, IDEMPOTENT. NOT applied by the author.
-- GuardProbes: _SW_372_PROBES in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.whatsapp_connections') IS NULL THEN
    RAISE EXCEPTION 'Migration 372 requires social_wiring.whatsapp_connections (migration 004) -- apply it first';
  END IF;
END
$guard$;

SET LOCAL lock_timeout = '5s';

-- ----------------------------------------------------------------------------
-- 1. julia_videos_prontos_config (per org; off by default, nothing seeded)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_videos_prontos_config (
    org_id          UUID PRIMARY KEY REFERENCES public.organizations (id) ON DELETE CASCADE,
    connection_id   UUID NOT NULL REFERENCES social_wiring.whatsapp_connections (id) ON DELETE CASCADE,
    -- the group JID, e.g. 120363369180055435@g.us
    chat_id         TEXT NOT NULL CONSTRAINT julia_videos_prontos_config_chat_grupo CHECK (chat_id LIKE '%@g.us'),
    privacy_status  TEXT NOT NULL DEFAULT 'private'
                        CONSTRAINT julia_videos_prontos_config_privacy_valida CHECK (privacy_status IN ('private', 'unlisted', 'public')),
    ativo           BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- the webhook's per-message lookup: is this (connection, chat) an active Vídeos Prontos group?
CREATE INDEX IF NOT EXISTS julia_videos_prontos_config_conexao_idx
    ON social_wiring.julia_videos_prontos_config (connection_id, chat_id) WHERE ativo;

-- ----------------------------------------------------------------------------
-- 2. julia_videos_prontos_submissoes (the state row; its history is the transition log below)
-- measurable[julia_videos_prontos_submissoes]: status history = the seed transition log julia_video_pronto_events rendered in section 4 (FK added by ALTER TABLE; the keeper learns that shape in this same branch)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_videos_prontos_submissoes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    connection_id           UUID REFERENCES social_wiring.whatsapp_connections (id) ON DELETE SET NULL,
    chat_id                 TEXT NOT NULL,
    -- the sender inside the group (WAHA `participant`), never the group itself
    remetente               TEXT NOT NULL,
    -- the property code, upper-cased (PRODUCT_CODE_SCAN_PATTERN); NULL until a message brings it
    codigo                  TEXT,
    drive_folder_url        TEXT,
    drive_folder_id         TEXT,
    exclusividade           BOOLEAN NOT NULL DEFAULT false,
    status                  TEXT NOT NULL DEFAULT 'aguardando'
                                CONSTRAINT julia_videos_prontos_submissoes_status_valido CHECK (status IN (
                                    'aguardando', 'incompleto', 'processando', 'concluido', 'parcial', 'falhou',
                                    'no_videos_found')),
    -- the debounce: every relevant message bumps `versao` and pushes `due_at`; only the job of the current version runs
    versao                  INTEGER NOT NULL DEFAULT 1,
    due_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- the WhatsApp message ids that built the slot (a redelivered message is a no-op)
    ids_mensagens           TEXT[] NOT NULL DEFAULT '{}',
    -- the upload batch (`upload_jobs.batch_id`); NULL until the folder fan-out queued it
    batch_id                UUID,
    tentativas_retry        INTEGER NOT NULL DEFAULT 0,
    -- closed reason code of the last failure (`motivo`) + its short human text (`erro`)
    motivo                  TEXT,
    erro                    TEXT,
    -- the standard (16:9) video written to the property's YouTube field, once (S1 contract)
    video_imovel_youtube_id TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- one OPEN pairing slot per sender in a group
CREATE UNIQUE INDEX IF NOT EXISTS julia_videos_prontos_submissoes_aberta_uq
    ON social_wiring.julia_videos_prontos_submissoes (org_id, chat_id, remetente) WHERE status = 'aguardando';
-- the duplicate-upload guard: a pair being uploaded or already uploaded is never uploaded again
CREATE UNIQUE INDEX IF NOT EXISTS julia_videos_prontos_submissoes_par_uq
    ON social_wiring.julia_videos_prontos_submissoes (org_id, codigo, drive_folder_id)
    WHERE status IN ('processando', 'concluido', 'parcial') AND codigo IS NOT NULL AND drive_folder_id IS NOT NULL;
-- the list endpoint (newest first, per org) and the batch -> submission lookup
CREATE INDEX IF NOT EXISTS julia_videos_prontos_submissoes_org_idx
    ON social_wiring.julia_videos_prontos_submissoes (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS julia_videos_prontos_submissoes_batch_idx
    ON social_wiring.julia_videos_prontos_submissoes (batch_id) WHERE batch_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. RLS + grants (service-role only), tier
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.julia_videos_prontos_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "julia_videos_prontos_config_service_role" ON social_wiring.julia_videos_prontos_config;
CREATE POLICY "julia_videos_prontos_config_service_role" ON social_wiring.julia_videos_prontos_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.julia_videos_prontos_config FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE social_wiring.julia_videos_prontos_config TO service_role;
COMMENT ON TABLE social_wiring.julia_videos_prontos_config IS 'tier:org';

ALTER TABLE social_wiring.julia_videos_prontos_submissoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "julia_videos_prontos_submissoes_service_role" ON social_wiring.julia_videos_prontos_submissoes;
CREATE POLICY "julia_videos_prontos_submissoes_service_role" ON social_wiring.julia_videos_prontos_submissoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.julia_videos_prontos_submissoes FROM PUBLIC, anon, authenticated, service_role;
-- no DELETE: a submission carries its transition history (erasure goes through julia_video_pronto_erase_subject)
GRANT SELECT, INSERT, UPDATE ON TABLE social_wiring.julia_videos_prontos_submissoes TO service_role;
COMMENT ON TABLE social_wiring.julia_videos_prontos_submissoes IS 'tier:org';

-- ============================================================================
-- 4. The status history: the seed transition_log primitive (rendered by noctusai_lib.domain.transition_log; never
--    hand-edit the render -- re-render)
-- ============================================================================
-- Transition log -- generated by noctusai_lib.domain.transition_log.sql (do not hand-edit)

-- transition-log-config: {"actor_kinds":["user","agent","system"],"aggregate":"julia_video_pronto","foreign_key":true,"key":[{"name":"entity_id","state_column":"id","type":"uuid"}],"schema":"social_wiring","state_column":"status","state_created_at_column":"created_at","state_org_column":"org_id","state_table":"julia_videos_prontos_submissoes","state_type":"text","state_updated_at_column":"updated_at"}

SET search_path = social_wiring, public;

-- The schema's erasure log (shared by every transition-log aggregate): who erased which subject's history, when,
-- why, how many rows. Ids and counts only -- never the erased payload. Append-only, no carve-out.
CREATE TABLE IF NOT EXISTS social_wiring.transition_log_erasures (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    aggregate       TEXT NOT NULL,
    subject         JSONB NOT NULL,
    events_deleted  INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    actor_id        UUID,
    erased_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT transition_log_erasures_reason_present CHECK (btrim(reason) <> '')
);
CREATE INDEX IF NOT EXISTS idx_transition_log_erasures_org ON social_wiring.transition_log_erasures (org_id, aggregate, erased_at);
ALTER TABLE social_wiring.transition_log_erasures ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "transition_log_erasures_select_own_org" ON social_wiring.transition_log_erasures;
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.transition_log_erasures;
CREATE POLICY "service_role_bypass" ON social_wiring.transition_log_erasures FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.transition_log_erasures FROM PUBLIC, anon, authenticated;
GRANT ALL ON social_wiring.transition_log_erasures TO service_role;
COMMENT ON TABLE social_wiring.transition_log_erasures IS 'tier:org';
CREATE OR REPLACE FUNCTION social_wiring.transition_log_erasures_append_only() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'transition_log_erasures is append-only (% refused)', TG_OP USING ERRCODE = 'TL001';
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.transition_log_erasures_append_only() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS transition_log_erasures_no_update_delete ON social_wiring.transition_log_erasures;
CREATE TRIGGER transition_log_erasures_no_update_delete BEFORE UPDATE OR DELETE ON social_wiring.transition_log_erasures
    FOR EACH ROW EXECUTE FUNCTION social_wiring.transition_log_erasures_append_only();
DROP TRIGGER IF EXISTS transition_log_erasures_no_truncate ON social_wiring.transition_log_erasures;
CREATE TRIGGER transition_log_erasures_no_truncate BEFORE TRUNCATE ON social_wiring.transition_log_erasures
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.transition_log_erasures_append_only();

-- Events of `julia_video_pronto` (state truth: social_wiring.julia_videos_prontos_submissoes.status). Append-only; seq 1 is always the creation event.
CREATE TABLE IF NOT EXISTS social_wiring.julia_video_pronto_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    entity_id       UUID NOT NULL,
    seq             INTEGER NOT NULL,
    from_state      TEXT,
    to_state        TEXT,
    event_type      TEXT NOT NULL,
    data            JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_id        UUID,
    actor_kind      TEXT NOT NULL,
    correlation_id  UUID,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT julia_video_pronto_events_seq_positive CHECK (seq >= 1),
    CONSTRAINT julia_video_pronto_events_creation_first CHECK ((seq = 1) = (event_type IN ('created', 'imported_initial_state')) AND (event_type NOT IN ('created', 'imported_initial_state') OR from_state IS NULL)),
    CONSTRAINT julia_video_pronto_events_event_type_shape CHECK (event_type ~ '^[a-z][a-z0-9_.]*$'),
    CONSTRAINT julia_video_pronto_events_data_object CHECK (jsonb_typeof(data) = 'object'),
    CONSTRAINT julia_video_pronto_events_actor_kind CHECK (actor_kind IN ('user', 'agent', 'system', 'synthetic'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_julia_video_pronto_events_entity_seq ON social_wiring.julia_video_pronto_events (entity_id, seq);
CREATE INDEX IF NOT EXISTS idx_julia_video_pronto_events_org_entity_seq ON social_wiring.julia_video_pronto_events (org_id, entity_id, seq);
CREATE INDEX IF NOT EXISTS idx_julia_video_pronto_events_correlation ON social_wiring.julia_video_pronto_events (org_id, correlation_id) WHERE correlation_id IS NOT NULL;
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'julia_video_pronto_events_entity_fk' AND conrelid = 'social_wiring.julia_video_pronto_events'::regclass) THEN
        ALTER TABLE social_wiring.julia_video_pronto_events ADD CONSTRAINT julia_video_pronto_events_entity_fk FOREIGN KEY (entity_id)
            REFERENCES social_wiring.julia_videos_prontos_submissoes (id) ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;
    END IF;
END
$do$;
ALTER TABLE social_wiring.julia_video_pronto_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "julia_video_pronto_events_select_own_org" ON social_wiring.julia_video_pronto_events;
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.julia_video_pronto_events;
CREATE POLICY "service_role_bypass" ON social_wiring.julia_video_pronto_events FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.julia_video_pronto_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON social_wiring.julia_video_pronto_events TO service_role;
COMMENT ON TABLE social_wiring.julia_video_pronto_events IS 'tier:org';

-- Immutability: UPDATE always refused, DELETE only under noctus_tl.erase_julia_video_pronto (set by julia_video_pronto_erase_subject alone).
-- guc-carveout-guard: rendered by noctusai_lib.domain.sql_templates.guc_carveout_guard_sql
CREATE OR REPLACE FUNCTION social_wiring.guard_julia_video_pronto_events_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = social_wiring, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('noctus_tl.erase_julia_video_pronto', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'julia_video_pronto_events is append-only' USING ERRCODE = 'TL001';
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.guard_julia_video_pronto_events_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.guard_julia_video_pronto_events_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_julia_video_pronto_events_append_only ON social_wiring.julia_video_pronto_events;
CREATE TRIGGER guard_julia_video_pronto_events_append_only
    BEFORE UPDATE OR DELETE ON social_wiring.julia_video_pronto_events
    FOR EACH ROW EXECUTE FUNCTION social_wiring.guard_julia_video_pronto_events_append_only();

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_events_refuse_truncate() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'julia_video_pronto_events is append-only (TRUNCATE refused)' USING ERRCODE = 'TL001';
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_events_refuse_truncate() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS julia_video_pronto_events_no_truncate ON social_wiring.julia_video_pronto_events;
CREATE TRIGGER julia_video_pronto_events_no_truncate BEFORE TRUNCATE ON social_wiring.julia_video_pronto_events
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.julia_video_pronto_events_refuse_truncate();

-- Row-locked RPCs of `julia_video_pronto`: lock the state row, compare-and-set, write state + event in ONE transaction.

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_create(p_org UUID, p_row JSONB, p_data JSONB DEFAULT '{}'::jsonb, p_actor_id UUID DEFAULT NULL, p_actor_kind TEXT DEFAULT 'user', p_correlation_id UUID DEFAULT NULL, p_event_id UUID DEFAULT NULL, p_occurred_at TIMESTAMPTZ DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
DECLARE
    v_row  JSONB;
    v_cols TEXT;
    v_ins  JSONB;
    v_key  JSONB;
    v_prev social_wiring.julia_video_pronto_events%ROWTYPE;
    v_ev   social_wiring.julia_video_pronto_events%ROWTYPE;
BEGIN
    IF p_row IS NULL OR jsonb_typeof(p_row) <> 'object' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_row');
    END IF;
    p_data := COALESCE(p_data, '{}'::jsonb);
    IF jsonb_typeof(p_data) <> 'object' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_data');
    END IF;
    IF p_actor_kind IS NULL OR p_actor_kind <> ALL (ARRAY['user', 'agent', 'system']::text[]) THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_actor_kind');
    END IF;
    IF p_event_id IS NOT NULL THEN
        SELECT * INTO v_prev FROM social_wiring.julia_video_pronto_events WHERE id = p_event_id;
        IF FOUND THEN
            IF v_prev.org_id = p_org AND v_prev.event_type = 'created' THEN
                RETURN jsonb_build_object('status', 'replayed', 'event', to_jsonb(v_prev));
            END IF;
            RETURN jsonb_build_object('status', 'refused', 'code', 'idempotency_conflict');
        END IF;
    END IF;
    v_row := p_row || jsonb_build_object('org_id', p_org);
    SELECT string_agg(quote_ident(k), ', ') INTO v_cols FROM jsonb_object_keys(v_row) AS k;
    BEGIN
        EXECUTE format('INSERT INTO %I.%I AS x (%s) SELECT %s FROM jsonb_populate_record(NULL::%I.%I, $1) RETURNING to_jsonb(x.*)',
                       'social_wiring', 'julia_videos_prontos_submissoes', v_cols, v_cols, 'social_wiring', 'julia_videos_prontos_submissoes')
            INTO v_ins USING v_row;
        v_key := jsonb_build_object('entity_id', v_ins->'id');
        INSERT INTO social_wiring.julia_video_pronto_events (id, org_id, entity_id, seq, from_state, to_state, event_type, data, actor_id, actor_kind, correlation_id, occurred_at)
        VALUES (COALESCE(p_event_id, gen_random_uuid()), p_org, (v_key->>'entity_id')::uuid, 1, NULL, (v_ins->>'status')::text, 'created', p_data, p_actor_id, p_actor_kind, p_correlation_id, COALESCE(p_occurred_at, now())) RETURNING * INTO v_ev;
    EXCEPTION
        WHEN unique_violation THEN
            IF p_event_id IS NOT NULL THEN
                SELECT * INTO v_prev FROM social_wiring.julia_video_pronto_events WHERE id = p_event_id;
                IF FOUND AND v_prev.org_id = p_org AND v_prev.event_type = 'created' THEN
                    RETURN jsonb_build_object('status', 'replayed', 'event', to_jsonb(v_prev));
                END IF;
            END IF;
            RETURN jsonb_build_object('status', 'refused', 'code', 'duplicate', 'detail', SQLERRM);
        WHEN undefined_column OR not_null_violation OR check_violation OR foreign_key_violation
             OR invalid_text_representation OR datatype_mismatch OR invalid_datetime_format THEN
            RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_row', 'detail', SQLERRM);
    END;
    RETURN jsonb_build_object('status', 'ok', 'event', to_jsonb(v_ev));
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_create(UUID, JSONB, JSONB, UUID, TEXT, UUID, UUID, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.julia_video_pronto_create(UUID, JSONB, JSONB, UUID, TEXT, UUID, UUID, TIMESTAMPTZ) TO service_role;

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_record_created(p_org UUID, p_key JSONB, p_data JSONB DEFAULT '{}'::jsonb, p_actor_id UUID DEFAULT NULL, p_actor_kind TEXT DEFAULT 'user', p_correlation_id UUID DEFAULT NULL, p_event_id UUID DEFAULT NULL, p_occurred_at TIMESTAMPTZ DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
DECLARE
    v_cur     text;
    v_created TIMESTAMPTZ;
    v_seq     INTEGER;
    v_prev    social_wiring.julia_video_pronto_events%ROWTYPE;
    v_ev      social_wiring.julia_video_pronto_events%ROWTYPE;
BEGIN
    IF p_key IS NULL OR jsonb_typeof(p_key) <> 'object' OR (p_key->>'entity_id') IS NULL THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_key');
    END IF;
    p_data := COALESCE(p_data, '{}'::jsonb);
    IF jsonb_typeof(p_data) <> 'object' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_data');
    END IF;
    IF p_actor_kind IS NULL OR p_actor_kind <> ALL (ARRAY['user', 'agent', 'system']::text[]) THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_actor_kind');
    END IF;
    SELECT s.status, s.created_at INTO v_cur, v_created FROM social_wiring.julia_videos_prontos_submissoes s
        WHERE s.id = (p_key->>'entity_id')::uuid AND s.org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'not_found');
    END IF;
    IF p_event_id IS NOT NULL THEN
        SELECT * INTO v_prev FROM social_wiring.julia_video_pronto_events WHERE id = p_event_id;
        IF FOUND THEN
            IF v_prev.org_id = p_org AND v_prev.entity_id = (p_key->>'entity_id')::uuid AND v_prev.event_type = 'created' THEN
                RETURN jsonb_build_object('status', 'replayed', 'event', to_jsonb(v_prev));
            END IF;
            RETURN jsonb_build_object('status', 'refused', 'code', 'idempotency_conflict');
        END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM social_wiring.julia_video_pronto_events e WHERE e.entity_id = (p_key->>'entity_id')::uuid) THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'history_exists');
    END IF;
    INSERT INTO social_wiring.julia_video_pronto_events (id, org_id, entity_id, seq, from_state, to_state, event_type, data, actor_id, actor_kind, correlation_id, occurred_at)
        VALUES (COALESCE(p_event_id, gen_random_uuid()), p_org, (p_key->>'entity_id')::uuid, 1, NULL, v_cur, 'created', p_data, p_actor_id, p_actor_kind, p_correlation_id, COALESCE(p_occurred_at, now())) RETURNING * INTO v_ev;
    RETURN jsonb_build_object('status', 'ok', 'event', to_jsonb(v_ev));
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_record_created(UUID, JSONB, JSONB, UUID, TEXT, UUID, UUID, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.julia_video_pronto_record_created(UUID, JSONB, JSONB, UUID, TEXT, UUID, UUID, TIMESTAMPTZ) TO service_role;

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_transition(p_org UUID, p_key JSONB, p_from text, p_to text, p_event_type TEXT DEFAULT 'transitioned', p_data JSONB DEFAULT '{}'::jsonb, p_actor_id UUID DEFAULT NULL, p_actor_kind TEXT DEFAULT 'user', p_correlation_id UUID DEFAULT NULL, p_event_id UUID DEFAULT NULL, p_occurred_at TIMESTAMPTZ DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
DECLARE
    v_cur     text;
    v_created TIMESTAMPTZ;
    v_seq     INTEGER;
    v_prev    social_wiring.julia_video_pronto_events%ROWTYPE;
    v_ev      social_wiring.julia_video_pronto_events%ROWTYPE;
BEGIN
    IF p_key IS NULL OR jsonb_typeof(p_key) <> 'object' OR (p_key->>'entity_id') IS NULL THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_key');
    END IF;
    p_data := COALESCE(p_data, '{}'::jsonb);
    IF jsonb_typeof(p_data) <> 'object' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_data');
    END IF;
    IF p_actor_kind IS NULL OR p_actor_kind <> ALL (ARRAY['user', 'agent', 'system']::text[]) THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_actor_kind');
    END IF;
    IF p_event_type IS NULL OR p_event_type !~ '^[a-z][a-z0-9_.]*$' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_event_type');
    END IF;
    IF p_event_type IN ('created', 'imported_initial_state') THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'reserved_event_type');
    END IF;
    SELECT s.status, s.created_at INTO v_cur, v_created FROM social_wiring.julia_videos_prontos_submissoes s
        WHERE s.id = (p_key->>'entity_id')::uuid AND s.org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'not_found');
    END IF;
    IF p_event_id IS NOT NULL THEN
        SELECT * INTO v_prev FROM social_wiring.julia_video_pronto_events WHERE id = p_event_id;
        IF FOUND THEN
            IF v_prev.org_id = p_org AND v_prev.entity_id = (p_key->>'entity_id')::uuid AND v_prev.event_type = p_event_type AND v_prev.to_state IS NOT DISTINCT FROM p_to THEN
                RETURN jsonb_build_object('status', 'replayed', 'event', to_jsonb(v_prev));
            END IF;
            RETURN jsonb_build_object('status', 'refused', 'code', 'idempotency_conflict');
        END IF;
    END IF;
    IF v_cur IS DISTINCT FROM p_from THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'stale_state', 'current_state', v_cur);
    END IF;
    SELECT COALESCE(max(e.seq), 0) INTO v_seq FROM social_wiring.julia_video_pronto_events e WHERE e.entity_id = (p_key->>'entity_id')::uuid;
    IF v_seq = 0 THEN
        -- No history yet (an entity older than its log): its initial state becomes a synthetic seq 1 first.
        INSERT INTO social_wiring.julia_video_pronto_events (id, org_id, entity_id, seq, from_state, to_state, event_type, data, actor_id, actor_kind, correlation_id, occurred_at)
        VALUES (gen_random_uuid(), p_org, (p_key->>'entity_id')::uuid, 1, NULL, v_cur, 'imported_initial_state', jsonb_build_object('synthetic', true, 'source', 'lazy_first_transition'), NULL, 'synthetic', p_correlation_id, COALESCE(v_created, now()));
        v_seq := 1;
    END IF;
    UPDATE social_wiring.julia_videos_prontos_submissoes s SET status = p_to, updated_at = now() WHERE s.id = (p_key->>'entity_id')::uuid AND s.org_id = p_org;
    INSERT INTO social_wiring.julia_video_pronto_events (id, org_id, entity_id, seq, from_state, to_state, event_type, data, actor_id, actor_kind, correlation_id, occurred_at)
        VALUES (COALESCE(p_event_id, gen_random_uuid()), p_org, (p_key->>'entity_id')::uuid, v_seq + 1, v_cur, p_to, p_event_type, p_data, p_actor_id, p_actor_kind, p_correlation_id, COALESCE(p_occurred_at, now())) RETURNING * INTO v_ev;
    RETURN jsonb_build_object('status', 'ok', 'event', to_jsonb(v_ev));
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_transition(UUID, JSONB, text, text, TEXT, JSONB, UUID, TEXT, UUID, UUID, TIMESTAMPTZ) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.julia_video_pronto_transition(UUID, JSONB, text, text, TEXT, JSONB, UUID, TEXT, UUID, UUID, TIMESTAMPTZ) TO service_role;

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_history(p_org UUID, p_key JSONB) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
BEGIN
    IF p_key IS NULL OR jsonb_typeof(p_key) <> 'object' OR (p_key->>'entity_id') IS NULL THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_key');
    END IF;
    RETURN jsonb_build_object('status', 'ok', 'events', COALESCE(
        (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.seq) FROM social_wiring.julia_video_pronto_events e WHERE e.org_id = p_org AND e.entity_id = (p_key->>'entity_id')::uuid),
        '[]'::jsonb));
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_history(UUID, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.julia_video_pronto_history(UUID, JSONB) TO service_role;

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_erase_subject(p_org UUID, p_subject JSONB, p_reason TEXT, p_actor_id UUID DEFAULT NULL) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
DECLARE
    v_n INTEGER;
BEGIN
    IF p_org IS NULL OR p_subject IS NULL OR jsonb_typeof(p_subject) <> 'object' OR NOT (p_subject ?| ARRAY['entity_id']::text[])
       OR EXISTS (SELECT 1 FROM jsonb_each(p_subject) j WHERE j.key <> ALL (ARRAY['entity_id']::text[]) OR jsonb_typeof(j.value) = 'null') THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_key');
    END IF;
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'invalid_reason');
    END IF;
    -- The ONE gated delete (LGPD erasure, owner decision 2026-11-07): the flag is transaction-local and is
    -- dropped again before anything else runs, error or not.
    PERFORM set_config('noctus_tl.erase_julia_video_pronto', 'on', true);
    BEGIN
        DELETE FROM social_wiring.julia_video_pronto_events e WHERE e.org_id = p_org AND (NOT (p_subject ? 'entity_id') OR e.entity_id = (p_subject->>'entity_id')::uuid);
        GET DIAGNOSTICS v_n = ROW_COUNT;
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('noctus_tl.erase_julia_video_pronto', 'off', true);
        RAISE;
    END;
    PERFORM set_config('noctus_tl.erase_julia_video_pronto', 'off', true);
    INSERT INTO social_wiring.transition_log_erasures (org_id, aggregate, subject, events_deleted, reason, actor_id)
        VALUES (p_org, 'julia_video_pronto', p_subject, v_n, p_reason, p_actor_id);
    RETURN jsonb_build_object('status', 'ok', 'deleted', v_n);
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_erase_subject(UUID, JSONB, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.julia_video_pronto_erase_subject(UUID, JSONB, TEXT, UUID) TO service_role;

CREATE OR REPLACE FUNCTION social_wiring.julia_video_pronto_backfill_initial_state(p_org UUID DEFAULT NULL) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, social_wiring, pg_temp
AS $fn$
DECLARE
    v_n INTEGER;
BEGIN
    INSERT INTO social_wiring.julia_video_pronto_events (org_id, entity_id, seq, from_state, to_state, event_type, data, actor_kind, occurred_at)
    SELECT s.org_id, s.id, 1, NULL, s.status, 'imported_initial_state',
           jsonb_build_object('synthetic', true, 'source', 'transition_log_backfill'), 'synthetic', COALESCE(s.created_at, now())
      FROM social_wiring.julia_videos_prontos_submissoes s
     WHERE (p_org IS NULL OR s.org_id = p_org)
       AND NOT EXISTS (SELECT 1 FROM social_wiring.julia_video_pronto_events e WHERE e.entity_id = s.id)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.julia_video_pronto_backfill_initial_state(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.julia_video_pronto_backfill_initial_state(UUID) TO service_role;

