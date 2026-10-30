-- 051_status_pagina_agentes_unificado.sql -- agents-unified CONTRACT §5/§7 (2026-10-29).
--
-- Every agent now lives on ONE listing (`/agentes`) and ONE page (`/agentes/:key`). The two nav items that
-- were per-agent / per-listing shells are gone from the nav: `Bia` (`/bia`, now a redirect to
-- `/agentes/bia?tab=conversar`) and `Catálogo de agentes` (`/agentes/catalogo`, now a redirect to `/agentes`).
-- Their status_pagina rows gate nothing any more; leaving them would be a stale nav-visibility row nobody reads.
-- The `agentes` row (the unified listing) is kept as is.
--
-- Forward-only + idempotent (a re-run deletes nothing).
SET search_path = agents, public;

DELETE FROM agents.status_pagina WHERE nome_pagina IN ('bia', 'agentes-catalogo');
