-- ============================================================================
-- Migration 225 · social_wiring: shared voice transcription product layer —
-- `transcricoes`, the quota RPC `reservar_transcricao()`, the private
-- `sw-transcricoes` bucket, and the transcricao_id FKs of Segundo Cerebro
-- ============================================================================
-- WHY
-- ---
-- Contract: projects/core-studio/specs/transcription-contract.md (section 3 abuse
-- shield, section 5 row 3). One row per submitted recording; the audio itself
-- lives in the PRIVATE bucket and is deleted right after a successful
-- transcription (LGPD: voice is personal data). All writes go through the
-- service role (the backend); an authenticated user can only SELECT own rows.
--
-- QUOTAS ARE IN POSTGRES, NOT REDIS: prod has no Redis, and an in-memory tracker
-- dies on restart. `reservar_transcricao()` takes a per-user advisory lock (and a
-- global one, so the org/global caps are exact) and checks + inserts in ONE
-- transaction. The numbers below ARE the contract (section 3):
--   per user   <= 10 submissions / hour, <= 1800 s (30 min) / rolling 24 h, <= 2 in flight
--   per org    <= 7200 s (120 min) / rolling 24 h
--   global     <= 36000 s (600 min) / rolling 24 h, queue depth (na_fila+processando) <= 20
-- Rolling 24 h sums `duracao_s` of rows with `minutos_reembolsados = false`;
-- minutes of a failure we caused (or a cancellation) are refunded.
--
-- Resolves the fk-transcricoes deferral recorded in migration 224: the FKs are added
-- here (ON DELETE SET NULL).
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_brain_answers') IS NULL THEN
    RAISE EXCEPTION 'Migration 225 requires social_wiring.cs_brain_answers (migration 224) -- apply 224 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.transcricoes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    user_id              UUID NOT NULL,
    contexto_tipo        TEXT NOT NULL CHECK (contexto_tipo ~ '^[a-z][a-z0-9_]{0,39}$'),
    contexto_ref         TEXT NOT NULL CHECK (char_length(contexto_ref) BETWEEN 1 AND 200),
    storage_path         TEXT NOT NULL,
    bytes                BIGINT NOT NULL CHECK (bytes > 0),
    duracao_s            NUMERIC(8, 2) NOT NULL CHECK (duracao_s > 0),
    formato              TEXT NOT NULL CHECK (formato IN ('webm', 'ogg', 'mp4', 'mp3', 'wav')),
    status               TEXT NOT NULL DEFAULT 'na_fila'
                         CHECK (status IN ('na_fila', 'processando', 'concluida', 'falhou', 'cancelada')),
    texto                TEXT CHECK (char_length(texto) <= 200000),
    erro_codigo          TEXT,
    modelo               TEXT,
    rtf                  NUMERIC(8, 3),
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    iniciado_em          TIMESTAMPTZ,
    concluido_em         TIMESTAMPTZ,
    audio_apagado_em     TIMESTAMPTZ,
    minutos_reembolsados BOOLEAN NOT NULL DEFAULT false,
    -- Set (atomically, claim-then-apply) when the completion hook for
    -- `contexto_tipo` ran: the exactly-once marker of the hook.
    hook_aplicado_em     TIMESTAMPTZ,
    -- A refund only exists for a failure or a cancellation.
    CONSTRAINT transcricoes_reembolso_so_terminal
        CHECK (NOT minutos_reembolsados OR status IN ('falhou', 'cancelada'))
);

COMMENT ON TABLE social_wiring.transcricoes IS
    'Migration 225 - shared voice transcription jobs (transcription-contract.md). Audio is in the private '
    'sw-transcricoes bucket and deleted right after success (audio_apagado_em); transcripts purged after 7 days. '
    'Writes are service-role only.';

CREATE INDEX IF NOT EXISTS transcricoes_user_criado_idx ON social_wiring.transcricoes (user_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS transcricoes_org_criado_idx ON social_wiring.transcricoes (org_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS transcricoes_status_idx ON social_wiring.transcricoes (status);

-- ----------------------------------------------------------------------------
-- 2. RLS: owner SELECT only; every write is the service role (the backend)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.transcricoes ENABLE ROW LEVEL SECURITY;

REVOKE INSERT, UPDATE, DELETE ON social_wiring.transcricoes FROM anon, authenticated;

DROP POLICY IF EXISTS "transcricoes_select_owner" ON social_wiring.transcricoes;
CREATE POLICY "transcricoes_select_owner"
    ON social_wiring.transcricoes
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "transcricoes_service_role" ON social_wiring.transcricoes;
CREATE POLICY "transcricoes_service_role"
    ON social_wiring.transcricoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. reservar_transcricao(): the atomic quota gate
-- ----------------------------------------------------------------------------
-- Returns jsonb: {"ok": true, "row": {...transcricoes row...}} or
-- {"ok": false, "codigo": <code>, "http": 429|503, "retry_after_s": <int>}.
-- Charged on the PROBED duration the caller passes (never a client-sent value).
CREATE OR REPLACE FUNCTION social_wiring.reservar_transcricao(
    p_id            UUID,
    p_org           UUID,
    p_user          UUID,
    p_duracao_s     NUMERIC,
    p_bytes         BIGINT,
    p_formato       TEXT,
    p_contexto_tipo TEXT,
    p_contexto_ref  TEXT,
    p_storage_path  TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = social_wiring, public
AS $fn$
DECLARE
    v_agora      TIMESTAMPTZ := now();
    v_n          INTEGER;
    v_soma       NUMERIC;
    v_mais_antigo TIMESTAMPTZ;
    v_row        social_wiring.transcricoes%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:user:' || p_user::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:global', 0));

    -- per user: in flight
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE user_id = p_user AND status IN ('na_fila', 'processando');
    IF v_n >= 2 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_usuario', 'http', 429, 'retry_after_s', 60);
    END IF;

    -- per user: submissions per hour
    SELECT count(*), min(criado_em) INTO v_n, v_mais_antigo FROM social_wiring.transcricoes
     WHERE user_id = p_user AND NOT minutos_reembolsados AND criado_em > v_agora - interval '1 hour';
    IF v_n >= 10 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_usuario', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '1 hour' - v_agora)))::int));
    END IF;

    -- per user: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE user_id = p_user AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 1800 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_usuario', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    -- per org: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE org_id = p_org AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 7200 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_org', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    -- global: queue depth
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes WHERE status IN ('na_fila', 'processando');
    IF v_n >= 20 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'fila_cheia', 'http', 503, 'retry_after_s', 120);
    END IF;

    -- global: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 36000 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'capacidade_diaria', 'http', 503,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    INSERT INTO social_wiring.transcricoes
        (id, org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato, criado_em)
    VALUES
        (p_id, p_org, p_user, p_contexto_tipo, p_contexto_ref, p_storage_path, p_bytes, p_duracao_s, p_formato, v_agora)
    RETURNING * INTO v_row;

    RETURN jsonb_build_object('ok', true, 'row', to_jsonb(v_row));
END
$fn$;

COMMENT ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT) IS
    'Migration 225 - atomic quota gate + insert for a transcription (transcription-contract.md section 3). Service role only.';

REVOKE EXECUTE ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT)
    TO service_role;

-- ----------------------------------------------------------------------------
-- 4. Private bucket (audio is personal data: never public, never a signed URL)
-- ----------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('sw-transcricoes', 'sw-transcricoes', false)
ON CONFLICT (id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 5. Segundo Cerebro transcricao_id FKs (resolves the fk-transcricoes deferral of 224)
-- ----------------------------------------------------------------------------
DO $fk$
DECLARE
    alvo TEXT[];
BEGIN
    FOREACH alvo SLICE 1 IN ARRAY ARRAY[
        ARRAY['cs_brain_answers', 'cs_brain_answers_transcricao_fk'],
        ARRAY['cs_brain_imports', 'cs_brain_imports_transcricao_fk'],
        ARRAY['cs_extractions',   'cs_extractions_transcricao_fk']
    ]
    LOOP
        IF to_regclass('social_wiring.' || alvo[1]) IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = alvo[2]) THEN
            EXECUTE format(
                'ALTER TABLE social_wiring.%I ADD CONSTRAINT %I FOREIGN KEY (transcricao_id) '
                'REFERENCES social_wiring.transcricoes (id) ON DELETE SET NULL',
                alvo[1], alvo[2]);
        END IF;
    END LOOP;
END
$fk$;

CREATE INDEX IF NOT EXISTS cs_brain_answers_transcricao_idx
    ON social_wiring.cs_brain_answers (transcricao_id) WHERE transcricao_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_brain_imports_transcricao_idx
    ON social_wiring.cs_brain_imports (transcricao_id) WHERE transcricao_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_extractions_transcricao_idx
    ON social_wiring.cs_extractions (transcricao_id) WHERE transcricao_id IS NOT NULL;
