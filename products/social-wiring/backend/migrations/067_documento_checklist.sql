-- 067 · The permanent document checklist — TICK STATE ONLY.
--
-- Every lead that becomes a client needs the same six pieces of identity data
-- collected before the process can start. That list is the SAME for every
-- client, so it is not data — it is a decision, and it lives in code
-- (`documento_checklist_service.ITENS`).
--
-- WHY NOT `cliente_checklists`
-- ---------------------------
-- The obvious move is a row in `cliente_checklists` with `origem='documentos'`
-- plus six `cliente_checklist_itens`. That materialises the DEFINITION once per
-- client, and the definition is the thing most likely to change: adding a
-- seventh field would then need a backfill across every existing client, and
-- until it finished, cards created before and after would show different
-- checklists. A card whose checklist depends on when it was created is exactly
-- the drift the card_hub exists to avoid.
--
-- So this table stores ONLY what is genuinely per-client: which items are
-- ticked. An item with no row here is simply not done. Adding, renaming or
-- reordering an item is a code change that every card reflects immediately,
-- and no row here becomes wrong — `item_key` is the stable identity, never the
-- label.
--
-- An orphan row (item_key retired from the code) is inert: nothing reads it.
-- It is left rather than deleted so an accidental retirement is reversible.

CREATE TABLE IF NOT EXISTS social_wiring.cliente_documento_checklist (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    cliente_id     UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    -- Stable key from `documento_checklist_service.ITENS` — NOT the label.
    -- Renaming "Gênero" must never orphan its tick.
    item_key       TEXT NOT NULL,
    concluido      BOOLEAN NOT NULL DEFAULT false,
    concluido_em   TIMESTAMPTZ,
    concluido_por  UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One tick per (client, item). The upsert in `marcar` depends on this.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_documento_checklist_item
    ON social_wiring.cliente_documento_checklist (cliente_id, item_key);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_documento_checklist_cliente
    ON social_wiring.cliente_documento_checklist (cliente_id);

ALTER TABLE social_wiring.cliente_documento_checklist ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_documento_checklist_select_own_org"
    ON social_wiring.cliente_documento_checklist;
CREATE POLICY "cliente_documento_checklist_select_own_org"
    ON social_wiring.cliente_documento_checklist
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_documento_checklist_service_role"
    ON social_wiring.cliente_documento_checklist;
CREATE POLICY "cliente_documento_checklist_service_role"
    ON social_wiring.cliente_documento_checklist
    FOR ALL TO service_role USING (true) WITH CHECK (true);
