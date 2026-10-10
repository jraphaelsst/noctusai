-- 227_campanha_veiculacoes_nivel_not_null.sql — close the NULL hole in 218's nivel CHECK
--
-- 218 shipped `campanha_veiculacoes_nivel_valido` as
--     (canal = 'meta_ads' AND nivel IN (...)) OR (canal <> 'meta_ads' AND nivel IS NULL)
-- For a meta_ads row with nivel NULL, `nivel IN (...)` is NULL, the second arm is FALSE,
-- NULL OR FALSE is NULL — and a CHECK passes on NULL. So the "required for meta_ads" half
-- never fired (caught post-deploy by verify_db_guards probe
-- social_wiring.campanha_veiculacoes.meta_requires_nivel). The table was empty in prod at
-- the time, so no row needs repair; the pre-check below refuses loudly if one appeared.
--
-- Same constraint name, same contract (CONTRACT.md §1.2) — only the NULL arm is closed.
-- Idempotent: drop-if-exists + re-add inside one transaction.

SET search_path = social_wiring, public;

DO $c$
BEGIN
  IF EXISTS (SELECT 1 FROM social_wiring.campanha_veiculacoes
              WHERE canal = 'meta_ads' AND nivel IS NULL) THEN
    RAISE EXCEPTION 'campanha_veiculacoes has meta_ads rows with nivel NULL — set their nivel before applying 227';
  END IF;
END
$c$;

ALTER TABLE social_wiring.campanha_veiculacoes
  DROP CONSTRAINT IF EXISTS campanha_veiculacoes_nivel_valido;

ALTER TABLE social_wiring.campanha_veiculacoes
  ADD CONSTRAINT campanha_veiculacoes_nivel_valido CHECK (
    (canal = 'meta_ads' AND nivel IS NOT NULL AND nivel IN ('campaign', 'adset', 'ad', 'form'))
    OR (canal <> 'meta_ads' AND nivel IS NULL)
  );
