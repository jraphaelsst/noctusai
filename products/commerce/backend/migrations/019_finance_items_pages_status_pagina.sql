-- 019_finance_items_pages_status_pagina.sql — status_pagina rows for the P4 / ERP W1-W2 back-office pages.
--
-- The seed layout hides any nav item whose `route` key has no `commerce.status_pagina` row
-- (filterNavByPageStatus), so the new menu entries (`products/commerce/frontend/src/App.tsx`, NAV_GROUPS) need
-- their rows. Vocabulary is the table's CHECK (001): producao | desenvolvimento | desativado.
--
--   financeiro  producao         finance + reconciliation are mounted at /api/finance (017) — page is live
--   itens       producao         items catalog is mounted at /api/items (018) — page is live
--   parceiros   desenvolvimento  /api/parties is NOT mounted in this host yet (page built, backend pending)
--   estoque     desenvolvimento  /api/inventory is NOT mounted in this host yet (page built, backend pending)
--
-- NOC-REMEDIATE[commerce-parties-inventory-mount]: mount make_parties_router / make_inventory_router in
-- products/commerce/backend/app/main.py (+ their migrations), then promote `parceiros` and `estoque` to
-- 'producao' in a follow-up migration — 2026-10-14. Until then 'desenvolvimento' shows them to owner/dev/admin only
-- (dev_veem_desenvolvimento, 005) so nobody else lands on a page whose API answers 404.
--
-- Forward-only + idempotent: a row an operator already flipped is never overwritten.

SET search_path = commerce, public;

INSERT INTO commerce.status_pagina (nome_pagina, status) VALUES
    ('financeiro', 'producao'),
    ('itens', 'producao'),
    ('parceiros', 'desenvolvimento'),
    ('estoque', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
