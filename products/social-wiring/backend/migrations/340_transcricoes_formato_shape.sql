-- ============================================================================
-- Migration 340 · social_wiring: `transcricoes.formato` checks a SHAPE, not a
-- hand-copied value list.
-- ============================================================================
-- WHY
-- ---
-- 225 pinned `formato IN ('webm','ogg','mp4','mp3','wav')`, a SQL copy of the
-- seed's container allowlist. On 2026-11-13 the seed widened that allowlist
-- (noctusai_lib.integrations.transcription.validation.CONTAINERS: flac, aiff,
-- aac, wma, amr, caf, mkv on top of the five), because the old one effectively
-- accepted only mp3 + ogg/opus. With the copy in place, a flac upload would pass
-- validation and the quota RPC, then fail the INSERT — a hand-maintained list
-- drifting from its source (CLAUDE.md §1 "derive, don't sync by hand").
--
-- The vocabulary has ONE owner: the seed. The column keeps a shape check, so a
-- garbage value still cannot land, without a second list to keep in sync.
-- ============================================================================

DO $$
DECLARE c record;
BEGIN
  FOR c IN
    SELECT con.conname
      FROM pg_constraint con
     WHERE con.conrelid = 'social_wiring.transcricoes'::regclass
       AND con.contype = 'c'
       AND pg_get_constraintdef(con.oid) ILIKE '%formato%'
       AND con.conname <> 'transcricoes_formato_shape'
  LOOP
    EXECUTE format('ALTER TABLE social_wiring.transcricoes DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;

ALTER TABLE social_wiring.transcricoes
  DROP CONSTRAINT IF EXISTS transcricoes_formato_shape;
ALTER TABLE social_wiring.transcricoes
  ADD CONSTRAINT transcricoes_formato_shape CHECK (formato ~ '^[a-z0-9]{2,8}$');

COMMENT ON CONSTRAINT transcricoes_formato_shape ON social_wiring.transcricoes IS
  'Canonical container name (seed transcription.validation.CONTAINERS owns the vocabulary; 340).';
