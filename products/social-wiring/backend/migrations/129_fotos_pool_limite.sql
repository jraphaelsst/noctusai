-- 129_fotos_pool_limite.sql -- social_wiring: reference-pool size limit
--
-- Edição de Fotos W6 (contract §5, plan §1): the global reference pool has a
-- size limit set in the admin UI, COUNTED IN PAIRS. NULL or 0 = unlimited.
-- Uploads are blocked while the pool is full; archived pairs
-- (`arquivado_em IS NOT NULL`) never count.
--
-- 1. `fotos_platform_settings.limite_pares_referencia` -- the setting
--    (124 shipped the pool table but nowhere to store its limit).
-- 2. A BEFORE INSERT / un-archive trigger on `fotos_referencias` that
--    refuses a pair past the limit. The API checks the limit first (the
--    friendly 409 `pool_cheio`); this trigger is the race-free half: it
--    takes a row lock on the settings singleton, so two concurrent uploads
--    serialize and the second one sees the first one's row. The error
--    message starts with `pool_cheio`, which the seed repository
--    (`SupabasePhotoEditingRepository.add_reference`) maps to
--    `PoolFullError`.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. The setting
-- ----------------------------------------------------------------------------

ALTER TABLE social_wiring.fotos_platform_settings
    ADD COLUMN IF NOT EXISTS limite_pares_referencia INTEGER
        CHECK (limite_pares_referencia IS NULL OR limite_pares_referencia >= 0);

COMMENT ON COLUMN social_wiring.fotos_platform_settings.limite_pares_referencia IS
    'Reference-pool size limit in PAIRS. NULL or 0 = unlimited. Archived pairs do not count.';

-- ----------------------------------------------------------------------------
-- 2. Write-time enforcement
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION social_wiring.fotos_referencias_limite()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_limite INTEGER;
    v_ativos INTEGER;
BEGIN
    IF NEW.arquivado_em IS NOT NULL THEN
        RETURN NEW;  -- an archived row never counts
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.arquivado_em IS NULL THEN
        RETURN NEW;  -- already active: not a new pair
    END IF;

    -- Row lock on the singleton serializes concurrent inserts.
    SELECT limite_pares_referencia INTO v_limite
    FROM social_wiring.fotos_platform_settings
    WHERE id = 1
    FOR UPDATE;

    IF COALESCE(v_limite, 0) = 0 THEN
        RETURN NEW;
    END IF;

    SELECT count(*) INTO v_ativos
    FROM social_wiring.fotos_referencias
    WHERE arquivado_em IS NULL;

    IF v_ativos >= v_limite THEN
        RAISE EXCEPTION 'pool_cheio: pool de referências cheio (% pares)', v_limite
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fotos_referencias_limite ON social_wiring.fotos_referencias;
CREATE TRIGGER trg_fotos_referencias_limite
    BEFORE INSERT OR UPDATE OF arquivado_em ON social_wiring.fotos_referencias
    FOR EACH ROW
    EXECUTE FUNCTION social_wiring.fotos_referencias_limite();

-- Trigger functions are invoked by the trigger, never called directly.
REVOKE EXECUTE ON FUNCTION social_wiring.fotos_referencias_limite() FROM PUBLIC;
