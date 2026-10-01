-- ============================================================================
-- 183 — imovel_proprietarios: who owns an imóvel, as far as WE have registered
-- ============================================================================
-- Feeds the comprador page "Imóveis que possui", the roteiro PDF's
-- "proprietário", and permuta intro. Owner is a PF (cliente_id) XOR a PJ
-- (empresa_id). origem: manual | matricula | atendimento. One live row per
-- (imóvel, owner).
--
-- BACKFILL (SQL): origem='atendimento' from the VENDEDOR partes of every
-- atendimento × that atendimento's negociação imóvel. 🔴 NOT backfilled here
-- (left to the BE-imoveis slice, Python): matrícula owners matched by CPF —
-- they live inside `matricula_extracoes` structured JSON and need the same CPF
-- normalization the matrícula service already owns; re-implementing it in SQL
-- would fork it. That slice ships an idempotent backfill (origem='matricula').
--
-- Forward-only, idempotent. NOT applied to prod here.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_proprietarios (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    codigo      TEXT NOT NULL,
    cliente_id  UUID REFERENCES social_wiring.clientes (id) ON DELETE CASCADE,
    empresa_id  UUID REFERENCES social_wiring.empresas (id) ON DELETE CASCADE,
    origem      TEXT NOT NULL DEFAULT 'manual'
        CONSTRAINT imovel_proprietarios_origem_valida
        CHECK (origem IN ('manual', 'matricula', 'atendimento')),
    created_by  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ,
    CONSTRAINT imovel_proprietarios_pessoa_xor_empresa
        CHECK (num_nonnulls(cliente_id, empresa_id) = 1),
    CONSTRAINT imovel_proprietarios_registry_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_imovel_proprietarios_cliente_vivo
    ON social_wiring.imovel_proprietarios (codigo, cliente_id, org_id)
    WHERE cliente_id IS NOT NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_imovel_proprietarios_empresa_vivo
    ON social_wiring.imovel_proprietarios (codigo, empresa_id, org_id)
    WHERE empresa_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_imovel_proprietarios_cliente
    ON social_wiring.imovel_proprietarios (org_id, cliente_id)
    WHERE cliente_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_imovel_proprietarios_empresa
    ON social_wiring.imovel_proprietarios (org_id, empresa_id)
    WHERE empresa_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_imovel_proprietarios_codigo
    ON social_wiring.imovel_proprietarios (org_id, codigo)
    WHERE deleted_at IS NULL;

ALTER TABLE social_wiring.imovel_proprietarios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_proprietarios_select_own_org"
    ON social_wiring.imovel_proprietarios;
CREATE POLICY "imovel_proprietarios_select_own_org"
    ON social_wiring.imovel_proprietarios
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_proprietarios_service_role"
    ON social_wiring.imovel_proprietarios;
CREATE POLICY "imovel_proprietarios_service_role"
    ON social_wiring.imovel_proprietarios
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.imovel_proprietarios IS
    'Registered owners of an imóvel (PF xor PJ). origem: manual | matricula | '
    'atendimento. Migration 183.';

-- ── Backfill: vendedor partes × the atendimento's negociação imóvel ──────
INSERT INTO social_wiring.imovel_proprietarios
    (org_id, codigo, cliente_id, origem, created_at)
SELECT DISTINCT ON (p.cliente_id, r.codigo_canonical)
       p.org_id, r.codigo_canonical, p.cliente_id, 'atendimento', p.created_at
  FROM social_wiring.atendimento_partes p
  JOIN social_wiring.atendimento_negociacao n ON n.atendimento_id = p.atendimento_id
  JOIN social_wiring.imovel_registry r
    ON r.org_id = p.org_id AND r.codigo_canonical = upper(btrim(n.imovel_codigo))
 WHERE p.lado = 'vendedor'
   AND p.cliente_id IS NOT NULL
   AND btrim(COALESCE(n.imovel_codigo, '')) <> ''
 ORDER BY p.cliente_id, r.codigo_canonical, p.created_at
ON CONFLICT DO NOTHING;

NOTIFY pgrst, 'reload schema';
