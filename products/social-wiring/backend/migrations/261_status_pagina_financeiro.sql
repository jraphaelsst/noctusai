-- 261_status_pagina_financeiro.sql -- status_pagina row for the seed finance organ page (/financeiro).
--
-- The seed layout hides any nav item whose `route` key has no `social_wiring.status_pagina` row
-- (filterNavByPageStatus), so the Financeiro entry needs its row. 'producao' per the roadmap
-- (erp-seed-2026-10 E10-E11): the organ is the same one commerce mounts; the page is admin-gated.
--
-- Forward-only + idempotent (ON CONFLICT DO NOTHING leaves a status a human has since changed alone).
-- Requires 260_finance.sql only for the page to have something to show; no dependency in SQL.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('financeiro', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
