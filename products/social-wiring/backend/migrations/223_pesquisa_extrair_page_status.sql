-- ============================================================================
-- Migration 223 · social_wiring: nav gate for the new "Extrair Pesquisa" page
-- ============================================================================
-- WHY: contract projects/core-studio/specs/pesquisa-wave2-contract.md section
-- 4.1. filterNavByPageStatus hides any page absent from status_pagina, so the
-- Extrair page needs its row. 'desenvolvimento' = owner/dev-visible until the
-- owner validates the DRAFT extractor prompts (same stance as 217 for
-- 'media-creation-pesquisa').
--
-- FORWARD-ONLY, IDEMPOTENT. Data-only: no DDL.
-- ============================================================================

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('media-creation-pesquisa-extrair', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
