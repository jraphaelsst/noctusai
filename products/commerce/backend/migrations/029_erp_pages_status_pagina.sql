-- 029_erp_pages_status_pagina.sql — status_pagina rows for the ERP W3-W4 back-office pages.
--
-- The seed layout hides any nav item whose `route` key has no `commerce.status_pagina` row
-- (filterNavByPageStatus), so the new "Gestão" entries (`products/commerce/frontend/src/App.tsx`, NAV_GROUPS) need
-- their rows. Vocabulary is the table's CHECK (001): producao | desenvolvimento | desativado.
--
--   compras      /api/purchasing  (025)
--   orcamentos   /api/quotes      (026)   (+ the public accept page /orcamento/:token, outside the authed shell)
--   contratos    /api/contracts   (027)
--
-- Their routers are mounted in this host (`app/routers/commerce_routers.py`), so every page is `producao`.
-- Forward-only + idempotent: a row an operator already flipped is never overwritten.

SET search_path = commerce, public;

INSERT INTO commerce.status_pagina (nome_pagina, status) VALUES
    ('compras', 'producao'),
    ('orcamentos', 'producao'),
    ('contratos', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
