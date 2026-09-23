-- ============================================================================
-- 024_status_pagina_orcamentos_produtos.sql — register the two wave-2 routes
--
-- Slice C of `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-2-contract.md`
-- adds two sidebar entries under Clientes: Orçamentos (`/orcamentos`) and
-- Produtos e Serviços (`/produtos-servicos`). `filterNavByPageStatus` HIDES an
-- unlisted route once the table is non-empty (see 014), so a nav entry without
-- its row here would silently vanish from the sidebar.
--
-- Naming: deliberately NOT `024_igig_*` — same reason as 014: `status_pagina`
-- is a framework table with no SQLite mirror (`tests/test_schema_parity.py`
-- requires a mirror only for `*_igig_*` domain migrations).
--
-- Idempotent: ON CONFLICT DO NOTHING, so re-running never disturbs a status a
-- human has since changed (e.g. flipping a page to 'desenvolvimento').
-- ============================================================================
SET search_path = igig, public;

INSERT INTO igig.status_pagina (nome_pagina, status) VALUES
    ('orcamentos',         'producao'),
    ('produtos_servicos',  'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
