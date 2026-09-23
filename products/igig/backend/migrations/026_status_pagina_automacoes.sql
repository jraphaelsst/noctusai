-- ============================================================================
-- 026_status_pagina_automacoes.sql — register the Automações route
--
-- Slice F of `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-2-contract.md`
-- adds one sidebar entry: Automações (`/automacoes`, the rules editor + the
-- execuções log over slice E2's `/api/automacoes`). `filterNavByPageStatus`
-- HIDES an unlisted route once the table is non-empty (see 014), so a nav
-- entry without its row here would silently vanish from the sidebar.
--
-- The `marca` row (014) is deliberately left alone: the Marca sidebar entry
-- is gone (the Central da Marca moved into the cliente card) and `/marca` is
-- now a redirect to `/clientes` — a row for a route nobody links to is inert,
-- and deleting a status a human may have set is not this migration's call.
--
-- Naming: deliberately NOT `026_igig_*` — same reason as 014/024:
-- `status_pagina` is a framework table with no SQLite mirror
-- (`tests/test_schema_parity.py` requires a mirror only for `*_igig_*`
-- domain migrations).
--
-- Idempotent: ON CONFLICT DO NOTHING, so re-running never disturbs a status a
-- human has since changed (e.g. flipping the page to 'desenvolvimento').
-- ============================================================================
SET search_path = igig, public;

INSERT INTO igig.status_pagina (nome_pagina, status) VALUES
    ('automacoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
