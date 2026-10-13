-- 013_admin_pages_status_pagina.sql — status_pagina rows for the back-office menu.
--
-- The seed layout hides any nav item whose `route` key has no
-- `commerce.status_pagina` row (filterNavByPageStatus). P3 slice D's back office
-- (`products/commerce/frontend/src/App.tsx`, NAV_GROUPS) uses these keys; only
-- `equipe` existed (001). CONTRACT-DELTAS D6.
--
-- 'desenvolvimento' per the status-pagina dev-visibility pattern
-- (KB § PATTERNS/frontend/status-pagina-dev-visibility.md): the product is
-- deploy_scope=dev until gate T2, so the pages show to owner/dev/admin through
-- the `dev_veem_desenvolvimento` policy (005) and to no one else. Promote to
-- 'producao' at T2.
--
-- Forward-only + idempotent.

SET search_path = commerce, public;

INSERT INTO commerce.status_pagina (nome_pagina, status) VALUES
    ('pedidos', 'desenvolvimento'),
    ('clientes', 'desenvolvimento'),
    ('cupons', 'desenvolvimento'),
    ('produtos', 'desenvolvimento'),
    ('categorias', 'desenvolvimento'),
    ('loja', 'desenvolvimento'),
    ('enderecos', 'desenvolvimento'),
    ('integracoes', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
