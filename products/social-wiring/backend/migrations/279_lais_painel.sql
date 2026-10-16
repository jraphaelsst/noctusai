-- ============================================================================
-- Migration 279 -- social_wiring: Lais wave 9 "Painel" (Inicio) -- status_pagina + read indexes
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 11 (wave 9) +
--   specs/page-map-v2.md "Inicio". `GET /api/lais/painel?mes=` aggregates, per org and month (edges in
--   America/Sao_Paulo), lais_contatos (funnel + charts), lais_eventos (cobrancas) and lais_visitas
--   (pre-agendamentos). The aggregation is done in the service (A7 member scoping is a rule over two tables,
--   not expressible in a view), so no views and no new tables: only the month-window read indexes it needs
--   and the status_pagina row.
--     * lais_contatos  (org_id, created_at)  -- already idx_lais_contatos_org_criado (270, DESC); not repeated
--     * lais_eventos   (org_id, tipo, created_at)
--     * lais_visitas   (org_id, created_at)
--
-- No new table / policy / function: NO RLS change, NO SECURITY DEFINER.
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 014 (status_pagina), 267 (lais_eventos), 272 (lais_visitas).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.lais_eventos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_eventos (migration 267) -- apply 267 first';
  END IF;
  IF to_regclass('social_wiring.lais_visitas') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_visitas (migration 272) -- apply 272 first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'this migration requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

CREATE INDEX IF NOT EXISTS idx_lais_eventos_org_tipo_created
    ON social_wiring.lais_eventos (org_id, tipo, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lais_visitas_org_created
    ON social_wiring.lais_visitas (org_id, created_at DESC);

-- status_pagina: Lais > Inicio / Painel (copies whatsapp_chat, like 259 / 270 / 272)
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_painel', 'Lais — Painel (Início)')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
