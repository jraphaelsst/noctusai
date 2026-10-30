-- 311_status_pagina_leftovers.sql — page-visibility leftovers (planned-vs-shipped scan)
--
--   * clientes_revisao  — /clientes/revisao had NO status_pagina row, so the
--     nav hid it (filterNavByPageStatus: unlisted route => hidden).
--   * campanhas         — 065 created it 'desenvolvimento'; 218's insert was
--     ON CONFLICT DO NOTHING, so the page never reached 'producao'.
--   * atendimento_blocos / supervisao — 286 seeded 'desenvolvimento'; FE pages,
--     routes, nav entries and mounted backend routers all ship.
--   * portal_roi        — 043 seeded 'desenvolvimento'; page, route, nav entry
--     and router all ship.
--
-- FORWARD-ONLY, IDEMPOTENT (upsert on the nome_pagina UNIQUE key).
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('clientes_revisao',  'producao'),
    ('campanhas',         'producao'),
    ('atendimento_blocos','producao'),
    ('supervisao',        'producao'),
    ('portal_roi',        'producao')
ON CONFLICT (nome_pagina) DO UPDATE SET status = EXCLUDED.status;
