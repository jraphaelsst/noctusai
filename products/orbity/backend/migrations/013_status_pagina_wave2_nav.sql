-- ============================================================================
-- Migration 013 — Orbity nav pages: status_pagina rows for Wave-2 modules
--
-- The sidebar nav is gated by the seed's filterNavByPageStatus / isPageVisible:
-- a route with NO orbity.status_pagina row is SILENTLY HIDDEN. Migration 008
-- seeded the Financial / CRM / Tasks+Agenda wave; this seeds the Wave-2 module
-- pages (Tráfego / Automação / Conteúdo / Relatórios) so their sidebar links
-- appear.
--
-- NOTE: These rows are already live in the prod/dev DB (applied manually).
-- This migration exists for fresh-DB reproducibility only. Tech-lead does NOT
-- need to re-apply.
--
-- status='producao' = visible to all roles. (desenvolvimento = owner/dev only.)
-- IDEMPOTENT: ON CONFLICT (nome_pagina) DO NOTHING.
-- ============================================================================

INSERT INTO orbity.status_pagina (nome_pagina, status) VALUES
    ('trafego',    'producao'),   -- Meta Ads / Tráfego module
    ('automacao',  'producao'),   -- Automation module
    ('conteudo',   'producao'),   -- Content / Social Studio module
    ('relatorios', 'producao')    -- Reports module
ON CONFLICT (nome_pagina) DO NOTHING;
