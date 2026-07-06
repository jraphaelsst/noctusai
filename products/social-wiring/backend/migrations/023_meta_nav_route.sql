-- 023_meta_nav_route.sql — register /meta in status_pagina
--
-- The remodeled Meta dashboard (Instagram + Facebook, Wave 3) replaces the
-- flat "Instagram Insights" page at `/instagram-insights`. Seeded as
-- 'desenvolvimento' (not 'producao') on purpose — same posture as the
-- 021_instagram_insights_nav_route.sql predecessor: the shell + subtabs
-- render + the connect flow works, but the new account-scoped /api/meta/*
-- endpoints (Wave 3 backend slice) aren't proven end-to-end against a live
-- Meta connection yet. Flip to 'producao' once confirmed.
--
-- The `instagram_insights` status_pagina row is intentionally LEFT AS-IS —
-- the route now redirects to /meta client-side, so a status_pagina flip is
-- unnecessary (the row is simply unused by any live nav item going forward).
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('meta', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
