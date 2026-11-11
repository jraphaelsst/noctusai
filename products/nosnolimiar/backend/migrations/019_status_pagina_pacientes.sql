-- status_pagina -- the patients pages (patient list/detail and the cross-patient agenda).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus` hides it from EVERYONE
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md). The route names are the `route` keys in
-- `products/monica/frontend/src/App.tsx`. Seeded at 'producao': the patients area is part of the product.
-- Forward-only + idempotent.
INSERT INTO monica.status_pagina (nome_pagina, status) VALUES
    ('pacientes', 'producao'),
    ('pacientes_agenda', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
