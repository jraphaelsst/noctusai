-- 069_status_pagina_agentes_plataforma.sql — page-visibility row for `/agentes-plataforma`
-- (Studio "Agentes da plataforma": the platform's internal AI calls, vendor + model + prompt).
-- Unlisted nav pages are hidden from everyone (`filterNavByPageStatus`), so the nav item needs this row.
-- 'desenvolvimento' = owner/dev/admin only, matching `dev_veem_desenvolvimento` (005). The page itself is
-- server-gated by `require_platform_admin`. Forward-only + idempotent.

SET search_path = agents, public;

INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('agentes-plataforma', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
