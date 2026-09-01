-- 084_agendamentos_nav_route.sql — register /agendamentos in status_pagina
--
-- The `scheduling` module (Wave 2.3, absorbed real-estate scheduling) shipped
-- 15 HTTP endpoints and NO frontend at all — condominiums / properties /
-- services / users CRUD, the appointment + appointment-request reads, the
-- pending-chat-identity resolve, and POST /propose were reachable only by
-- hand-issuing HTTP calls. The 2026-09-01 endpoint-to-UI parity sweep found
-- it as the second-largest unsurfaced module in the product.
--
-- `products/social-wiring/frontend/src/pages/scheduling/Agendamentos.tsx` is
-- that frontend, declared in App.tsx NAV_GROUPS as `route: "agendamentos"`.
-- Without a matching status_pagina row the seed `filterNavByPageStatus` gate
-- hides the nav item silently — the route works if you type the URL, but the
-- sidebar link never appears. Same silent-failure shape 018/021/023/039 exist
-- to close.
--
-- Seeded 'producao' (not 'desenvolvimento'): unlike 021/023/039 this is not a
-- multi-slice feature still landing. The backend has been live and tested for
-- months; only the UI was missing, and it ships complete (all four states on
-- every list, page-scoped CRUD via the canonical ResourceManager organ) and
-- verified end-to-end against the live API before this migration is applied.
--
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('agendamentos', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
