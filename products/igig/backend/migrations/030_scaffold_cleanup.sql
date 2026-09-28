-- ============================================================================
-- 030_scaffold_cleanup.sql — drop the seed scaffold nothing in igig reads
--
-- Two leftovers from the seed skeleton, confirmed dead by the closeout audit
-- (`platforma` achado #15):
--
--   * `igig.examples` (003) — the reference `example` CRUD's table. Its
--     router/service/schema/page were removed once the six módulos landed
--     (see `app/main.py`'s note); the table itself was never dropped. No
--     code path in this product reads or writes it.
--
--   * `igig.status_pagina` row `nome_pagina='marca'` (014) — 026 deliberately
--     LEFT this one alone ("a row for a route nobody links to is inert, and
--     deleting a status a human may have set is not this migration's call").
--     That call stands as written; THIS migration is a different, later one
--     confirming the same fact and acting on it: `/marca` is a pure redirect
--     to `/clientes` (`app/app.tsx`) that never calls `usePageStatus`, and no
--     other route name is `marca` — so no `filterNavByPageStatus` lookup, no
--     RLS read, nothing anywhere keys off this row. Deleting it changes no
--     observable behaviour today; keeping it only invites a future person to
--     wonder what "marca" gates.
--
-- Naming: deliberately NOT `030_igig_*` — same reason as 003/014/024/026:
-- neither target is a domain table with a SQLite mirror
-- (`tests/test_schema_parity.py` only requires one for `*_igig_*` files).
--
-- Idempotent: `DROP TABLE IF EXISTS` + a plain `DELETE` (no-op on a second
-- run once the row is gone).
-- ============================================================================
SET search_path = igig, public;

DROP TABLE IF EXISTS igig.examples;

DELETE FROM igig.status_pagina WHERE nome_pagina = 'marca';
