-- ============================================================================
-- Migration 281 -- social_wiring: Lais wave 13 "Analise de credito"
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 15 (wave 13,
-- "Analise de credito") + section 17 (a credit result is FINANCIAL DATA: explicit in-chat consent before
-- ANY provider call; nothing raw is stored).
--   lais_credito_config         per-org switch: ativo, provider (null until the owner picks one),
--                               apenas_aluguel (default true: the analysis runs at the visit step of an aluguel).
--   lais_credito_consentimentos append-only log of the lead's answer (aceito true|false) + the version of
--                               the text the lead agreed to. The LATEST row per contato wins.
--   lais_credito_analises       one row per run: status pendente|aprovado|reprovado|erro, `resumo` is a short
--                               verdict sentence (NEVER a score / income / raw provider payload).
--                               It can only exist behind a consent row with aceito = true -- by construction:
--                               a composite FK (consentimento_id, contato_id, consentimento_aceito) onto the
--                               consent's UNIQUE (id, contato_id, aceito) plus CHECK (consentimento_aceito).
--   status_pagina               `lais_credito` (copies whatsapp_chat, like 259/270/278).
--
-- RLS: select_own_org + service_role (writes through the backend only), pattern 267/270/278.
-- NO SECURITY DEFINER function in this file. FORWARD-ONLY, IDEMPOTENT.
-- PREREQUISITES: core 070, 014 (status_pagina), 267 (lais_contatos). Applied by the tech-lead with
-- noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.lais_contatos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.lais_contatos (migration 267) -- apply 267 first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'this migration requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

-- ── per-org config ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lais_credito_config (
    org_id        uuid        PRIMARY KEY,
    ativo         boolean     NOT NULL DEFAULT false,
    provider      text,
    apenas_aluguel boolean    NOT NULL DEFAULT true,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_credito_config_provider_valido
        CHECK (provider IS NULL OR provider ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT lais_credito_config_ativo_exige_provider
        CHECK (NOT ativo OR provider IS NOT NULL)
);

COMMENT ON TABLE social_wiring.lais_credito_config IS
    'Lais > Analise de credito, per-org switch (migration 281, contract 15): ativo needs a provider; apenas_aluguel limits it to aluguel leads.';

-- ── consent log ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lais_credito_consentimentos (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid        NOT NULL,
    contato_id    uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    aceito        boolean     NOT NULL,
    registrado_at timestamptz NOT NULL DEFAULT now(),
    texto_versao  text        NOT NULL,
    CONSTRAINT lais_credito_consentimentos_texto_versao_nao_vazia
        CHECK (length(btrim(texto_versao)) > 0),
    CONSTRAINT lais_credito_consentimentos_id_contato_aceito_uq UNIQUE (id, contato_id, aceito)
);

COMMENT ON TABLE social_wiring.lais_credito_consentimentos IS
    'Append-only log of the lead''s in-chat answer to the credit-analysis consent (migration 281, contract 17); the latest row per contato wins; texto_versao names the wording agreed to.';

CREATE INDEX IF NOT EXISTS idx_lais_credito_consent_contato
    ON social_wiring.lais_credito_consentimentos (contato_id, registrado_at DESC);

-- ── analyses ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lais_credito_analises (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid        NOT NULL,
    contato_id    uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    consentimento_id uuid     NOT NULL,
    consentimento_aceito boolean NOT NULL DEFAULT true,
    provider      text        NOT NULL,
    status        text        NOT NULL DEFAULT 'pendente',
    resumo        text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_credito_analises_status_valido
        CHECK (status IN ('pendente', 'aprovado', 'reprovado', 'erro')),
    CONSTRAINT lais_credito_analises_consentimento_aceito
        CHECK (consentimento_aceito),
    CONSTRAINT lais_credito_analises_consentimento_fk
        FOREIGN KEY (consentimento_id, contato_id, consentimento_aceito)
        REFERENCES social_wiring.lais_credito_consentimentos (id, contato_id, aceito) ON DELETE CASCADE
);

COMMENT ON TABLE social_wiring.lais_credito_analises IS
    'Lais > Analise de credito runs (migration 281, contract 15/17): status + a one-sentence resumo, never raw financial data; a row can only hang off a consent with aceito = true.';

CREATE INDEX IF NOT EXISTS idx_lais_credito_analises_feed
    ON social_wiring.lais_credito_analises (org_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lais_credito_analises_contato
    ON social_wiring.lais_credito_analises (contato_id, created_at DESC);

-- ── RLS ─────────────────────────────────────────────────────────────────────
ALTER TABLE social_wiring.lais_credito_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lais_credito_config_select_own_org" ON social_wiring.lais_credito_config;
CREATE POLICY "lais_credito_config_select_own_org" ON social_wiring.lais_credito_config
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_credito_config_service_role" ON social_wiring.lais_credito_config;
CREATE POLICY "lais_credito_config_service_role" ON social_wiring.lais_credito_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.lais_credito_consentimentos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lais_credito_consentimentos_select_own_org" ON social_wiring.lais_credito_consentimentos;
CREATE POLICY "lais_credito_consentimentos_select_own_org" ON social_wiring.lais_credito_consentimentos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_credito_consentimentos_service_role" ON social_wiring.lais_credito_consentimentos;
CREATE POLICY "lais_credito_consentimentos_service_role" ON social_wiring.lais_credito_consentimentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.lais_credito_analises ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lais_credito_analises_select_own_org" ON social_wiring.lais_credito_analises;
CREATE POLICY "lais_credito_analises_select_own_org" ON social_wiring.lais_credito_analises
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_credito_analises_service_role" ON social_wiring.lais_credito_analises;
CREATE POLICY "lais_credito_analises_service_role" ON social_wiring.lais_credito_analises
    FOR ALL TO service_role USING (true) WITH CHECK (true);

INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT 'lais_credito', origem.status, 'Lais — Análise de crédito'
  FROM social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
