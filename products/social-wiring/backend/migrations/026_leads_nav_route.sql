-- 026_leads_nav_route.sql — register /leads in status_pagina
--
-- Without this row `filterNavByPageStatus` (seed nav gate) hides the new
-- "Leads" nav item silently — same contract as 018_clientes_nav_route.sql /
-- 023_meta_nav_route.sql. Seeded as 'producao': the CRUD + import surface
-- is the primary deliverable of this module (not a preview/soft-launch).
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('leads', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
