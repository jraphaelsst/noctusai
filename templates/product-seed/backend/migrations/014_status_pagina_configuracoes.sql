-- status_pagina -- the "Configurações" nav page (`/configuracoes/*`, seed `SectionTabsPage`).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus` hides it from EVERYONE
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md). Seeded at 'producao'.
-- Forward-only + idempotent.
INSERT INTO {{SCHEMA_NAME}}.status_pagina (nome_pagina, status) VALUES
    ('configuracoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
