-- status_pagina -- the "Financeiro" nav page (`/financeiro`, finance organ mount).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus` hides it from EVERYONE
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md). Seeded at 'producao'.
-- Forward-only + idempotent.
INSERT INTO monica.status_pagina (nome_pagina, status) VALUES
    ('financeiro', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
