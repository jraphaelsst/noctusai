-- 012_interessados_status_pagina.sql — register the new `/interessados`
-- nav route (`frontend/src/App.tsx`'s NAV_GROUPS) in status_pagina so it's
-- visible in the sidebar (`isPageVisible()`,
-- seed/lib/frontend/src/page-status.ts, treats an unlisted route as hidden
-- from everyone).
--
-- Numbered 012, not 011: the backend engineer building the `interessados`
-- table + routes in parallel (`projects/interessados-CONTRACT.md`) owns
-- `011_interessados.sql`. Coordinate before applying — this migration is
-- independent of that one (a different table, `status_pagina`, already
-- exists since 001) but SHOULD land after it so `011` and `012` apply in
-- their numeric order.
--
-- WHY 'producao', not 'desenvolvimento': the page is a finished admin
-- feature, not a mid-build slice (unlike 009's kb/decisoes/perguntas/
-- roadmap rows). `producao` matches the precedent set by 'equipe' (001) —
-- another admin-only surface (invite/remove members) that is nonetheless
-- listed 'producao' in status_pagina; the actual 401/403 admin gate lives
-- in the backend route (contract: `GET/DELETE /api/interessados` →
-- authenticated + admin), not in page-level nav visibility. A non-admin
-- member who opens the page sees the standard `ErrorState` for the 403,
-- same as any other admin-gated call in this product.
--
-- Insert shape copied from 001_academia-de-reciclagem.sql's own seed block
-- (`INSERT ... ON CONFLICT (nome_pagina) DO NOTHING`), same as 009.
--
-- Forward-only + idempotent. Not applied by this slice (frontend-only) —
-- the tech-lead applies it alongside the backend engineer's `011`.

INSERT INTO academia_de_reciclagem.status_pagina (nome_pagina, status) VALUES
    ('interessados', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
