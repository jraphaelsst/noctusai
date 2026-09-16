-- 128_fotos_status_pagina.sql -- register the edicao-fotos nav pages in
-- status_pagina, seeded 'desenvolvimento'
--
-- Plan §1 (rollout): "admin screens live inside Social Wiring; menu
-- 'Edição de Fotos'; pages ship as status_pagina='desenvolvimento' (owner
-- accepts that other orgs' owner/admin/dev can see them); everything
-- ships as one release."
--
-- This migration ONLY inserts rows -- it does NOT add a new dev-visibility
-- RLS policy. `social_wiring.status_pagina` already carries the
-- `dev_veem_desenvolvimento` policy from `036_status_pagina_dev_
-- visibility.sql` (role array `['owner', 'dev', 'admin']`, matching the
-- FE `DEV_ROLES` const), which applies to EVERY row in the table
-- regardless of when it was inserted. Filename deliberately does NOT
-- match `*status_pagina_dev_visibility.sql` -- that glob is what
-- `check_status_pagina_role_parity` scans for role-array comparisons, and
-- this file declares no policy for it to compare.
--
-- Ten pages -- the nav-group pages named in the approved plan §4
-- (`Lotes`, `NovoLote`, `LoteRevisao`, `Configuracoes`) plus the admin
-- surfaces (`Referencias`, `GuiasEstilo`, `Modelos`, `Regras`,
-- `Curadores`, `Painel`). Route-slug convention follows the flat
-- kebab-case shape existing rows use (`agendamentos`, `instagram-
-- insights`, ...), prefixed `edicao-fotos` for this module's nav group.
-- The FE slice that actually registers these routes in App.tsx's
-- NAV_GROUPS (Wave 3 W10a-e) MUST use these exact slugs or the
-- `filterNavByPageStatus` gate hides the page silently (same failure
-- shape 018/021/023/039/084 exist to close).
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao) VALUES
    ('edicao-fotos',              'desenvolvimento', 'Edição de Fotos — lotes (lista)'),
    ('edicao-fotos-novo-lote',    'desenvolvimento', 'Edição de Fotos — novo lote'),
    ('edicao-fotos-revisao',      'desenvolvimento', 'Edição de Fotos — revisão de lote'),
    ('edicao-fotos-configuracoes','desenvolvimento', 'Edição de Fotos — configurações da organização'),
    ('edicao-fotos-referencias',  'desenvolvimento', 'Edição de Fotos — pool de referências (admin)'),
    ('edicao-fotos-guias',        'desenvolvimento', 'Edição de Fotos — guias de estilo (admin)'),
    ('edicao-fotos-modelos',      'desenvolvimento', 'Edição de Fotos — catálogo de modelos (admin)'),
    ('edicao-fotos-regras',       'desenvolvimento', 'Edição de Fotos — regras de aprendizado (admin)'),
    ('edicao-fotos-curadores',    'desenvolvimento', 'Edição de Fotos — curadores de fotos (admin)'),
    ('edicao-fotos-painel',       'desenvolvimento', 'Edição de Fotos — painel/dashboard (admin)')
ON CONFLICT (nome_pagina) DO NOTHING;
