-- 009_status_pagina_pages.sql — register the A3 (academia UI) routes in
-- status_pagina so they render for dev/owner/admin while the API + import
-- slices land in parallel (slice A2 / A3, roadmap
-- `project-history/roadmaps/julia-agents-academia-2026-09.md`).
--
-- WHY 'desenvolvimento', not 'producao': `isPageVisible()`
-- (seed/lib/frontend/src/page-status.ts) treats an UNLISTED route as
-- hidden from everyone, and a `desenvolvimento` row is visible only to
-- dev/owner/admin via the `dev_veem_desenvolvimento` policy already shipped
-- in 005_status_pagina_dev_visibility.sql (RLS role source:
-- public.current_org_role(), never user_metadata). No RLS change needed
-- here — that policy is generic over every 'desenvolvimento' row, not
-- page-specific.
--
-- Insert shape copied from 001_academia-de-reciclagem.sql's own seed block
-- (`INSERT ... ON CONFLICT (nome_pagina) DO NOTHING`).
--
-- `nome_pagina` values MUST equal the `route` field on each NavItemWithRoute
-- in `frontend/src/App.tsx`'s NAV_GROUPS — that is the join key
-- `isPageVisible()` reads.
--
-- Forward-only + idempotent. Not applied by this slice (frontend-only) —
-- the tech-lead applies it alongside the A2 backend routes.

INSERT INTO academia_de_reciclagem.status_pagina (nome_pagina, status) VALUES
    ('kb', 'desenvolvimento'),
    ('decisoes', 'desenvolvimento'),
    ('perguntas', 'desenvolvimento'),
    ('roadmap', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
