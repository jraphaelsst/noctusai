-- ============================================================================
-- Migration 170 · social_wiring: per-card CUSTOM rows on the Certidões
-- matriz tab ("+ Adicionar certidão")
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- Owner request (2026-09-24, follow-up to the Levantamento de Certidões
-- matriz tab): the fixed 13 rows (5.1-5.13) stay fixed, but an operator can
-- add as many additional "Outras: <nome>" rows as a given card needs —
-- renamable, removable (soft-delete, results NEVER lost), numbered 5.14,
-- 5.15, ... in creation order. Replaces the two hard-coded `outras_1`/
-- `outras_2` registry rows this branch shipped in an earlier, unmerged
-- commit on THIS SAME feature branch (never reached `dev`/prod — see
-- `app/modules/certidoes/registry.py`'s own note — so no orphaning risk;
-- this migration removes them from the app-side registry in the same
-- commit, not here, since they were never a DB-level concept).
--
-- `certidao_matriz_linhas_customizadas` — one row per custom certidão TYPE
-- a card's operator defined. Scoped to (org_id, cliente_id): `cliente_id`
-- is the CARD's titular id, the same identifier `GET /api/clientes/
-- {cliente_id}/certidoes/matriz` is already keyed by — a custom row is a
-- fact about THIS card, not a fleet-wide registry entry like the fixed 13.
--
-- `certidao_resultados.linha_customizada_id` — an FK, NOT an id encoded
-- into `tipo` (owner directive: "prefer an FK column over encoding ids
-- into tipo"). A resultado recording a custom row's cell carries
-- `tipo = 'outras_custom'` (a fixed sentinel — `tipo` stays NOT NULL,
-- unchanged) PLUS `linha_customizada_id` naming WHICH custom row; every
-- other resultado carries `linha_customizada_id IS NULL`. The CHECK below
-- pins that pairing so a `tipo='outras_custom'` row can never exist
-- without naming its row, and no other `tipo` can accidentally claim one.
--
-- Recording a cell for a custom row goes through the EXACT SAME audited
-- manual-record path every other manual-only type already uses
-- (`POST /resultados/{id}/upload`, `PATCH /resultados/{id}`,
-- `confirmar_resultado`) — this migration adds no new write path, only the
-- placeholder row shape those existing endpoints already operate on.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. certidao_matriz_linhas_customizadas
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.certidao_matriz_linhas_customizadas (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    -- The CARD's titular — `atendimentos.cliente_id` — the same scope key
    -- `GET .../certidoes/matriz` already reads by. No FK to `atendimentos`
    -- (a card can outlive/change its open atendimento; the matriz endpoint
    -- itself re-resolves the atendimento live, this row just needs to
    -- survive that same way).
    cliente_id    UUID NOT NULL
                  REFERENCES social_wiring.clientes (id) ON DELETE CASCADE,
    nome          TEXT NOT NULL CHECK (btrim(nome) <> ''),

    -- 14, 15, 16, ... — the matriz row LABEL ("5.{ordem}"), assigned once
    -- at creation (MAX existing ordem for this cliente_id, including
    -- soft-deleted, + 1; never reused) so a later removal never renumbers
    -- a sibling row still on screen.
    ordem         INT NOT NULL,

    -- Soft-delete: the ROW DEFINITION stops appearing on the matriz: its
    -- own `certidao_resultados` rows are NEVER deleted (owner directive —
    -- "must NOT delete any recorded result").
    excluida_em   TIMESTAMPTZ,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    UUID,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.certidao_matriz_linhas_customizadas IS
    'Per-card ("+ Adicionar certidão") custom rows on the Certidões matriz '
    'tab, beyond the fixed 13 (5.1-5.13). Soft-deleted, never hard-deleted '
    '— its certidao_resultados rows outlive a removed row definition.';

CREATE INDEX IF NOT EXISTS idx_sw_certidao_matriz_linhas_cliente
    ON social_wiring.certidao_matriz_linhas_customizadas (cliente_id, ordem)
    WHERE excluida_em IS NULL;

ALTER TABLE social_wiring.certidao_matriz_linhas_customizadas
    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "certidao_matriz_linhas_select_own_org"
    ON social_wiring.certidao_matriz_linhas_customizadas;
CREATE POLICY "certidao_matriz_linhas_select_own_org"
    ON social_wiring.certidao_matriz_linhas_customizadas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_matriz_linhas_write_own_org"
    ON social_wiring.certidao_matriz_linhas_customizadas;
CREATE POLICY "certidao_matriz_linhas_write_own_org"
    ON social_wiring.certidao_matriz_linhas_customizadas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_matriz_linhas_service_role"
    ON social_wiring.certidao_matriz_linhas_customizadas;
CREATE POLICY "certidao_matriz_linhas_service_role"
    ON social_wiring.certidao_matriz_linhas_customizadas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. certidao_resultados — the FK a custom row's cell resultado points at
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS linha_customizada_id UUID
        REFERENCES social_wiring.certidao_matriz_linhas_customizadas (id);

COMMENT ON COLUMN social_wiring.certidao_resultados.linha_customizada_id IS
    'Migration 170. Set (with tipo=''outras_custom'') ONLY for a resultado '
    'recording a Certidões matriz custom row''s cell; NULL for every '
    'fixed-type resultado. See certidao_resultados_linha_customizada_par CHECK.';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'certidao_resultados_linha_customizada_par'
    ) THEN
        ALTER TABLE social_wiring.certidao_resultados
            ADD CONSTRAINT certidao_resultados_linha_customizada_par
            CHECK ((tipo = 'outras_custom') = (linha_customizada_id IS NOT NULL));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_linha_customizada
    ON social_wiring.certidao_resultados (linha_customizada_id)
    WHERE linha_customizada_id IS NOT NULL;
