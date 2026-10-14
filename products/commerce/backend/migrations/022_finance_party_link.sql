-- 022_finance_party_link.sql — finance entries link to the parties organ (FinanceConfig.with_parties=True).
--
-- DELTA over 017_finance.sql: the lines `finance_migration(FinanceConfig(schema, with_parties=True))` emits that the
-- default output (017) does not — a nullable `fin_entries.party_id` with a composite same-org FK to
-- `pty_parties` (020), so a payable can point at its supplier and a linked party is never hard-deleted
-- (PartiesConfig.reference_tables). Forward-only + idempotent. Pinned by
-- tests/test_commerce_p4_wiring.py::test_finance_party_link_delta_is_the_generators_with_parties_diff.

-- Party link (parties organ): nullable, same-org by composite FK.
ALTER TABLE commerce.fin_entries ADD COLUMN IF NOT EXISTS party_id UUID;
ALTER TABLE commerce.fin_entries DROP CONSTRAINT IF EXISTS fin_entries_party_fk;
ALTER TABLE commerce.fin_entries ADD CONSTRAINT fin_entries_party_fk
    FOREIGN KEY (party_id, org_id) REFERENCES commerce.pty_parties(id, org_id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_fin_entries_party ON commerce.fin_entries (org_id, party_id) WHERE party_id IS NOT NULL;
