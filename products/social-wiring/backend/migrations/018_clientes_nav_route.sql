-- 018_clientes_nav_route.sql — Wave 2 FE: register /clientes route in status_pagina
--
-- The "Clientes" page is the primary connections surface introduced by the
-- "clientes own their connections" initiative (Wave 2). Without this row the
-- seed filterNavByPageStatus gate hides the nav item silently.
--
-- The "Chat WhatsApp" (whatsapp_chat) route is KEPT in status_pagina (added by
-- migration 014) — the route remains live for back-compat even though its nav
-- entry is removed in Wave 2. No deletion needed.
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('clientes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
