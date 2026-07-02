-- 037_status_pagina_desativado.sql
-- Align erp.status_pagina.status CHECK with the canonical 3-status model:
--   producao | desenvolvimento | desativado
--
-- The original CHECK (001_erp_imobiliario.sql) allowed only
-- ('producao', 'desenvolvimento'). The seed `status_paginas` standard router
-- and its FE offer all three values; social-wiring already carries the full
-- set. This migration makes erp uniform so "desativado" (hide-from-everyone)
-- can be set on erp pages too.
--
-- Idempotent + forward-safe: DROP IF EXISTS removes the inline-generated
-- constraint (Postgres names an unnamed column CHECK `<table>_<col>_check`);
-- ADD then recreates it with the superset. Re-running is a no-op net effect.

SET search_path = erp, public;

ALTER TABLE erp.status_pagina
  DROP CONSTRAINT IF EXISTS status_pagina_status_check;

ALTER TABLE erp.status_pagina
  ADD CONSTRAINT status_pagina_status_check
  CHECK (status IN ('producao', 'desenvolvimento', 'desativado'));
