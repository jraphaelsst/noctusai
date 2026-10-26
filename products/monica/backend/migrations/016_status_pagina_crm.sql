-- status_pagina -- the CRM nav pages (leads funnel + list, conversations, context, settings > connections).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus` hides it from EVERYONE
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md). The route names are the `route` keys in
-- `products/monica/frontend/src/App.tsx`. Seeded at 'producao': these ARE the product.
-- Forward-only + idempotent.
INSERT INTO monica.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('leads', 'producao'),
    ('leads_lista', 'producao'),
    ('conversas', 'producao'),
    ('contexto', 'producao'),
    ('conexoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
