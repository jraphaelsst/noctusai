-- status_pagina — the "Chaves de IA" nav page (`/chaves-ia`, Lais A3).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus`
-- hides it from EVERYONE (KB § PATTERNS/frontend/status-pagina-dev-visibility.md).
-- Seeded at 'desenvolvimento' — visible to owner/dev/admin via the existing
-- `dev_veem_desenvolvimento` policy (005), same as 008/010/012.
INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('chaves-ia', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
