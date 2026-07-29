-- 035_meta_pages_producao.sql — promote `meta` + `instagram_insights` to 'producao'
--
-- Both rows were seeded 'desenvolvimento' (023_meta_nav_route.sql,
-- 021_instagram_insights_nav_route.sql) while the surfaces were being built.
-- They shipped long ago — the whole Anúncios console (Visão geral / Campanhas /
-- Histórico / Financeiro / Leads), IG Conteúdo and IG Visão geral are live and
-- were smoke-tested against real data on 2026-07-26 — but the nav rows never
-- followed, so `filterNavByPageStatus` kept them owner-only in production.
--
-- 🔴 The gate is stricter than it reads. `status_pagina` carries ONE RLS
-- SELECT policy (`todos_veem_producao`, `status = 'producao'`) and the FE
-- reads through the authenticated product client, so a 'desenvolvimento' row
-- is returned to NOBODY — not even to an owner. `isPageVisible`'s
-- dev/owner branch is unreachable dead code today. Promoting these two rows
-- makes both pages visible to every member of the org, which is the intent;
-- repairing the dev-visibility branch itself is a separate, wider change
-- (it needs a second additive RLS policy keyed on a server-owned role, plus
-- the seed FE role const) and is tracked on
-- `project-history/roadmaps/ig-login-messaging-migration-2026-07.md`.
--
-- Idempotent: an UPDATE to a value a row may already hold. Scoped by name so
-- it can never promote a page that was deliberately parked.

SET search_path = social_wiring, public;

UPDATE social_wiring.status_pagina
   SET status = 'producao'
 WHERE nome_pagina IN ('meta', 'instagram_insights')
   AND status <> 'producao';
