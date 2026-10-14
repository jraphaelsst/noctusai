-- ============================================================================
-- Migration 259 · social_wiring: status_pagina row for Lais › Agente
-- ============================================================================
-- WHY
-- ---
-- Lais gains a third routed page, /lais/agente (Julia: Agents link, the
-- per-connection "Julia atende leads" switch, handoff target, privacy notice).
-- The nav gates items by status_pagina (unlisted key => hidden), so the key
-- `lais_agente` needs a row. Same rule as migration 252: it takes the status the
-- `whatsapp_chat` row carries at apply time (copied, not hard-coded), so the new
-- page can never be more visible than the WhatsApp surface it extends.
--
-- FORWARD-ONLY, IDEMPOTENT (ON CONFLICT DO NOTHING). Requires 014 (and 252's
-- sibling rows are untouched). No CHECK / UNIQUE / trigger added, so no GuardProbe.
-- Apply together with (or before) the image that ships the page.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'Migration 259 requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES
          ('lais_agente', 'Lais — Agente (Julia)')
       ) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
