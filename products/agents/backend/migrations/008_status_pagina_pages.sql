-- 008_status_pagina_pages.sql — page-visibility rows for the Julia agents UI
-- (contract §E, projects/julia-agents-academia-CONTRACT.md; G4 slice).
--
-- Every nav-listed route needs a matching agents.status_pagina row, or
-- `filterNavByPageStatus` (seed/lib/frontend/src/page-status.ts) hides it
-- from EVERYONE the moment any row exists in this table — "unlisted pages
-- are hidden" (KB § PATTERNS/frontend/status-pagina-dev-visibility.md).
-- `001_agents.sql` already seeded `dashboard` and `equipe` at 'producao';
-- this migration adds the three new pages this slice ships, at
-- 'desenvolvimento' — visible only to owner/dev/admin via the
-- `dev_veem_desenvolvimento` policy (005_status_pagina_dev_visibility.sql),
-- whose role array already matches the FE's `DEV_ROLES`
-- (seed/lib/frontend/src/roles.ts) — no new RLS policy needed here.
--
-- `/agentes/julia/persona` is reached via a link from the Agentes page (the
-- same pattern as Equipe's invite modal), not its own nav item, so it gets
-- no status_pagina row — it is gated purely by `useIsAdmin()` client-side
-- and `require_admin` server-side.
--
-- Forward-only + idempotent (ON CONFLICT DO NOTHING).

SET search_path = agents, public;

INSERT INTO agents.status_pagina (nome_pagina, status) VALUES
    ('julia', 'desenvolvimento'),
    ('agentes', 'desenvolvimento'),
    ('aprovacoes', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
