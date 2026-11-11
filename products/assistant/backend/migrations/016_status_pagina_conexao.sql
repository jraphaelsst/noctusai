-- status_pagina -- the "Conexão" nav page (`/conexao`, the WhatsApp pairing page).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus` hides it from EVERYONE
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md). Forward-only + idempotent.
INSERT INTO assistant.status_pagina (nome_pagina, status) VALUES
    ('conexao', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
