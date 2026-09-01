-- ============================================================================
-- 014_status_pagina_rotas.sql — register every shipped route in status_pagina
--
-- WHY. `filterNavByPageStatus` treats an unlisted route as HIDDEN
-- (`seed/lib/frontend/src/page-status.ts`: "if (!page) return false"), and the
-- layout only falls back to the unfiltered nav when the status list comes back
-- EMPTY. IgIg had exactly two rows — 'dashboard' and 'equipe' — from `001`,
-- while the product grew to eleven pages. That left the product one row away
-- from a fleet-visible outage: the moment any third row was inserted, the list
-- became non-empty, filtering switched on, and the nine unregistered pages
-- (Comercial, Clientes, Esteira, Marca, Calendário, Distribuição, Financeiro,
-- Integrações, Custos) would have vanished from the sidebar for everyone.
--
-- The nav rendering correctly today was therefore an accident of the table
-- being under-populated, not evidence that it was configured. This makes the
-- registration match the shipped routes.
--
-- Naming: deliberately NOT `014_igig_*`. That infix marks DOMAIN migrations,
-- which `tests/test_schema_parity.py` requires to have a `migrations/sqlite/`
-- mirror. `status_pagina` is a framework table declared in `001`, is read
-- straight from Supabase by the frontend rather than through the persistence
-- seam, and has no SQLite counterpart — same shape as `005` and `013`.
--
-- Idempotent: ON CONFLICT DO NOTHING, so re-running never disturbs a status a
-- human has since changed (e.g. flipping a page to 'desenvolvimento').
-- ============================================================================
SET search_path = igig, public;

INSERT INTO igig.status_pagina (nome_pagina, status) VALUES
    ('comercial',    'producao'),
    ('clientes',     'producao'),
    ('esteira',      'producao'),
    ('marca',        'producao'),
    ('calendario',   'producao'),
    ('distribuicao', 'producao'),
    ('financeiro',   'producao'),
    ('integracoes',  'producao'),
    ('custos',       'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- The seed's placeholder CRUD page. It shipped in the production nav of a
-- live agency ERP alongside its `/api/example` router; both are removed. The
-- delete is here so an environment that had already registered it does not
-- keep advertising a route the SPA no longer serves.
DELETE FROM igig.status_pagina WHERE nome_pagina = 'example';
