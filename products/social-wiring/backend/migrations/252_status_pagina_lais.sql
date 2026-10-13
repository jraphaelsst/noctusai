-- ============================================================================
-- Migration 252 · social_wiring: status_pagina rows for the "Lais" nav group
-- ============================================================================
-- WHY
-- ---
-- Owner decision 2026-10-13: the WhatsApp (WAHA) surface leaves the "Conexões"
-- nav group and becomes the "Lais" chatbot group. Today's single /whatsapp-chat
-- page (subtabs Chat + Configurações) splits into two routed pages:
--   * /lais/conversas    -> nav route key `lais_conversas`
--   * /lais/configuracoes -> nav route key `lais_configuracoes`
-- The nav gates items by status_pagina (unlisted key => hidden), so both keys
-- need a row. They take the SAME status the `whatsapp_chat` row carries at
-- apply time ('producao' per migration 014) -- copied, not hard-coded, so the
-- new pages can never be more visible than the page they replace.
--
-- The `whatsapp_chat` row is KEPT (back-compat: /whatsapp-chat still routes,
-- as a redirect to /lais/conversas). No data is touched.
--
-- FORWARD-ONLY, IDEMPOTENT (ON CONFLICT DO NOTHING). Requires 014.
-- No CHECK / UNIQUE / trigger added, so no GuardProbe.
-- Apply together with (or before) the image that ships the Lais nav group.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'Migration 252 requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_conversas', 'Lais — Conversas (WhatsApp)'),
          ('lais_configuracoes', 'Lais — Configurações das conexões WhatsApp')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
