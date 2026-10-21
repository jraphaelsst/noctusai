-- status_pagina -- the "Opt-outs" nav page (`/opt-outs`: leads that asked to stop being contacted).
-- Every nav-listed route needs a matching row, or `filterNavByPageStatus` hides it from EVERYONE
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md). Seeded at 'producao': it is where the owner's
-- in-app notice lands (metadata.link = /opt-outs?evento=<id>), so it must be visible to the people notified.
-- Forward-only + idempotent.
INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('opt-outs', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
