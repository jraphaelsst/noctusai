-- 021_instagram_insights_nav_route.sql — register /instagram-insights in status_pagina
--
-- The "Instagram Insights" page (frontend v1) is gated by the seed
-- filterNavByPageStatus rule: without a status_pagina row the nav item is
-- silently hidden. Seeded as 'desenvolvimento' (not 'producao') on purpose —
-- the page renders + the "Conectar Instagram" flow works, but the numbers are
-- not proven against a live Meta connection yet, so it stays owner/admin/dev-
-- visible only until the connection is validated end-to-end. Flip to
-- 'producao' (a one-line status_pagina PATCH via the Visibilidade tab, or a
-- follow-up migration) once real metrics are confirmed.
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('instagram_insights', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
