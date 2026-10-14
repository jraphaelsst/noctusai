-- 019_finance_items_pages_status_pagina.sql — status_pagina rows for the P4 / ERP back-office pages.
--
-- The seed layout hides any nav item whose `route` key has no `commerce.status_pagina` row
-- (filterNavByPageStatus), so the new menu entries (`products/commerce/frontend/src/App.tsx`, NAV_GROUPS) need
-- their rows. Vocabulary is the table's CHECK (001): producao | desenvolvimento | desativado.
--
--   financeiro  /api/finance     (017)        itens      /api/items      (018)
--   parceiros   /api/parties     (020)        estoque    /api/inventory  (021)
--
-- Their routers are mounted in this host, so every page is `producao`. (`compras` / purchasing, `orcamentos` and
-- `contratos` follow in 029.) Forward-only + idempotent: a row an
-- operator already flipped is never overwritten.

SET search_path = commerce, public;

INSERT INTO commerce.status_pagina (nome_pagina, status) VALUES
    ('financeiro', 'producao'),
    ('itens', 'producao'),
    ('parceiros', 'producao'),
    ('estoque', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
