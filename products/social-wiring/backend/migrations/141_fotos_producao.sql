-- 141_fotos_producao.sql — promote every `edicao-fotos*` page from
-- 'desenvolvimento' to 'producao'
--
-- 128_fotos_status_pagina.sql seeded the ten Edição de Fotos nav pages
-- (Lotes, Novo Lote, Revisão, Configurações, Referências, Guias de Estilo,
-- Modelos, Regras, Curadores, Painel) as 'desenvolvimento' — accepted at
-- the time per plan §1 ("owner accepts that other orgs' owner/admin/dev
-- can see them; everything ships as one release"). 130_fotos_modelos_
-- processamento.sql added an eleventh (`edicao-fotos-processamento`) the
-- same way. Per `036_status_pagina_dev_visibility.sql`'s
-- `dev_veem_desenvolvimento` policy (role array ['owner','dev','admin']),
-- a 'desenvolvimento' row is visible to NOBODY else — every admin/operator/
-- curador role that actually runs this module day to day (see
-- `seed/lib/frontend/src/photo-editing/permissions.ts`) has had the whole
-- module hidden from their nav since 121-128 landed in prod
-- (`APPLIED.md` § "114–128 — applied 2026-09-16").
--
-- Verified complete before flipping (KB § PATTERNS/frontend/
-- status-pagina-dev-visibility.md — promote only what is actually
-- shipped): all 44 FE calls in `seed/lib/frontend/src/photo-editing/
-- hooks.ts` (`createEdicaoFotosHooks`, consumed unmodified by SW's
-- `hooks/useEdicaoFotos.ts`) map 1:1 onto a mounted route under
-- `app/modules/edicao_fotos/routers/*` (capacidades, revisao, referencias,
-- guias, regras, configuracoes, lotes, painel, curadores, notificacoes,
-- modelos, processamento — all registered via `app.modules.edicao_fotos.
-- register` in `main.py`). Every `edicao-fotos/*` page in `App.tsx`'s
-- route table + both NAV_GROUPS blocks (admin + non-admin sidebars) reads
-- its loading state off the seed hooks' precomputed `showSkeleton`/
-- `isRefreshing` — none of the 11 pages touches `.isLoading` directly
-- (grep-verified). No page was held back.
--
-- Idempotent: an UPDATE to a value a row may already hold, scoped by the
-- `edicao-fotos` name prefix so it can never promote an unrelated page.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

UPDATE social_wiring.status_pagina
   SET status = 'producao'
 WHERE nome_pagina LIKE 'edicao-fotos%'
   AND status <> 'producao';
