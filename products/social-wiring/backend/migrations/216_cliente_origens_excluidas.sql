-- ============================================================================
-- Migration 216 · social_wiring: `cliente_origens_excluidas` -- tombstones so a
-- DELETED cliente is not re-created from its (still existing) lead
-- ============================================================================
-- WHY
-- ---
-- Found in prod 2026-10-09: "[TESTE P3] 876 Reserva do Viana" was deleted on
-- 2026-10-07 (`DELETE /api/clientes/{id}` hard-deletes; `cliente_touches`
-- CASCADEs) and was RECREATED as 97a05bee... at 22:57:56 UTC by the 6-hourly
-- `clientes_service.run_backfill`, from lead 96aabb98... which still exists:
-- the backfill treats every lead whose (origem_tabela, origem_id) has no touch
-- as NEW. The recreated person had no CPF and no documents.
--
-- OWNER DECISION 2026-10-09: "Mark as deleted, keep leads." Leads are EVENTS
-- (kept for attribution); a cliente is a PERSON. So `excluir_cliente` records
-- one tombstone per touched source row BEFORE deleting, and the backfill skips
-- tombstoned sources. Only the old source rows are tombstoned -- never the
-- person's key: a NEW lead from the same person is a new event and creates a
-- new cliente. Merges never write here.
--
-- `cliente_id` has NO FK on purpose: the cliente row is gone; it is audit only.
-- Uniqueness is global (not org-scoped) for the same reason as 048's
-- uq_sw_cliente_touches_origem: leads.id is a UUID and meta_ads_leads.id is
-- Meta's globally unique id.
--
-- FORWARD-ONLY, IDEMPOTENT. NOT APPLIED by the author.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'migration 216 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'migration 216 requires public.attach_acting_audit_triggers (core migration 072) -- apply core first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.cliente_origens_excluidas (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL
        REFERENCES public.organizations (id) ON DELETE CASCADE,
    origem_tabela  TEXT NOT NULL CHECK (origem_tabela IN ('leads', 'meta_ads_leads')),
    origem_id      TEXT NOT NULL,
    cliente_id     UUID NOT NULL,
    cliente_nome   TEXT,
    excluido_por   UUID,
    excluido_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN social_wiring.cliente_origens_excluidas.cliente_id IS
    'Id of the DELETED cliente. Deliberately no FK: the row no longer exists; audit only.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_origens_excluidas_origem
    ON social_wiring.cliente_origens_excluidas (origem_tabela, origem_id);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_origens_excluidas_org
    ON social_wiring.cliente_origens_excluidas (org_id);

ALTER TABLE social_wiring.cliente_origens_excluidas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_origens_excluidas_select_own_org" ON social_wiring.cliente_origens_excluidas;
CREATE POLICY "cliente_origens_excluidas_select_own_org"
    ON social_wiring.cliente_origens_excluidas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cliente_origens_excluidas_write_own_org" ON social_wiring.cliente_origens_excluidas;
CREATE POLICY "cliente_origens_excluidas_write_own_org"
    ON social_wiring.cliente_origens_excluidas
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cliente_origens_excluidas_service_role" ON social_wiring.cliente_origens_excluidas;
CREATE POLICY "cliente_origens_excluidas_service_role"
    ON social_wiring.cliente_origens_excluidas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Acting-audit trigger for the new table (migration 214, idempotent).
SELECT public.attach_acting_audit_triggers('social_wiring');
