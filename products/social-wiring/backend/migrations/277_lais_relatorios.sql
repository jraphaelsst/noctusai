-- ============================================================================
-- 277_lais_relatorios.sql -- Lais wave 10 "Relatorios" (contract section 12)
--
-- The page is a read-side aggregation over tables that already exist (lais_contatos / lais_interacoes /
-- lais_visitas / lais_acoes_aplicadas / imoveis), so this migration only adds:
--   1. the status_pagina row `lais_relatorios` (without it the nav item is invisible), copying the
--      status of `whatsapp_chat` like 259/273/275;
--   2. two supporting indexes for the month-window scans of the report.
--
-- FORWARD-ONLY, IDEMPOTENT. Applied by the tech-lead with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.lais_interacoes') IS NULL OR to_regclass('social_wiring.lais_visitas') IS NULL THEN
    RAISE EXCEPTION 'this migration requires 267 (lais_interacoes) and 272 (lais_visitas)';
  END IF;
END
$guard$;

CREATE INDEX IF NOT EXISTS idx_lais_interacoes_org_iniciada
    ON social_wiring.lais_interacoes (org_id, iniciada_at DESC);
CREATE INDEX IF NOT EXISTS idx_lais_visitas_org_created
    ON social_wiring.lais_visitas (org_id, created_at DESC);

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('lais_relatorios', 'Lais — Relatórios')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
