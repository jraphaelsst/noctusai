-- 043_status_pagina_financeiro_novo.sql -- status_pagina row for the seed finance organ page (/financeiro-novo).
--
-- The seed finance organ runs IN PARALLEL to the live agency finance ('financeiro', migration 011 + 014).
-- 'desenvolvimento' keeps the new page visible to owner/dev/admin only (005 policy) so it is not confused
-- with the live one. NOC-REMEDIATE[igig-finance-cutover]: flip to 'producao' (and retire 'financeiro')
-- once the importer has moved igig.fatura* into fin_entries -- 2026-10-14.
--
-- Naming: deliberately NOT `043_igig_*` -- that infix marks DOMAIN migrations needing a sqlite mirror
-- (tests/test_schema_parity.py); status_pagina is a framework table (same shape as 014).
-- Forward-only + idempotent.

SET search_path = igig, public;

INSERT INTO igig.status_pagina (nome_pagina, status) VALUES
    ('financeiro-novo', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
