-- 039_n8n_nav_route.sql — register /n8n in status_pagina
--
-- The `/n8n` workflows page (client folder tree + drag-and-drop workflow
-- assignment) ships its route as `route: "n8n"` in App.tsx's NAV_GROUPS
-- (products/social-wiring/frontend/src/App.tsx, feat/n8n-page-ui @
-- 3ac27a79). Without a matching status_pagina row the seed
-- filterNavByPageStatus gate hides the nav item silently — the page and
-- route work fine if you type the URL, but the sidebar link never
-- appears. Same silent-failure shape 018/021/023 exist to close.
--
-- Seeded as 'desenvolvimento' (not 'producao') — same posture as
-- 021_instagram_insights_nav_route.sql / 023_meta_nav_route.sql: this is a
-- multi-slice feature still landing across several concurrent engineer
-- worktrees (folder-tree migration, backend module, seed adapter, page UI),
-- not yet proven end-to-end against a live n8n instance. Flip to
-- 'producao' once confirmed.
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('n8n', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
