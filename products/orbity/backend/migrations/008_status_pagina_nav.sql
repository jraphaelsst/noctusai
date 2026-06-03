-- ============================================================================
-- Migration 008 — Orbity nav pages: status_pagina rows for the FE modules
--
-- The sidebar nav is gated by the seed's filterNavByPageStatus / isPageVisible:
-- a route with NO orbity.status_pagina row is SILENTLY HIDDEN. Migration 001
-- seeded dashboard + equipe; this seeds the module pages shipped by the
-- Financial / CRM / Tasks+Agenda FE waves so their sidebar links appear.
--
-- status='producao' = visible to all roles. (desenvolvimento = owner/dev only.)
-- IDEMPOTENT: ON CONFLICT (nome_pagina) DO NOTHING.
-- ============================================================================

INSERT INTO orbity.status_pagina (nome_pagina, status) VALUES
    ('financeiro', 'producao'),   -- Financial hub (contracts/expenses/revenues/cash-flow)
    ('clientes',   'producao'),   -- CRM: clients
    ('funil',      'producao'),   -- CRM: leads funnel kanban
    ('tarefas',    'producao'),   -- Tasks board
    ('agenda',     'producao'),   -- Agenda / calendar
    ('rotinas',    'producao')    -- Recurring routines
ON CONFLICT (nome_pagina) DO NOTHING;
