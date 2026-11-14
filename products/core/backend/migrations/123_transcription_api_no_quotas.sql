-- 123: transcription API -- drop every usage quota (owner decision 2026-11-14).
-- The owner asked for load-protection guards, never for daily minute caps (the figures were
-- agent-chosen). Removed from reservar_transcricao_api: hourly submission cap (limite_envios_hora)
-- and the rolling-24h minute caps per caller / org / global (cota_diaria_chamador, cota_diaria_org,
-- capacidade_diaria). Kept: argument validation, advisory locks, per-caller in-flight cap
-- (limite_em_andamento, 3) and global queue depth (fila_cheia, 20). Same signature and grants as 074.
-- Backward-compatible with the previous image: same return shape, strictly fewer refusal codes.

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
    -- Limits (CONTRACT §3) -- declared once, here. No daily/hourly usage quotas (owner 2026-11-14).
    c_caller_em_andamento  CONSTANT int     := 3;
    c_fila_max             CONSTANT int     := 20;

    v_n         int;
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
