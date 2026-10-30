-- 052_status_pagina_studio_drop.sql -- agents-unified wizard slice (2026-10-30).
--
-- The Agent Studio console (`/studio`) folded into the unified listing: create = the new-agent wizard
-- (`/agentes/novo`), import / delete / content token = actions on `/agentes`. `/studio` is now a redirect to
-- `/agentes` and its nav item is gone, so the `studio` status_pagina row (seeded by 012) gates nothing any more
-- -- the same cleanup 051 did for `bia` / `agentes-catalogo`. The Studio sub-pages (`/studio/biblioteca-skills`,
-- `/studio/prompts/:hash`) never had a row of their own.
--
-- Numbered by noctus.dev.next_migration_number (052 was unclaimed on disk, origin/dev and every local branch);
-- the agents chain must stay gap-free (tests/stores/test_migration_017_shape.py), so a slice that lands later
-- renumbers past this one (task_branch integrate re-checks collisions after its rebase).
-- Forward-only + idempotent (a re-run deletes nothing).
SET search_path = agents, public;

DELETE FROM agents.status_pagina WHERE nome_pagina = 'studio';
