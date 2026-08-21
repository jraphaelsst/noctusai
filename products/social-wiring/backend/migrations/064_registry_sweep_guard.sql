-- ============================================================================
-- Migration 064 -- social_wiring: a circuit breaker on the registry sweep
--
-- WHY THIS EXISTS -- a real incident, 2026-08-21
-- ----------------------------------------------
-- Minutes after 063 was applied, `sweep_imovel_registry` was invoked by hand
-- to verify it worked. It delisted 484 imóveis that are live in the catalog,
-- wrote last-known snapshots over all of them, and reported success.
--
-- The call was wrong, not the function: it passed
-- `max(sincronizado_em)` as `p_run_at`. That looks like "the moment of the
-- last sync" and is not. The 2026-08-21 run stamped its rows at two instants
-- 83 ms apart (03:05:00.254 and 03:05:00.337 — 443 and 1500 rows), so
-- `>= max(...)` excluded the 443 rows written at the earlier instant. They
-- were present in the catalog and were delisted anyway.
--
-- The sync itself passes its OWN `started` stamp, which is <= every row it
-- writes, so the production path was never wrong. But nothing in the
-- database refused an obviously-destructive sweep, and that is the actual
-- defect: a function that can silently retire a quarter of the catalog
-- should not depend on every caller getting an argument subtly right.
--
-- (Why one run produced two stamps is NOT established. The container logs
-- had rolled over before this was investigated. Both candidate explanations
-- -- two overlapping runs, or a non-uniform stamp inside one run -- are
-- contained by the guard below, so it is recorded as an open question
-- rather than guessed at.)
--
-- THE GUARD
-- ---------
-- Refuse a sweep that would delist more than `p_max_delist_pct` of the
-- currently-active registry, unless the absolute count is trivially small.
-- Both conditions matter:
--   · a percentage alone would block a legitimate sweep on a 3-imóvel org;
--   · an absolute count alone would wave through 480/1943.
--
-- RAISE, not a silent no-op. A refused sweep means the registry keeps a
-- stale `ativo_no_vista` for one night — recoverable, visible, and loud. A
-- silent skip would look identical to a clean run.
--
-- ALSO FIXED HERE: reactivation now CLEARS the snapshot.
-- 063 set `delistado_em = NULL` when an imóvel reappeared but left `snap_*`
-- populated, so a row could be simultaneously active and carrying a
-- "last known state before it left" — two contradictory facts. The invariant
-- is: snapshot is present IF AND ONLY IF the imóvel is delisted.
--
-- PREREQUISITE: 063_imovel_registry.sql.
-- Forward-only + idempotent (CREATE OR REPLACE).
-- ============================================================================

SET search_path = social_wiring, public;

-- DROP the 2-argument signature FIRST. `CREATE OR REPLACE` matches on the
-- full argument list, so adding two defaulted parameters creates a SECOND
-- function rather than replacing the first. Both would then be candidates
-- for the app's 2-argument `rpc("sweep_imovel_registry", {p_org_id,
-- p_run_at})` call, and Postgres refuses an ambiguous overload:
--   ERROR 42725: function ... is not unique
-- Which would have taken the nightly sweep down the first time it ran.
DROP FUNCTION IF EXISTS social_wiring.sweep_imovel_registry(UUID, TIMESTAMPTZ);

CREATE OR REPLACE FUNCTION social_wiring.sweep_imovel_registry(
    p_org_id UUID,
    p_run_at TIMESTAMPTZ,
    p_max_delist_pct NUMERIC DEFAULT 20.0,
    p_min_delist_abs INTEGER DEFAULT 50
)
RETURNS TABLE (marcados_ativos INTEGER, marcados_delistados INTEGER)
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_ativos INTEGER := 0;
    v_delistados INTEGER := 0;
    v_ativos_antes INTEGER := 0;
    v_a_delistar INTEGER := 0;
    v_pct NUMERIC := 0;
BEGIN
    SELECT count(*) INTO v_ativos_antes
      FROM social_wiring.imovel_registry
     WHERE org_id = p_org_id AND ativo_no_vista;

    -- ── The circuit breaker, BEFORE any write ───────────────────────────
    SELECT count(*) INTO v_a_delistar
      FROM social_wiring.imovel_registry r
     WHERE r.org_id = p_org_id
       AND r.ativo_no_vista
       AND NOT EXISTS (
           SELECT 1 FROM social_wiring.imoveis i
            WHERE i.org_id = p_org_id
              AND i.codigo_norm = r.codigo_canonical
              AND i.sincronizado_em >= p_run_at
       );

    IF v_ativos_antes > 0 THEN
        v_pct := (v_a_delistar::NUMERIC / v_ativos_antes::NUMERIC) * 100.0;
    END IF;

    IF v_a_delistar > p_min_delist_abs AND v_pct > p_max_delist_pct THEN
        -- PL/pgSQL's RAISE takes a bare `%` placeholder — it has no printf
        -- precision syntax, so `%.1f` emits the full numeric followed by a
        -- literal ".1f". Round before interpolating.
        --
        -- And the percent SIGN is spelled out rather than written as `%%`
        -- next to a placeholder: `%%%` is ambiguous (it lexes as literal-%
        -- then placeholder, i.e. the sign lands on the wrong side of the
        -- number). Not worth the cleverness in an error message whose whole
        -- job is to be read under pressure.
        RAISE EXCEPTION
            'sweep_imovel_registry refused: would delist % of % active imoveis '
            '(% pct, limit % pct) for org % at run_at %. This usually means '
            'p_run_at is later than the timestamps the sync actually wrote — '
            'pass the run''s OWN start stamp, not max(sincronizado_em).',
            v_a_delistar, v_ativos_antes, round(v_pct, 1),
            round(p_max_delist_pct, 1), p_org_id, p_run_at
            USING ERRCODE = 'raise_exception';
    END IF;

    -- ── 1. Present in this run ⇒ active, and NOT delisted ───────────────
    -- Clearing `snap_*` is the invariant: a snapshot exists if and only if
    -- the imóvel is currently delisted. 063 left them populated on
    -- reactivation, which made a row assert two contradictory things.
    WITH presentes AS (
        SELECT codigo_norm FROM social_wiring.imoveis
         WHERE org_id = p_org_id AND sincronizado_em >= p_run_at
    )
    UPDATE social_wiring.imovel_registry r
       SET ativo_no_vista = TRUE,
           ultimo_visto_no_vista_em = p_run_at,
           delistado_em = NULL,
           snap_titulo = NULL, snap_categoria = NULL, snap_status = NULL,
           snap_bairro = NULL, snap_cidade = NULL, snap_uf = NULL,
           snap_valor_venda = NULL, snap_valor_locacao = NULL,
           snap_dormitorios = NULL, snap_area_total = NULL,
           snap_foto_destaque = NULL, snap_em = NULL
      FROM presentes p
     WHERE r.org_id = p_org_id AND r.codigo_canonical = p.codigo_norm;
    GET DIAGNOSTICS v_ativos = ROW_COUNT;

    -- ── 2. Absent ⇒ delisted, snapshot taken from the row going stale ───
    WITH ausentes AS (
        SELECT r.id, r.codigo_canonical
          FROM social_wiring.imovel_registry r
         WHERE r.org_id = p_org_id
           AND r.ativo_no_vista
           AND NOT EXISTS (
               SELECT 1 FROM social_wiring.imoveis i
                WHERE i.org_id = p_org_id
                  AND i.codigo_norm = r.codigo_canonical
                  AND i.sincronizado_em >= p_run_at
           )
    )
    UPDATE social_wiring.imovel_registry r
       SET ativo_no_vista = FALSE,
           delistado_em = p_run_at,
           snap_titulo        = i.titulo,
           snap_categoria     = i.categoria,
           snap_status        = i.status,
           snap_bairro        = i.bairro,
           snap_cidade        = i.cidade,
           snap_uf            = i.uf,
           snap_valor_venda   = i.valor_venda,
           snap_valor_locacao = i.valor_locacao,
           snap_dormitorios   = i.dormitorios,
           snap_area_total    = i.area_total,
           snap_foto_destaque = i.foto_destaque,
           snap_em            = p_run_at
      FROM ausentes a
      LEFT JOIN social_wiring.imoveis i
             ON i.org_id = p_org_id AND i.codigo_norm = a.codigo_canonical
     WHERE r.id = a.id;
    GET DIAGNOSTICS v_delistados = ROW_COUNT;

    RETURN QUERY SELECT v_ativos, v_delistados;
END;
$$;

-- ── Repair the 2026-08-21 incident ──────────────────────────────────────
-- Idempotent: after the guard is in place these are no-ops on a healthy
-- database. They are here so the file alone reconstructs the correct state,
-- rather than depending on the ad-hoc statements run during the incident.
UPDATE social_wiring.imovel_registry
   SET snap_titulo = NULL, snap_categoria = NULL, snap_status = NULL,
       snap_bairro = NULL, snap_cidade = NULL, snap_uf = NULL,
       snap_valor_venda = NULL, snap_valor_locacao = NULL,
       snap_dormitorios = NULL, snap_area_total = NULL,
       snap_foto_destaque = NULL, snap_em = NULL
 WHERE ativo_no_vista AND snap_em IS NOT NULL;
