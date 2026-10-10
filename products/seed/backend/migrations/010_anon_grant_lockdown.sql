-- ============================================================================
-- Migration 010 — anon loses every table privilege in this schema except
-- SELECT on status_pagina (the public route map the SPA reads before login).
--
-- WHY: 001 originally ran `GRANT ALL ON ALL TABLES IN SCHEMA seed TO anon` plus a
-- matching DEFAULT PRIVILEGES grant. The lockdown was later written INTO 001
-- (b5abd1896, 2026-09-20), but 001 had already run in prod (ledger checksum =
-- the 2026-06-02 blob), so prod kept anon=arwdDxtm on seed.examples /
-- seed.status_pagina and on every future table. Found by the 2026-10-10 ledger
-- checksum audit. RLS still refused anon writes (no anon write policy), so this
-- is defence in depth, not an open hole — but a table that ever ships without
-- RLS would have been writable with the public anon key.
--
-- Applied migrations are immutable (the ledger stores their sha256), so the fix
-- is this forward migration, never an edit of 001. Idempotent: REVOKE/GRANT are
-- no-ops on re-apply. Mirrors social-wiring 140_anon_grant_lockdown.sql.
-- GuardProbes: verify_db_guards `seed.anon_*`.
-- ============================================================================

SET search_path = seed, public;

REVOKE ALL ON ALL TABLES IN SCHEMA seed FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA seed REVOKE ALL ON TABLES FROM anon;
GRANT SELECT ON seed.status_pagina TO anon;
