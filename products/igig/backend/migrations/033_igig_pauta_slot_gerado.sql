-- ============================================================================
-- IgIg — pauta_slot_gerado: an append-only generation ledger (leftovers #6)
--
-- Bug: `pautas.gerar`/`estender` decide whether a (orcamento_item, day) slot
-- already has a pauta by reading the LIVE `igig.pauta` rows
-- (`_dias_cobertos`). Once the user deletes that pauta, or drags it to a
-- different `data_publicacao`, the slot reads as uncovered again — the next
-- accept retry or the daily rolling job (`estender_pendentes`) silently
-- recreates it. A deliberately-removed or -rescheduled pauta must never come
-- back on its own.
--
-- Fix: record every (org, orcamento_item, day) slot the moment it is
-- generated, in its OWN append-only table — never updated, never deleted by
-- anything that touches `igig.pauta` itself (no FK from `pauta` to this
-- table, and `pauta_router.py`'s delete/reschedule never reference it). A
-- slot claimed once stays claimed forever, independent of what happens to
-- the pauta card that slot produced.
--
-- `orcamento_item_id` is stable for the lifetime of a generation ledger row:
-- an orçamento's items are only ever rewritten (delete+insert) while it is
-- still rascunho/enviado (`orcamentos._gravar_itens`), and pautas are only
-- ever generated for an ACCEPTED orçamento, whose items are frozen
-- (`_exigir_editavel` blocks further edits once aceito). `ON DELETE CASCADE`
-- only fires if the item row itself is later purged (e.g. the orçamento is
-- deleted outright) — at that point the ledger has nothing left to protect.
--
-- SQLite mirror: migrations/sqlite/033_pauta_slot_gerado.sql (no RLS there).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE IF NOT EXISTS igig.pauta_slot_gerado (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    orcamento_item_id   UUID NOT NULL REFERENCES igig.orcamento_item (id) ON DELETE CASCADE,
    slot_date           DATE NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, orcamento_item_id, slot_date)
);

CREATE INDEX IF NOT EXISTS idx_igig_pauta_slot_gerado_item
    ON igig.pauta_slot_gerado (orcamento_item_id);

ALTER TABLE igig.pauta_slot_gerado ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pauta_slot_gerado_org_isolation ON igig.pauta_slot_gerado;
CREATE POLICY pauta_slot_gerado_org_isolation ON igig.pauta_slot_gerado FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

NOTIFY pgrst, 'reload schema';
