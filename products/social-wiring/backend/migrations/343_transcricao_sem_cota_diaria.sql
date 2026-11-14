-- 343: transcription (voice + library lanes) -- drop every DAILY usage cap (owner decision 2026-11-14).
-- The owner asked for load protection, never for daily minute caps (agent-chosen figures); the
-- transcriber runs on its own server so it can be used heavily. Removed:
--   reservar_transcricao          : cota_diaria_usuario (30 min/24h), cota_diaria_org (120 min/24h),
--                                   capacidade_diaria (600 min/24h platform-wide)
--   reservar_transcricao_biblioteca: cota_diaria_biblioteca_org, capacidade_diaria_biblioteca
-- Kept: advisory locks, per-user in-flight cap (2) and per-user hourly burst cap (10, limite_usuario),
-- global queue depth (20, fila_cheia), library per-reel length (180 s) and library queue (5).
-- Same signatures, return shapes, SECURITY INVOKER, search_path and grants as 229: strictly fewer
-- refusal codes, so the previous image keeps working.

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
    v_mais_antigo TIMESTAMPTZ;
    v_row        social_wiring.transcricoes%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:user:' || p_user::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:global', 0));

    -- per user: in flight
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE user_id = p_user AND origem = 'usuario' AND status IN ('na_fila', 'processando');
    IF v_n >= 2 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_usuario', 'http', 429, 'retry_after_s', 60);
    END IF;

    -- per user: submissions per hour
    SELECT count(*), min(criado_em) INTO v_n, v_mais_antigo FROM social_wiring.transcricoes
     WHERE user_id = p_user AND origem = 'usuario' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '1 hour';
    IF v_n >= 10 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_usuario', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '1 hour' - v_agora)))::int));
    END IF;

    -- global: queue depth
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE origem = 'usuario' AND status IN ('na_fila', 'processando');
    IF v_n >= 20 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'fila_cheia', 'http', 503, 'retry_after_s', 120);
    END IF;

    INSERT INTO social_wiring.transcricoes
        (id, org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato, criado_em, origem)
    VALUES
        (p_id, p_org, p_user, p_contexto_tipo, p_contexto_ref, p_storage_path, p_bytes, p_duracao_s, p_formato, v_agora, 'usuario')
    RETURNING * INTO v_row;

    RETURN jsonb_build_object('ok', true, 'row', to_jsonb(v_row));
END
$fn$;

COMMENT ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT) IS
    'Migration 225, redefined by 229 and 343 (no daily caps) - atomic load gate + insert for a VOICE transcription (every counter sees only origem = usuario). Service role only.';

REVOKE EXECUTE ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT)
    TO service_role;

CREATE OR REPLACE FUNCTION social_wiring.reservar_transcricao_biblioteca(
    p_id            UUID,
    p_org           UUID,
    p_user          UUID,
    p_duracao_s     NUMERIC,
    p_bytes         BIGINT,
    p_formato       TEXT,
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
    v_row        social_wiring.transcricoes%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:biblioteca', 0));

    -- per reel
    IF p_duracao_s > 180 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'reel_longo', 'http', 422, 'retry_after_s', 0);
    END IF;

    -- library rows queued or processing
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE origem = 'biblioteca' AND status IN ('na_fila', 'processando');
    IF v_n >= 5 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'fila_biblioteca_cheia', 'http', 503, 'retry_after_s', 120);
    END IF;

    INSERT INTO social_wiring.transcricoes
        (id, org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato, criado_em, origem)
    VALUES
        (p_id, p_org, p_user, 'biblioteca_viral', p_contexto_ref, p_storage_path, p_bytes, p_duracao_s, p_formato, v_agora, 'biblioteca')
    RETURNING * INTO v_row;

    RETURN jsonb_build_object('ok', true, 'row', to_jsonb(v_row));
END
$fn$;

COMMENT ON FUNCTION social_wiring.reservar_transcricao_biblioteca(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT) IS
    'Migration 229, redefined by 343 (no daily caps) - the library lane load gate + insert (origem = biblioteca; geracao-contract.md 3.4). Service role only.';

REVOKE EXECUTE ON FUNCTION social_wiring.reservar_transcricao_biblioteca(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.reservar_transcricao_biblioteca(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT)
    TO service_role;
