-- ============================================================================
-- Migration 083 · social_wiring: cliente_checklist_extras — the OPERATOR's
-- half of the card's checklist surface.
--
-- WHY THIS TABLE EXISTS, AND WHY IT IS NOT `cliente_documento_checklist`
-- ---------------------------------------------------------------------
-- Migration 067 stores ticks for a list that is IDENTICAL for every client,
-- and says so: the definition lives in code (`documento_checklist_service
-- .ITENS`) precisely so adding a ninth mandatory item is a deploy and not a
-- per-client backfill. That argument is exactly why an operator-created row
-- cannot live there. "Send me the condominium bylaws for THIS client" is the
-- opposite kind of fact — it is per-client by definition, it has a label
-- someone typed, and it must not appear on anybody else's card.
--
-- So the two halves have two homes, and each home stores only what is
-- genuinely its own: 067 stores ticks against a code-owned list, this table
-- stores rows a person authored.
--
-- 🔴 WHY THERE IS NO `concluido` COLUMN
-- -------------------------------------
-- Same reasoning migration 068 applied to 067's ticks, and for the same
-- structural reason rather than by imitation. A `texto` extra is done when it
-- has text; an `arquivo` extra is done when it holds a live document. Both
-- facts are already in this row (`valor_texto`, `documento_id`), so a stored
-- `concluido` could only ever agree with them or be wrong — and it goes wrong
-- silently: the retention sweep (`documentos_service.run_retention_sweep`)
-- soft-deletes documents on a schedule with no knowledge of this table, so a
-- stored tick would survive the disappearance of the very file it asserts.
-- `checklist_extras_service` derives it on read; there is no interval in which
-- it is allowed to be stale.
--
-- 🔴 WHY `documento_id` IS A NULLABLE FK AND NOT A CASCADE
-- --------------------------------------------------------
-- The product rule is explicit: deleting the FILE keeps the ROW. An operator
-- who asked for the wrong scan deletes it and re-uploads onto the same line —
-- the line is the request ("Comprovante de residência"), the document is only
-- its current answer. `ON DELETE SET NULL` encodes that: should a documento
-- row ever be hard-deleted, the extra survives, empty and ready. A CASCADE
-- would delete the request along with the answer.
--
-- The live path never hard-deletes anyway (`cliente_documentos.deleted_at` is
-- a soft delete, migration 057), so the service also NULLs `documento_id`
-- itself when it soft-deletes — the FK is the backstop, not the mechanism.
--
-- ORG SCOPING + SOFT DELETE: copied from the sibling tables, deliberately.
-- `org_id UUID NOT NULL` + a SELECT policy on `public.current_org_id()` +
-- an ALL policy for `service_role` is the shape of 057 (`cliente_documentos`)
-- and 067 (`cliente_documento_checklist`); the backend writes through the
-- service-role admin client, which is why no `authenticated` INSERT/UPDATE
-- policy is granted here either.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the row
-- counts this will touch and the user has given an explicit go-ahead.
-- Applied state is recorded in `migrations/APPLIED.md` — do NOT trust this
-- header alone.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.cliente_checklist_extras (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    cliente_id    UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    -- What the operator typed. Free text on purpose: the whole point of this
    -- table is the request nobody anticipated.
    label         TEXT NOT NULL,
    -- How the line is satisfied. Mirrored in
    -- `checklist_extras_service.TIPOS_VALIDOS` — both exist on purpose: the
    -- schema protects the API surface, the CHECK protects every other writer
    -- (a migration, a script, a future job). Neither is redundant.
    tipo          TEXT NOT NULL CHECK (tipo IN ('texto', 'arquivo')),
    -- Exactly one of these carries the answer, decided by `tipo`. Not a
    -- CHECK-enforced XOR: an `arquivo` line that has not been uploaded to yet
    -- has neither, which a strict XOR would forbid, and the service refuses
    -- the crossed writes (a `valor_texto` on an `arquivo` line, a document on
    -- a `texto` line) with a 422 rather than a constraint violation the API
    -- would surface as a 500.
    valor_texto   TEXT,
    documento_id  UUID REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ordem         INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Soft delete, per the card_hub convention (057, 082): removing a line an
    -- operator authored is one UPDATE to undo, not a resurrection.
    deleted_at    TIMESTAMPTZ
);

-- The card's read path: this client's live lines, in the order they render.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_checklist_extras_cliente
    ON social_wiring.cliente_checklist_extras (cliente_id, ordem, created_at)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_cliente_checklist_extras_org
    ON social_wiring.cliente_checklist_extras (org_id);

-- Answers "is this document still referenced by a checklist line?" without a
-- sequential scan — the delete path asks it per document.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_checklist_extras_documento
    ON social_wiring.cliente_checklist_extras (documento_id)
    WHERE documento_id IS NOT NULL;

ALTER TABLE social_wiring.cliente_checklist_extras ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_checklist_extras_select_own_org"
    ON social_wiring.cliente_checklist_extras;
CREATE POLICY "cliente_checklist_extras_select_own_org"
    ON social_wiring.cliente_checklist_extras
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_checklist_extras_service_role"
    ON social_wiring.cliente_checklist_extras;
CREATE POLICY "cliente_checklist_extras_service_role"
    ON social_wiring.cliente_checklist_extras
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.cliente_checklist_extras IS
    'Operator-authored checklist lines for ONE client. The mandatory list '
    'lives in code (documento_checklist_service.ITENS) with its ticks in '
    'cliente_documento_checklist; this table is the per-client half. '
    'Completion is DERIVED (valor_texto for tipo=texto, a live documento_id '
    'for tipo=arquivo) and deliberately not stored.';

COMMENT ON COLUMN social_wiring.cliente_checklist_extras.documento_id IS
    'The document currently answering this line, or NULL. Deleting the file '
    'NULLs this and KEEPS the row — the line is the request, the document is '
    'only its current answer.';
