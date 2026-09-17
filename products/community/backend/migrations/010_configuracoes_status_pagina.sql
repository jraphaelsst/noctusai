-- ============================================================================
-- Seed pages — `/configuracoes` nav entry (community-fe-apikeys-conexoes
-- slice). Visible to every authenticated member at 'producao' — the
-- "Chaves de API" content on that page is gated in-page by `isAdmin`
-- (Configuracoes.tsx), not by hiding the nav item; same convention
-- social-wiring's own `configuracoes` row uses.
--
-- `/whatsapp/conexoes` (Conexoes.tsx, the new WAHA connection admin
-- surface) is deliberately NOT added here — it is not in NAV_GROUPS
-- (linked from `/whatsapp`'s own banner instead), so it needs no
-- `status_pagina` row per `page-status.ts`'s contract (only routes with a
-- `route` key in `NAV_GROUPS` are looked up).
-- ============================================================================

INSERT INTO community.status_pagina (nome_pagina, status) VALUES
    ('configuracoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
