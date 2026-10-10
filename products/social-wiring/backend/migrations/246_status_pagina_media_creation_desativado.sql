-- ============================================================================
-- Migration 246 · social_wiring: retire the legacy "Criação de mídia" page (status desativado)
-- ============================================================================
-- WHY
-- ---
-- Esteira contract §A, step A-3. The legacy /media-creation page's tabs were absorbed by CoreStudio
-- (Biblioteca + Novo post → /media-creation/carrosseis, Branding → /media-creation/branding; FE-A),
-- the page component was deleted and /media-creation now redirects (FE-Z). Its status_pagina row
-- `media_creation` no longer gates any nav item; marking it `desativado` keeps the catalogue honest.
-- No data is touched: the legacy posts / brand-kit tables and routers stay (contract §A).
--
-- FORWARD-ONLY, IDEMPOTENT. Requires 241 (adds the replacement pages' status rows).
-- Apply together with the image that ships the FE-Z redirect.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'media-creation-carrosseis') THEN
    RAISE EXCEPTION 'Migration 246 requires the media-creation-carrosseis status row (migration 241) -- apply 241 first';
  END IF;
END
$guard$;

UPDATE social_wiring.status_pagina
   SET status = 'desativado'
 WHERE nome_pagina = 'media_creation'
   AND status IS DISTINCT FROM 'desativado';
