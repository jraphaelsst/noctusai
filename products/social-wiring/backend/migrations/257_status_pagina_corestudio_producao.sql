-- ============================================================================
-- Migration 257 · social_wiring: CoreStudio pages leave 'desenvolvimento'
-- ============================================================================
-- WHY
-- ---
-- Owner decision 2026-10-14: the CoreStudio surface (Esteira and the media-creation
-- pages) becomes visible to every org licensed for SW, like Branding/Carrosséis
-- already are. 11 pages move to 'producao'.
--
-- Deliberately KEPT in 'desenvolvimento':
--   * media-creation-biblioteca, media-creation-minha-biblioteca -- Biblioteca
--     ingestion is an open owner topic (kill switch biblioteca_ingestao_habilitada OFF).
--   * media-creation-treinamentos -- no lesson has a video yet (prod: 5 lessons,
--     0 with video_url); every lesson would show "Vídeo em produção".
--
-- FORWARD-ONLY, IDEMPOTENT (only rows still in 'desenvolvimento' move; a row an
-- admin already changed is left alone). Requires 241 (Esteira row) + the earlier
-- media-creation status rows. No CHECK / UNIQUE / trigger added, so no GuardProbe.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'media-creation-esteira') THEN
    RAISE EXCEPTION 'Migration 257 requires the media-creation-esteira status row (migration 241) -- apply 241 first';
  END IF;
END
$guard$;

UPDATE social_wiring.status_pagina
   SET status = 'producao'
 WHERE status = 'desenvolvimento'
   AND nome_pagina IN (
     'media-creation-dashboard',
     'media-creation-chat',
     'media-creation-cerebro',
     'media-creation-esteira',
     'media-creation-headlines-gerar',
     'media-creation-headlines-sugeridas',
     'media-creation-headlines-favoritas',
     'media-creation-perfil',
     'media-creation-pesquisa',
     'media-creation-pesquisa-extrair',
     'media-creation-roteiros'
   );
