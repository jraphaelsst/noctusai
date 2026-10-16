-- ============================================================================
-- Migration 273 -- social_wiring: Lais wave 6, Notificacoes (per-user prefs)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 8.
--
--   lais_notificacao_prefs  (org_id, user_id, tipo) -> in_app. One row only when a user
--                           CHANGED a type from the default (absent = ON). `tipo` is a
--                           notification type of lais_eventos_service.TIPOS_NOTIFICAVEIS or the
--                           pseudo-type `lead_pronto` (the header toggle "Notificar lead pronto
--                           para atendimento"). The closed list lives in the service; the DB
--                           guards the token shape only, so a new type needs no migration.
--
-- The notifications themselves are NOT stored here: they are rows of core's
-- public.notifications (kind in metadata.tipo = 'lais_<tipo>'), written by write_in_app.
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 272.
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: core 070. Applied with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.lais_notificacao_prefs (
    org_id     uuid        NOT NULL,
    user_id    uuid        NOT NULL,
    tipo       text        NOT NULL,
    in_app     boolean     NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id, tipo),
    CONSTRAINT lais_notificacao_prefs_tipo_valido CHECK (tipo ~ '^[a-z][a-z0-9_]{2,39}$')
);

COMMENT ON TABLE social_wiring.lais_notificacao_prefs IS
    'Per-user in-app preference per Lais notification type (migration 273, contract 8); absent row = on.';

ALTER TABLE social_wiring.lais_notificacao_prefs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_notificacao_prefs_select_own_org" ON social_wiring.lais_notificacao_prefs;
CREATE POLICY "lais_notificacao_prefs_select_own_org" ON social_wiring.lais_notificacao_prefs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_notificacao_prefs_service_role" ON social_wiring.lais_notificacao_prefs;
CREATE POLICY "lais_notificacao_prefs_service_role" ON social_wiring.lais_notificacao_prefs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- status_pagina: Lais > Notificacoes (copies whatsapp_chat, like 259)
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('lais_notificacoes', 'Lais — Notificações')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
