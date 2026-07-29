-- 044_contratos_fks.sql — give `erp.contratos` the foreign keys it never had
--
-- ⚠️  AUTHORED BUT NOT APPLIED. This is a schema-design decision on a live
--     table, not a test fix — apply it deliberately:
--       noctus.dev.migrate_product erp-imobiliario \
--         target=044_contratos_fks.sql confirm=True
--
-- THE GAP (verified against live `pg_constraint` on 2026-07-29)
--   `SELECT ... WHERE relname='contratos' AND contype='f'` → ZERO rows.
--   `cliente_id`, `imovel_id` and `proposta_id` are all NOT NULL (or set by
--   every caller) yet reference nothing, so a contract can point at a client
--   or property that does not exist. Canonical migration
--   `001_erp_imobiliario.sql` declared the columns without REFERENCES, so this
--   is an ORIGINAL GAP — not a regression, and nothing broke it.
--
--   It surfaced because `tests/realdb/test_erp_realdb.py::TestFKViolation`
--   asserts a bad reference is rejected. It never could be. That test also had
--   no `cleanup` fixture, so every run left the junk row behind: 38 rows had
--   accumulated in PRODUCTION since 2026-03-14, all with `cliente_id ==
--   imovel_id` and the test's exact fixture shape. They were purged and the
--   test now registers cleanup, so the leak is closed independently of this
--   migration.
--
-- TARGETS — why these tables
--   `cliente_id` → `erp.clientes.id`. Unambiguous.
--   `imovel_id`  → `erp.ativos.id`. `erp` has NO `imoveis` table; `ativos` is
--                  the asset table and carries `natureza='imovel'`. This is the
--                  one inference in the migration — CONFIRM IT before applying.
--   `proposta_id` → `erp.propostas.id`, nullable, so `ON DELETE SET NULL`.
--
-- ON DELETE choices are conservative: RESTRICT on the two required parents (you
-- should not be able to delete a client or property out from under a live
-- contract), SET NULL on the optional proposta.
--
-- 🔴 BEFORE APPLYING, re-check for orphans — this migration REFUSES rather than
--    silently dropping rows, and the table was empty of real data at authoring
--    time but may not be later:
--      SELECT count(*) FROM erp.contratos c
--       WHERE NOT EXISTS (SELECT 1 FROM erp.clientes k WHERE k.id = c.cliente_id)
--          OR NOT EXISTS (SELECT 1 FROM erp.ativos  a WHERE a.id = c.imovel_id);
--
-- Forward-only + idempotent (named constraints, IF NOT EXISTS guard via DO).

SET search_path = erp, public;

DO $$
DECLARE
    n_orphans bigint;
BEGIN
    SELECT count(*) INTO n_orphans
      FROM erp.contratos c
     WHERE NOT EXISTS (SELECT 1 FROM erp.clientes k WHERE k.id = c.cliente_id)
        OR NOT EXISTS (SELECT 1 FROM erp.ativos  a WHERE a.id = c.imovel_id);

    IF n_orphans > 0 THEN
        -- Fail LOUD rather than deleting production rows as a side effect of a
        -- constraint migration. Triage the orphans, then re-run.
        RAISE EXCEPTION
            'REFUSING: % contrato(s) reference a missing cliente or imovel. '
            'Triage them before adding the FKs (see the query in this file''s header).',
            n_orphans;
    END IF;
END $$;

ALTER TABLE erp.contratos
    DROP CONSTRAINT IF EXISTS contratos_cliente_id_fkey,
    ADD  CONSTRAINT contratos_cliente_id_fkey
         FOREIGN KEY (cliente_id) REFERENCES erp.clientes(id) ON DELETE RESTRICT;

ALTER TABLE erp.contratos
    DROP CONSTRAINT IF EXISTS contratos_imovel_id_fkey,
    ADD  CONSTRAINT contratos_imovel_id_fkey
         FOREIGN KEY (imovel_id) REFERENCES erp.ativos(id) ON DELETE RESTRICT;

ALTER TABLE erp.contratos
    DROP CONSTRAINT IF EXISTS contratos_proposta_id_fkey,
    ADD  CONSTRAINT contratos_proposta_id_fkey
         FOREIGN KEY (proposta_id) REFERENCES erp.propostas(id) ON DELETE SET NULL;
