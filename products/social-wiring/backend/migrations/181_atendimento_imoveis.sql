-- ============================================================================
-- 181 — atendimento_imoveis: the imóveis an atendimento is about (junction)
-- ============================================================================
-- Until now an atendimento reached an imóvel by two free-text códigos: the
-- originating lead's `codigo_imovel_norm` and `atendimento_negociacao.
-- imovel_codigo` ("the one under negotiation"). PROJECT.md §3.3: a real
-- junction. `atendimento_negociacao.imovel_codigo` stays "the one under
-- negotiation" and must be ∈ this junction — that invariant is SERVICE-enforced
-- (BE-imoveis), not a DB trigger, because the negociação row is created lazily.
--
-- origem: lead | manual | campanha | negociacao — how the link came to be.
-- principal: at most ONE live principal per atendimento (partial unique index).
-- Soft delete (deleted_at): removing a link must not erase that it existed.
--
-- BACKFILL (SQL, no Python follow-up needed): every atendimento's originating
-- lead / meta lead código (origem='lead') and negociação código
-- (origem='negociacao'), after registering any not-yet-registered código the
-- way `registrar_imovel` does (origem_descoberta lead|manual, ativo_no_vista
-- FALSE, ON CONFLICT DO NOTHING). Principal = the negociação código when one
-- exists, else the lead código. Rows with no código simply get no junction row:
-- `imovel_pendente` is DERIVED ("atendimento with zero live junction rows"),
-- never stored.
--
-- Forward-only, idempotent. NOT applied to prod here.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.atendimento_imoveis (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,
    codigo         TEXT NOT NULL,
    origem         TEXT NOT NULL DEFAULT 'manual'
        CONSTRAINT atendimento_imoveis_origem_valida
        CHECK (origem IN ('lead', 'manual', 'campanha', 'negociacao')),
    principal      BOOLEAN NOT NULL DEFAULT FALSE,
    created_by     UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at     TIMESTAMPTZ,
    CONSTRAINT atendimento_imoveis_registry_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimento_imoveis_vivo
    ON social_wiring.atendimento_imoveis (atendimento_id, codigo)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimento_imoveis_principal
    ON social_wiring.atendimento_imoveis (atendimento_id)
    WHERE principal AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_imoveis_codigo
    ON social_wiring.atendimento_imoveis (org_id, codigo)
    WHERE deleted_at IS NULL;

ALTER TABLE social_wiring.atendimento_imoveis ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_imoveis_select_own_org"
    ON social_wiring.atendimento_imoveis;
CREATE POLICY "atendimento_imoveis_select_own_org"
    ON social_wiring.atendimento_imoveis
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_imoveis_service_role"
    ON social_wiring.atendimento_imoveis;
CREATE POLICY "atendimento_imoveis_service_role"
    ON social_wiring.atendimento_imoveis
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.atendimento_imoveis IS
    'Imóveis an atendimento is about. origem says how the link arose; at most '
    'one live principal per atendimento. `imovel_pendente` = an atendimento '
    'with no live row here (derived, not stored). Migration 181.';

-- ── Backfill ────────────────────────────────────────────────────────────
-- 1. Register códigos we have never seen (negociação ones; lead/meta ones were
--    registered by 063/180).
INSERT INTO social_wiring.imovel_registry (
    org_id, codigo_canonical, codigo_display, primeiro_visto_em,
    ativo_no_vista, origem_descoberta
)
SELECT n.org_id, upper(btrim(n.imovel_codigo)), btrim(n.imovel_codigo),
       min(n.created_at), FALSE, 'manual'
  FROM social_wiring.atendimento_negociacao n
 WHERE btrim(COALESCE(n.imovel_codigo, '')) <> ''
 GROUP BY n.org_id, upper(btrim(n.imovel_codigo)), btrim(n.imovel_codigo)
ON CONFLICT (org_id, codigo_canonical) DO NOTHING;

-- 2. Lead-origin links (leads.codigo_imovel_norm, meta_ads_leads.codigo_imovel_norm).
INSERT INTO social_wiring.atendimento_imoveis
    (org_id, atendimento_id, codigo, origem, principal, created_at)
SELECT a.org_id, a.id, r.codigo_canonical, 'lead', FALSE, a.created_at
  FROM social_wiring.atendimentos a
  LEFT JOIN social_wiring.leads l ON l.id = a.lead_id
  LEFT JOIN social_wiring.meta_ads_leads m ON m.id = a.meta_ads_lead_id
  JOIN social_wiring.imovel_registry r
    ON r.org_id = a.org_id
   AND r.codigo_canonical = COALESCE(l.codigo_imovel_norm, m.codigo_imovel_norm)
ON CONFLICT DO NOTHING;

-- 3. Negociação links. If the código is already linked via the lead, it is
--    upgraded to origem='negociacao' (the stronger statement).
INSERT INTO social_wiring.atendimento_imoveis
    (org_id, atendimento_id, codigo, origem, principal, created_at)
SELECT n.org_id, n.atendimento_id, r.codigo_canonical, 'negociacao', FALSE, n.created_at
  FROM social_wiring.atendimento_negociacao n
  JOIN social_wiring.imovel_registry r
    ON r.org_id = n.org_id AND r.codigo_canonical = upper(btrim(n.imovel_codigo))
 WHERE btrim(COALESCE(n.imovel_codigo, '')) <> ''
ON CONFLICT DO NOTHING;

UPDATE social_wiring.atendimento_imoveis ai
   SET origem = 'negociacao'
  FROM social_wiring.atendimento_negociacao n
 WHERE n.atendimento_id = ai.atendimento_id
   AND upper(btrim(n.imovel_codigo)) = ai.codigo
   AND ai.deleted_at IS NULL
   AND ai.origem <> 'negociacao';

-- 4. Principal: the negociação código when linked, else the oldest link.
UPDATE social_wiring.atendimento_imoveis ai
   SET principal = TRUE
  FROM social_wiring.atendimento_negociacao n
 WHERE n.atendimento_id = ai.atendimento_id
   AND upper(btrim(n.imovel_codigo)) = ai.codigo
   AND ai.deleted_at IS NULL
   AND NOT EXISTS (SELECT 1 FROM social_wiring.atendimento_imoveis p
                    WHERE p.atendimento_id = ai.atendimento_id
                      AND p.principal AND p.deleted_at IS NULL);

UPDATE social_wiring.atendimento_imoveis ai
   SET principal = TRUE
 WHERE ai.deleted_at IS NULL
   AND ai.id = (SELECT x.id FROM social_wiring.atendimento_imoveis x
                 WHERE x.atendimento_id = ai.atendimento_id AND x.deleted_at IS NULL
                 ORDER BY x.created_at, x.codigo LIMIT 1)
   AND NOT EXISTS (SELECT 1 FROM social_wiring.atendimento_imoveis p
                    WHERE p.atendimento_id = ai.atendimento_id
                      AND p.principal AND p.deleted_at IS NULL);

NOTIFY pgrst, 'reload schema';
