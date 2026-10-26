-- 030_status_pagina_configuracoes.sql -- status_pagina row for the consolidated "Configurações" back-office page.
--
-- The three settings pages (loja / enderecos / integracoes) became tabs of one page, `/admin/configuracoes/*`
-- (seed `SectionTabsPage`), so the nav lists ONE entry with route key `configuracoes`. The seed layout hides any
-- nav item whose `route` key has no `commerce.status_pagina` row (filterNavByPageStatus), so it needs its row.
-- The old rows (loja, enderecos, integracoes) are left in place: harmless, and an operator's flip stays on record.
-- Forward-only + idempotent.
INSERT INTO commerce.status_pagina (nome_pagina, status) VALUES
    ('configuracoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
