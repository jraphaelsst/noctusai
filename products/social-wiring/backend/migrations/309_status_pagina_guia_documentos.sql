-- Migration: status_pagina_guia_documentos
-- Schema: social_wiring
--
-- "Guia de documentos" (`/guia-documentos`): one read-only page listing which
-- data each document supplies, what each certidão requires and the lead flow's
-- per-stage demands — derived from code catalogs by GET /api/guia-documentos.
-- The nav entry is gated by status_pagina (filterNavByPageStatus); without a
-- row the entry is silently hidden. Seeded 'producao': the page is a help
-- surface for every operator (owner ask 2026-10-26), it writes nothing.
-- FORWARD-ONLY, IDEMPOTENT.

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.status_pagina') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.status_pagina (migration 001) -- apply 001 first';
  END IF;
END
$guard$;

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
VALUES ('guia_documentos', 'producao', 'Guia de documentos — dados por documento, requisitos das certidões e fluxo do lead')
ON CONFLICT (nome_pagina) DO NOTHING;
