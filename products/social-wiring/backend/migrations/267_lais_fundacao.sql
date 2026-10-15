-- ============================================================================
-- Migration 267 -- social_wiring: Lais foundation (contatos, interacoes,
--                  acoes aplicadas, eventos)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md
--   section 0 (A1 SW is the source of truth for every Lais datum; 0.2 the
--   `gen` stale guard) and section 2.2 (slice F-SW).
--
--   lais_contatos        one row per person Julia talks to ("lead" in Lais' UI);
--                        `gen` is bumped on every inbound / encerrar / pause so a
--                        queued job that carries an older gen no-ops (0.2).
--   lais_interacoes      one episode (opened on the first inbound after 24 h of
--                        silence or after `encerrar`); at most ONE open per contato.
--   lais_acoes_aplicadas idempotency ledger of the actions agents returned (A4):
--                        unique (org_id, lote_hash, seq), so a replayed batch never
--                        applies an action twice.
--   lais_eventos         event bus later waves render (notifications, panel).
--
-- RLS: every table = ENABLE ROW LEVEL SECURITY + `select_own_org` policy
-- (org_id = current_org_id_for('social_wiring')) + service_role policy; writes go
-- through the backend service client only (pattern 255 / 258).
--
-- Retention (contract 17): contatos closed for 180 days without a SW lead are
-- purged by a later job; deletion on request is wired in `apagar_dados_do_chat`.
--
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 025 (leads), core 070
-- (current_org_id_for). Do not apply by hand: the tech-lead applies it with
-- noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

-- -- 1. lais_contatos -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_contatos (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid        NOT NULL,
    connection_id       uuid        NOT NULL,
    chat_id             text        NOT NULL,
    telefone_e164       text,
    nome                text,
    email               text,
    operacao            text,
    slots               jsonb       NOT NULL DEFAULT '{}'::jsonb,
    gen                 integer     NOT NULL DEFAULT 0,
    status_envio        text        NOT NULL DEFAULT 'nao_pronto',
    lead_id             uuid        REFERENCES social_wiring.leads (id) ON DELETE SET NULL,
    responsavel_user_id uuid,
    ultimo_inbound_at   timestamptz,
    ultimo_outbound_at  timestamptz,
    encerrado_at        timestamptz,
    canal               text        NOT NULL DEFAULT 'whatsapp',
    origem_slug         text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_contatos_status_envio_valido
        CHECK (status_envio IN ('nao_pronto', 'enviado', 'erro', 'enviado_auto'))
);

COMMENT ON TABLE social_wiring.lais_contatos IS
    'One row per person Julia (the Lais lead agent) talks to (migration 267, contract 2.2). '
    '`gen` is the stale-guard counter: bumped on inbound / encerrar / pause.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_contatos_org_conexao_chat_uq
    ON social_wiring.lais_contatos (org_id, connection_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_lais_contatos_org_inbound
    ON social_wiring.lais_contatos (org_id, ultimo_inbound_at DESC);

-- -- 2. lais_interacoes ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_interacoes (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid        NOT NULL,
    contato_id   uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    iniciada_at  timestamptz NOT NULL DEFAULT now(),
    encerrada_at timestamptz,
    operacao     text,
    tipo         text        NOT NULL DEFAULT 'comercial',
    resumo       text,
    slots        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    intencoes    text[]      NOT NULL DEFAULT '{}',
    desfecho     text,
    custo_usd    numeric,
    created_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.lais_interacoes IS
    'One episode of a contato (migration 267): opened on the first inbound after 24 h of silence '
    'or after `encerrar`; the summary/slots/desfecho come from agents `/resumo` when it closes.';

-- at most ONE open episode per contato (a race between two inbound turns must not open two)
CREATE UNIQUE INDEX IF NOT EXISTS lais_interacoes_uma_aberta_uq
    ON social_wiring.lais_interacoes (contato_id) WHERE encerrada_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_lais_interacoes_org_contato
    ON social_wiring.lais_interacoes (org_id, contato_id, iniciada_at DESC);

-- -- 3. lais_acoes_aplicadas ----------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_acoes_aplicadas (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid        NOT NULL,
    contato_id      uuid        NOT NULL REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    conversation_id uuid,
    lote_hash       text        NOT NULL,
    seq             integer     NOT NULL,
    tipo            text        NOT NULL,
    payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    resultado       jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.lais_acoes_aplicadas IS
    'Idempotency ledger of the actions agents returned in a turn (migration 267, contract A4): '
    'unique (org_id, lote_hash, seq) => a replayed batch applies nothing twice.';

CREATE UNIQUE INDEX IF NOT EXISTS lais_acoes_aplicadas_lote_seq_uq
    ON social_wiring.lais_acoes_aplicadas (org_id, lote_hash, seq);
CREATE INDEX IF NOT EXISTS idx_lais_acoes_contato
    ON social_wiring.lais_acoes_aplicadas (contato_id);

-- -- 4. lais_eventos ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_eventos (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    tipo       text        NOT NULL,
    contato_id uuid        REFERENCES social_wiring.lais_contatos (id) ON DELETE CASCADE,
    payload    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    lido_por   uuid[]      NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    -- the closed list of types lives in the service (`lais_eventos_service.TIPOS`) so a later
    -- wave adds one without a migration; the DB only guarantees a well-formed token.
    CONSTRAINT lais_eventos_tipo_valido CHECK (tipo ~ '^[a-z][a-z0-9_]{2,39}$')
);

COMMENT ON TABLE social_wiring.lais_eventos IS
    'Lais event bus (migration 267): wave 6 renders it as notifications; `lido_por` = users who read it.';

CREATE INDEX IF NOT EXISTS idx_lais_eventos_org_created
    ON social_wiring.lais_eventos (org_id, created_at DESC);

-- -- 5. RLS: select own org + service_role (writes through the backend only) ------
ALTER TABLE social_wiring.lais_contatos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_interacoes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_acoes_aplicadas  ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_eventos          ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_contatos_select_own_org" ON social_wiring.lais_contatos;
CREATE POLICY "lais_contatos_select_own_org" ON social_wiring.lais_contatos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_contatos_service_role" ON social_wiring.lais_contatos;
CREATE POLICY "lais_contatos_service_role" ON social_wiring.lais_contatos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_interacoes_select_own_org" ON social_wiring.lais_interacoes;
CREATE POLICY "lais_interacoes_select_own_org" ON social_wiring.lais_interacoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_interacoes_service_role" ON social_wiring.lais_interacoes;
CREATE POLICY "lais_interacoes_service_role" ON social_wiring.lais_interacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_acoes_aplicadas_select_own_org" ON social_wiring.lais_acoes_aplicadas;
CREATE POLICY "lais_acoes_aplicadas_select_own_org" ON social_wiring.lais_acoes_aplicadas
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_acoes_aplicadas_service_role" ON social_wiring.lais_acoes_aplicadas;
CREATE POLICY "lais_acoes_aplicadas_service_role" ON social_wiring.lais_acoes_aplicadas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_eventos_select_own_org" ON social_wiring.lais_eventos;
CREATE POLICY "lais_eventos_select_own_org" ON social_wiring.lais_eventos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_eventos_service_role" ON social_wiring.lais_eventos;
CREATE POLICY "lais_eventos_service_role" ON social_wiring.lais_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
