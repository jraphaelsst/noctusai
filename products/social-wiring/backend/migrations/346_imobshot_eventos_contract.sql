-- Resolves: NOC-REMEDIATE[imobshot-eventos-contract]
-- 346 — ImobShotAI: CONTRACT step. Drops the legacy hand-written `imobshot_eventos` (344) now that 345 moved the card
-- history onto the seed transition_log (`imobshot_card_events`) and prod verified it (0 legacy rows, INSERT revoked).
--
-- Nothing reads or writes the legacy table any more (the repository goes through `imobshot_card_*`). The guard RAISES
-- if any legacy row's id is not already an event, so unmigrated data is never dropped; the guard and the drops share
-- ONE block, so an abort skips the drops however the file is replayed. Idempotent (IF EXISTS; a no-op once the table is
-- gone). 344 and 345 are frozen and untouched.

SET search_path = social_wiring, pg_catalog, pg_temp;

DO $$
DECLARE
    v_missing int;
    v_sample  text;
BEGIN
    IF to_regclass('social_wiring.imobshot_eventos') IS NOT NULL THEN
        IF to_regclass('social_wiring.imobshot_card_events') IS NULL THEN
            RAISE EXCEPTION 'imobshot_eventos contract: imobshot_card_events does not exist (345 not applied); nothing was dropped';
        END IF;
        SELECT count(*), left(string_agg(o.id::text, ', '), 200) INTO v_missing, v_sample
          FROM social_wiring.imobshot_eventos o
         WHERE NOT EXISTS (SELECT 1 FROM social_wiring.imobshot_card_events n WHERE n.id = o.id);
        IF v_missing > 0 THEN
            RAISE EXCEPTION 'imobshot_eventos contract: % legacy row(s) are not in imobshot_card_events (sample ids: %); nothing was dropped', v_missing, v_sample;
        END IF;
        EXECUTE 'DROP TRIGGER IF EXISTS imobshot_eventos_no_update ON social_wiring.imobshot_eventos';
        EXECUTE 'DROP TABLE social_wiring.imobshot_eventos';
    END IF;
    EXECUTE 'DROP FUNCTION IF EXISTS social_wiring.imobshot_eventos_append_only()';
END $$;
