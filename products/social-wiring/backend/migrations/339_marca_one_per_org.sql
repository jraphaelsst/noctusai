-- ============================================================================
-- 339_marca_one_per_org.sql -- ONE brand per org, enforced by the database.
-- Schema: social_wiring
--
-- WHY: owner decision 2026-11-05 -- org = brand = customer; a second brand is a second org. Until now `marcas` allowed
-- several per org (UNIQUE (org_id, slug) + at most one primary, 210). The API already refuses a second create
-- (409 org_ja_tem_marca, marcas_service.OrgJaTemMarca); this index is the backstop for two concurrent creates.
-- Prod data checked 2026-11-12: 0 orgs with more than one marca (roadmap owner-kept-ideas-2026-11 P1.1).
--
-- GUARD: refuses to apply while any org still holds more than one marca -- the unique index would fail anyway, but
-- with an opaque error; this names the orgs.
--
-- Backward compatible with the previous image: N-1 can still POST a second marca, which now gets a unique_violation
-- -> its create path maps a unique error to 409, so N-1 degrades to a refusal, never to corruption.
-- Forward-only + idempotent. The table is tiny (single digits of rows): a plain CREATE UNIQUE INDEX holds its lock for
-- milliseconds; lock_timeout keeps it from queueing behind a long reader.
-- ============================================================================

SET search_path = social_wiring, public;

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE v_bad text;
BEGIN
  SELECT string_agg(format('%s (%s marcas)', org_id, n), ', ') INTO v_bad
    FROM (SELECT org_id, count(*) AS n FROM social_wiring.marcas GROUP BY org_id HAVING count(*) > 1) t;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION '339: org(s) hold more than one marca -- one brand per org must hold before this index: %', v_bad;
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_marcas_one_per_org ON social_wiring.marcas (org_id);

COMMENT ON INDEX social_wiring.uq_marcas_one_per_org IS
  'One brand per org (owner decision 2026-11-05). The primary-per-org index (210) stays: now implied but harmless.';
