-- ============================================================================
-- Migration 352 · social_wiring: unified chat, propostas, fluxo ledger (M3 of estruturas-contract.md section 3.3)
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/core-studio-build/specs/estruturas-contract.md sections 3.3, 6.5, 9 (UNI-1a,
-- owner decisions of 2026-11-15). ONE chat (no headline/roteiro switch): the assistant proposes headlines, each one a
-- first-class row (`cs_chat_propostas`) linked to the 1..3 Estruturas that inspired it; clicking one ("escolher")
-- saves it as a real, favorite `cs_headlines` row and starts a resumable flow (headline -> roteiro -> card). Every
-- state change of that flow lands as a row of the append-only `cs_fluxo_eventos` ledger in the SAME transaction.
--
--   * cs_chat_conversas.agente    -- also accepts 'unificado' (the N code writes it; legacy 'headline'/'roteiro' rows are
--                                    READ as unified, never backfilled here -- M5 backfills + tightens, >= 2 deploys later).
--   * cs_chat_mensagens           -- + tipo ('texto' | 'roteiro_gerado'), + proposta_id (unique: the roteiro_gerado message
--                                    is inserted once per proposta).
--   * cs_chat_propostas           -- one row per headline the assistant proposed (tier org, service-only).
--   * cs_chat_proposta_estruturas -- the 1..3 Estruturas a proposta cites; exactly one `principal`.
--   * cs_fluxo_eventos            -- append-only ledger of the whole flow (NO content: ids, counts, codes).
--   * cs_headlines                -- + conversa_id / proposta_id (UNIQUE: a retried save is a lookup).
--   * cs_roteiros                 -- + conversa_id, + formato (reels | carrossel | stories | post; every existing row is a Reels
--                                    script, so the DEFAULT is the truthful backfill).
--   * cs_posts                    -- cs_posts_formato_check relaxed from ('reel') to ('reel','carrossel','story','feed').
--   * status_pagina               -- the Headlines e Roteiros page is owner/dev-only until validated.
--
-- EVERY multi-table write is ONE call to a SECURITY DEFINER function (one PostgREST call = one transaction):
-- cs_chat_resposta_gravar (assistant message + propostas + Estrutura links + events), cs_chat_proposta_sintetizar
-- (an already-saved headline picked with `@`), cs_chat_proposta_reivindicar (the claim/lease of the saga's step 1),
-- cs_chat_proposta_salvar_headline (step 2: headline + usos + fluxo_etapa + event), cs_chat_proposta_liberar
-- (a pre-flight refusal gives the lease back so the same click can be retried at once). cs_fluxo_evento is the
-- internal helper they share (also reused by UNI-1b). The service role can only SELECT the new tables (and INSERT
-- events, for the surfaces that record name-resolution attempts); the writes go through the functions.
--
-- Backward compatible with the previous image (N-1): only additive objects, one CHECK widened. FORWARD-ONLY, IDEMPOTENT.
-- GuardProbes: _SW_352_PROBES in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
-- Requires 229 (cs_chat_*, cs_headlines, cs_roteiros), 241 (cs_posts) and 350 (cs_estruturas, cs_estrutura_usos).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_chat_conversas') IS NULL
     OR to_regclass('social_wiring.cs_headlines') IS NULL
     OR to_regclass('social_wiring.cs_roteiros') IS NULL THEN
    RAISE EXCEPTION 'Migration 352 requires the cs_* tables of migration 229 -- apply 229 first';
  END IF;
  IF to_regclass('social_wiring.cs_posts') IS NULL THEN
    RAISE EXCEPTION 'Migration 352 requires cs_posts (migration 241) -- apply 241 first';
  END IF;
  IF to_regclass('social_wiring.cs_estruturas') IS NULL OR to_regclass('social_wiring.cs_estrutura_usos') IS NULL THEN
    RAISE EXCEPTION 'Migration 352 requires cs_estruturas / cs_estrutura_usos (migration 350) -- apply 350 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Widen CHECKs on existing tables (backward compatible: a superset of the old vocabulary)
-- ----------------------------------------------------------------------------
SET LOCAL lock_timeout = '5s';

ALTER TABLE social_wiring.cs_chat_conversas DROP CONSTRAINT IF EXISTS cs_chat_conversas_agente_check;
ALTER TABLE social_wiring.cs_chat_conversas
    ADD CONSTRAINT cs_chat_conversas_agente_check CHECK (agente IN ('headline', 'roteiro', 'unificado')) NOT VALID;
ALTER TABLE social_wiring.cs_chat_conversas VALIDATE CONSTRAINT cs_chat_conversas_agente_check;

ALTER TABLE social_wiring.cs_posts DROP CONSTRAINT IF EXISTS cs_posts_formato_check;
ALTER TABLE social_wiring.cs_posts
    ADD CONSTRAINT cs_posts_formato_check CHECK (formato IN ('reel', 'carrossel', 'story', 'feed')) NOT VALID;
ALTER TABLE social_wiring.cs_posts VALIDATE CONSTRAINT cs_posts_formato_check;

-- ----------------------------------------------------------------------------
-- 2. cs_chat_mensagens: tipo + proposta_id
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_chat_mensagens ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'texto';
ALTER TABLE social_wiring.cs_chat_mensagens ADD COLUMN IF NOT EXISTS proposta_id UUID;
ALTER TABLE social_wiring.cs_chat_mensagens DROP CONSTRAINT IF EXISTS cs_chat_mensagens_tipo_check;
ALTER TABLE social_wiring.cs_chat_mensagens
    ADD CONSTRAINT cs_chat_mensagens_tipo_check CHECK (tipo IN ('texto', 'roteiro_gerado')) NOT VALID;
ALTER TABLE social_wiring.cs_chat_mensagens VALIDATE CONSTRAINT cs_chat_mensagens_tipo_check;
-- the roteiro_gerado message is inserted exactly once per proposta
CREATE UNIQUE INDEX IF NOT EXISTS cs_chat_mensagens_proposta_uq
    ON social_wiring.cs_chat_mensagens (proposta_id) WHERE proposta_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. cs_chat_propostas / cs_chat_proposta_estruturas
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_chat_propostas (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id          UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    conversa_id       UUID NOT NULL REFERENCES social_wiring.cs_chat_conversas (id) ON DELETE CASCADE,
    mensagem_id       UUID NOT NULL REFERENCES social_wiring.cs_chat_mensagens (id) ON DELETE CASCADE,
    ordem             SMALLINT NOT NULL CONSTRAINT cs_chat_propostas_ordem_check CHECK (ordem >= 1),
    -- the headline with the citation and the trigger tag stripped
    texto             TEXT NOT NULL CONSTRAINT cs_chat_propostas_texto_check CHECK (char_length(texto) BETWEEN 1 AND 1000),
    gatilho_tag       TEXT,
    status            TEXT NOT NULL DEFAULT 'proposta'
                      CONSTRAINT cs_chat_propostas_status_check CHECK (status IN ('proposta', 'escolhida')),
    -- NULL while `proposta`; the last durable step of the saga once chosen
    fluxo_etapa       TEXT
                      CONSTRAINT cs_chat_propostas_fluxo_etapa_check
                      CHECK (fluxo_etapa IN ('headline_salva', 'roteiro_criado', 'card_criado', 'concluido', 'falhou')),
    fluxo_erro_codigo TEXT,
    -- the resume lease: a claim holds the flow until this instant
    fluxo_lease_ate   TIMESTAMPTZ,
    headline_id       UUID REFERENCES social_wiring.cs_headlines (id) ON DELETE SET NULL,
    escolhida_por     UUID,
    escolhida_em      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_chat_propostas_mensagem_ordem_uq UNIQUE (mensagem_id, ordem)
);
CREATE INDEX IF NOT EXISTS cs_chat_propostas_conversa_idx ON social_wiring.cs_chat_propostas (conversa_id, created_at);
CREATE INDEX IF NOT EXISTS cs_chat_propostas_org_idx ON social_wiring.cs_chat_propostas (org_id);
CREATE INDEX IF NOT EXISTS cs_chat_propostas_headline_idx
    ON social_wiring.cs_chat_propostas (headline_id) WHERE headline_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS social_wiring.cs_chat_proposta_estruturas (
    proposta_id  UUID NOT NULL REFERENCES social_wiring.cs_chat_propostas (id) ON DELETE CASCADE,
    estrutura_id UUID NOT NULL REFERENCES social_wiring.cs_estruturas (id) ON DELETE CASCADE,
    -- max 3 per proposta: ordem 1..3 + the PK (proposta_id, estrutura_id)
    ordem        SMALLINT NOT NULL CONSTRAINT cs_chat_proposta_estruturas_ordem_check CHECK (ordem BETWEEN 1 AND 3),
    principal    BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (proposta_id, estrutura_id)
);
-- at most one principal per proposta; one Estrutura per slot
CREATE UNIQUE INDEX IF NOT EXISTS cs_chat_proposta_estruturas_principal_uq
    ON social_wiring.cs_chat_proposta_estruturas (proposta_id) WHERE principal;
CREATE UNIQUE INDEX IF NOT EXISTS cs_chat_proposta_estruturas_ordem_uq
    ON social_wiring.cs_chat_proposta_estruturas (proposta_id, ordem);
CREATE INDEX IF NOT EXISTS cs_chat_proposta_estruturas_estrutura_idx
    ON social_wiring.cs_chat_proposta_estruturas (estrutura_id);

-- ----------------------------------------------------------------------------
-- 4. cs_fluxo_eventos (append-only; no content, no FKs except org/marca)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_fluxo_eventos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id    UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    conversa_id UUID NOT NULL,
    proposta_id UUID,
    mensagem_id UUID,
    headline_id UUID,
    roteiro_id  UUID,
    post_id     UUID,
    -- NULL = the system acted
    ator_id     UUID,
    tipo        TEXT NOT NULL CONSTRAINT cs_fluxo_eventos_tipo_check CHECK (tipo IN (
        'propostas_geradas', 'proposta_escolhida', 'headline_salva', 'roteiro_criado', 'roteiro_gerado', 'roteiro_falhou',
        'card_criado', 'card_falhou', 'legenda_gerada', 'legenda_falhou', 'fluxo_concluido', 'fluxo_retomado',
        'perfil_resolvido', 'perfil_ambiguo', 'perfil_nao_encontrado', 'citacao_rejeitada', 'atribuicao_ausente',
        'placeholder_remanescente', 'formato_misturado')),
    -- e.g. how many citations were rejected
    contagem    INTEGER,
    -- an error / reason code, or the sha256 on legenda_gerada -- never text
    codigo      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cs_fluxo_eventos_proposta_idx
    ON social_wiring.cs_fluxo_eventos (proposta_id, created_at) WHERE proposta_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_fluxo_eventos_conversa_idx ON social_wiring.cs_fluxo_eventos (conversa_id, created_at);
CREATE INDEX IF NOT EXISTS cs_fluxo_eventos_org_tipo_idx ON social_wiring.cs_fluxo_eventos (org_id, tipo, created_at);
CREATE INDEX IF NOT EXISTS cs_fluxo_eventos_marca_idx ON social_wiring.cs_fluxo_eventos (marca_id);

-- append-only: UPDATE/DELETE refused for everybody; only a DB-driven ON DELETE CASCADE (org / marca erase, depth > 1)
-- may remove a row (the same carve-out cs_estrutura_usos has).
CREATE OR REPLACE FUNCTION social_wiring.cs_fluxo_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'cs_fluxo_eventos_imutavel: cs_fluxo_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_fluxo_eventos_imutavel ON social_wiring.cs_fluxo_eventos;
CREATE TRIGGER cs_fluxo_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_fluxo_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_fluxo_eventos_imutavel();

CREATE OR REPLACE FUNCTION social_wiring.cs_fluxo_recusa_truncate()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'cs_fluxo_recusa_truncate: % is append-only (TRUNCATE refused)', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_fluxo_eventos_no_truncate ON social_wiring.cs_fluxo_eventos;
CREATE TRIGGER cs_fluxo_eventos_no_truncate BEFORE TRUNCATE ON social_wiring.cs_fluxo_eventos
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.cs_fluxo_recusa_truncate();

-- ----------------------------------------------------------------------------
-- 5. cs_headlines / cs_roteiros: the conversation links + the roteiro formato
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_headlines
    ADD COLUMN IF NOT EXISTS conversa_id UUID REFERENCES social_wiring.cs_chat_conversas (id) ON DELETE SET NULL;
ALTER TABLE social_wiring.cs_headlines ADD COLUMN IF NOT EXISTS proposta_id UUID;
CREATE UNIQUE INDEX IF NOT EXISTS cs_headlines_conversa_proposta_uq
    ON social_wiring.cs_headlines (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_headlines_conversa_idx
    ON social_wiring.cs_headlines (conversa_id) WHERE conversa_id IS NOT NULL;

ALTER TABLE social_wiring.cs_roteiros
    ADD COLUMN IF NOT EXISTS conversa_id UUID REFERENCES social_wiring.cs_chat_conversas (id) ON DELETE SET NULL;
ALTER TABLE social_wiring.cs_roteiros ADD COLUMN IF NOT EXISTS formato TEXT NOT NULL DEFAULT 'reels';
ALTER TABLE social_wiring.cs_roteiros DROP CONSTRAINT IF EXISTS cs_roteiros_formato_check;
ALTER TABLE social_wiring.cs_roteiros
    ADD CONSTRAINT cs_roteiros_formato_check CHECK (formato IN ('reels', 'carrossel', 'stories', 'post')) NOT VALID;
ALTER TABLE social_wiring.cs_roteiros VALIDATE CONSTRAINT cs_roteiros_formato_check;
CREATE INDEX IF NOT EXISTS cs_roteiros_conversa_idx
    ON social_wiring.cs_roteiros (conversa_id) WHERE conversa_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 6. Page visibility: owner/dev-only until validated (an unlisted page is hidden)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('media-creation-headlines-roteiros', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 7. RPCs (service role only; SECURITY DEFINER, REVOKE EXECUTE below). One call = one transaction.
-- ----------------------------------------------------------------------------
-- Refusals are coded exceptions: RAISE EXCEPTION '<code>', mapped to HTTP by the API.

-- 7.0 internal helper (no grant to any API role): one fluxo event row.
CREATE OR REPLACE FUNCTION social_wiring.cs_fluxo_evento(
    p_org UUID, p_marca UUID, p_conversa UUID, p_tipo TEXT, p_proposta UUID, p_mensagem UUID, p_headline UUID,
    p_roteiro UUID, p_post UUID, p_ator UUID, p_contagem INTEGER, p_codigo TEXT)
RETURNS void
LANGUAGE sql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
    INSERT INTO social_wiring.cs_fluxo_eventos
        (org_id, marca_id, conversa_id, tipo, proposta_id, mensagem_id, headline_id, roteiro_id, post_id, ator_id, contagem, codigo)
    VALUES (p_org, p_marca, p_conversa, p_tipo, p_proposta, p_mensagem, p_headline, p_roteiro, p_post, p_ator, p_contagem, p_codigo);
$fn$;

-- 7.1 The assistant's answer: message + propostas + Estrutura links + events, atomically.
-- p = {org_id, conversa_id, user_id, conteudo, truncada, modelo, contexto_chars,
--      propostas: [{ordem, texto, gatilho_tag, estrutura_ids: [uuid, ...]}],   (first id = principal, 1..3)
--      eventos:   [{tipo, contagem}]}                                          (the parser's rejection counts)
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_resposta_gravar(p JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_org UUID := (p->>'org_id')::uuid;
    v_conversa UUID := (p->>'conversa_id')::uuid;
    v_user UUID := (p->>'user_id')::uuid;
    v_marca UUID;
    v_msg UUID;
    v_prop UUID;
    v_item JSONB;
    v_n INTEGER := 0;
    v_ids JSONB := '[]'::jsonb;
BEGIN
    SELECT marca_id INTO v_marca FROM social_wiring.cs_chat_conversas
     WHERE id = v_conversa AND org_id = v_org AND user_id = v_user;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'conversa_nao_encontrada';
    END IF;
    INSERT INTO social_wiring.cs_chat_mensagens (org_id, conversa_id, role, conteudo, status, truncada, modelo, contexto_chars, tipo)
    VALUES (v_org, v_conversa, 'assistant', p->>'conteudo', 'completa', COALESCE((p->>'truncada')::boolean, false),
            p->>'modelo', NULLIF(p->>'contexto_chars', '')::integer, 'texto')
    RETURNING id INTO v_msg;

    FOR v_item IN SELECT value FROM jsonb_array_elements(COALESCE(p->'propostas', '[]'::jsonb)) LOOP
        INSERT INTO social_wiring.cs_chat_propostas (org_id, marca_id, conversa_id, mensagem_id, ordem, texto, gatilho_tag)
        VALUES (v_org, v_marca, v_conversa, v_msg, (v_item->>'ordem')::smallint, v_item->>'texto', NULLIF(v_item->>'gatilho_tag', ''))
        RETURNING id INTO v_prop;
        -- ordinality = the slot; the first valid code is the principal
        INSERT INTO social_wiring.cs_chat_proposta_estruturas (proposta_id, estrutura_id, ordem, principal)
        SELECT v_prop, (e.value #>> '{}')::uuid, e.ord::smallint, e.ord = 1
          FROM jsonb_array_elements(COALESCE(v_item->'estrutura_ids', '[]'::jsonb)) WITH ORDINALITY AS e(value, ord);
        v_n := v_n + 1;
        v_ids := v_ids || jsonb_build_array(jsonb_build_object('id', v_prop, 'ordem', (v_item->>'ordem')::int));
    END LOOP;

    IF v_n > 0 THEN
        PERFORM social_wiring.cs_fluxo_evento(v_org, v_marca, v_conversa, 'propostas_geradas', NULL, v_msg, NULL, NULL, NULL, NULL, v_n, NULL);
    END IF;
    FOR v_item IN SELECT value FROM jsonb_array_elements(COALESCE(p->'eventos', '[]'::jsonb)) LOOP
        PERFORM social_wiring.cs_fluxo_evento(v_org, v_marca, v_conversa, v_item->>'tipo', NULL, v_msg, NULL, NULL, NULL, NULL,
                                              NULLIF(v_item->>'contagem', '')::integer, NULL);
    END LOOP;
    RETURN jsonb_build_object('mensagem_id', v_msg, 'propostas', v_ids);
END;
$fn$;

-- 7.2 An already-saved headline picked with `@`: a proposta row is synthesised (no Estrutura link), behind an assistant
-- message that carries it. Idempotent per (conversa, headline): the second call returns the existing proposta.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_sintetizar(p_org UUID, p_user UUID, p_conversa UUID, p_headline UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_marca UUID;
    v_texto TEXT;
    v_prop social_wiring.cs_chat_propostas;
    v_msg UUID;
BEGIN
    -- the conversation row lock serialises two concurrent synthesises of the same headline
    SELECT marca_id INTO v_marca FROM social_wiring.cs_chat_conversas
     WHERE id = p_conversa AND org_id = p_org AND user_id = p_user FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'conversa_nao_encontrada';
    END IF;
    SELECT texto INTO v_texto FROM social_wiring.cs_headlines WHERE id = p_headline AND org_id = p_org AND marca_id = v_marca;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'headline_nao_encontrada';
    END IF;
    SELECT * INTO v_prop FROM social_wiring.cs_chat_propostas WHERE conversa_id = p_conversa AND headline_id = p_headline
     ORDER BY created_at LIMIT 1;
    IF FOUND THEN
        RETURN jsonb_build_object('proposta_id', v_prop.id, 'sintetizada', false);
    END IF;
    INSERT INTO social_wiring.cs_chat_mensagens (org_id, conversa_id, role, conteudo, status, tipo)
    VALUES (p_org, p_conversa, 'assistant', v_texto, 'completa', 'texto')
    RETURNING id INTO v_msg;
    INSERT INTO social_wiring.cs_chat_propostas (org_id, marca_id, conversa_id, mensagem_id, ordem, texto, headline_id)
    VALUES (p_org, v_marca, p_conversa, v_msg, 1, v_texto, p_headline)
    RETURNING * INTO v_prop;
    PERFORM social_wiring.cs_fluxo_evento(p_org, v_marca, p_conversa, 'propostas_geradas', v_prop.id, v_msg, p_headline, NULL, NULL, p_user, 1, 'sintetizada');
    RETURN jsonb_build_object('proposta_id', v_prop.id, 'sintetizada', true);
END;
$fn$;

-- 7.3 escolher step 1 -- claim with a resume lease (the contract's UPDATE ... RETURNING, serialised by a row lock).
-- Returns {claimed, proposta}. claimed=false means someone else holds the flow (or it is done): the caller returns the
-- current state with ja_existia. The event is written by the claimant only: proposta_escolhida on the first claim,
-- fluxo_retomado when an interrupted flow is resumed.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_reivindicar(
    p_proposta UUID, p_org UUID, p_conversa UUID, p_user UUID, p_lease_s INTEGER)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_antes social_wiring.cs_chat_propostas;
    v_novo social_wiring.cs_chat_propostas;
BEGIN
    SELECT p.* INTO v_antes
      FROM social_wiring.cs_chat_propostas p
      JOIN social_wiring.cs_chat_conversas c ON c.id = p.conversa_id
     WHERE p.id = p_proposta AND p.conversa_id = p_conversa AND p.org_id = p_org AND c.user_id = p_user
       FOR UPDATE OF p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposta_nao_encontrada';
    END IF;
    UPDATE social_wiring.cs_chat_propostas
       SET status = 'escolhida',
           escolhida_por = COALESCE(escolhida_por, p_user),
           escolhida_em = COALESCE(escolhida_em, now()),
           fluxo_lease_ate = now() + make_interval(secs => GREATEST(COALESCE(p_lease_s, 60), 1)),
           fluxo_erro_codigo = NULL
     WHERE id = p_proposta
       AND (status = 'proposta'
            OR (COALESCE(fluxo_etapa, '') <> 'concluido' AND (fluxo_lease_ate IS NULL OR fluxo_lease_ate < now())))
    RETURNING * INTO v_novo;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('claimed', false, 'proposta', to_jsonb(v_antes));
    END IF;
    IF v_antes.status = 'proposta' THEN
        PERFORM social_wiring.cs_fluxo_evento(v_novo.org_id, v_novo.marca_id, v_novo.conversa_id, 'proposta_escolhida',
                                              v_novo.id, v_novo.mensagem_id, v_novo.headline_id, NULL, NULL, p_user, NULL, NULL);
    ELSE
        PERFORM social_wiring.cs_fluxo_evento(v_novo.org_id, v_novo.marca_id, v_novo.conversa_id, 'fluxo_retomado',
                                              v_novo.id, v_novo.mensagem_id, v_novo.headline_id, NULL, NULL, p_user, NULL, v_antes.fluxo_etapa);
    END IF;
    RETURN jsonb_build_object('claimed', true, 'proposta', to_jsonb(v_novo));
END;
$fn$;

-- 7.4 escolher step 2 -- the headline, the usos, the etapa and the event, in one transaction. Idempotent: a retry
-- finds the headline (UNIQUE (conversa_id, proposta_id)), writes no second uso and no second event.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_salvar_headline(p_proposta UUID, p_org UUID, p_user UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_prop social_wiring.cs_chat_propostas;
    v_h UUID;
    v_criada BOOLEAN := false;
BEGIN
    SELECT p.* INTO v_prop
      FROM social_wiring.cs_chat_propostas p
      JOIN social_wiring.cs_chat_conversas c ON c.id = p.conversa_id
     WHERE p.id = p_proposta AND p.org_id = p_org AND c.user_id = p_user
       FOR UPDATE OF p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposta_nao_encontrada';
    END IF;
    IF v_prop.status <> 'escolhida' THEN
        RAISE EXCEPTION 'proposta_nao_escolhida';
    END IF;

    v_h := v_prop.headline_id;
    IF v_h IS NULL THEN
        INSERT INTO social_wiring.cs_headlines
            (org_id, marca_id, texto, conversa_id, proposta_id, modo, favorita, favoritada_em, created_by)
        VALUES (v_prop.org_id, v_prop.marca_id, btrim(v_prop.texto), v_prop.conversa_id, v_prop.id, 'manual', true, now(), p_user)
        ON CONFLICT (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL DO NOTHING
        RETURNING id INTO v_h;
        IF v_h IS NULL THEN
            SELECT id INTO v_h FROM social_wiring.cs_headlines WHERE conversa_id = v_prop.conversa_id AND proposta_id = v_prop.id;
        END IF;
        UPDATE social_wiring.cs_chat_propostas SET headline_id = v_h WHERE id = v_prop.id;
    END IF;

    -- one use per cited Estrutura (a synthesised proposta cites none); the unique indexes make a retry a no-op
    INSERT INTO social_wiring.cs_estrutura_usos
        (org_id, marca_id, estrutura_id, contexto, papel, ordem, bloco_ids, headline_id, proposta_id, created_by)
    SELECT v_prop.org_id, v_prop.marca_id, pe.estrutura_id, 'chat',
           CASE WHEN pe.principal THEN 'principal' ELSE 'mistura' END, pe.ordem, '{}'::uuid[], v_h, v_prop.id, p_user
      FROM social_wiring.cs_chat_proposta_estruturas pe
     WHERE pe.proposta_id = v_prop.id
    ON CONFLICT DO NOTHING;

    IF v_prop.fluxo_etapa IS NULL THEN
        UPDATE social_wiring.cs_chat_propostas SET fluxo_etapa = 'headline_salva' WHERE id = v_prop.id;
        PERFORM social_wiring.cs_fluxo_evento(v_prop.org_id, v_prop.marca_id, v_prop.conversa_id, 'headline_salva',
                                              v_prop.id, v_prop.mensagem_id, v_h, NULL, NULL, p_user, NULL, NULL);
        v_criada := true;
    END IF;
    RETURN jsonb_build_object('headline_id', v_h, 'criada', v_criada);
END;
$fn$;

-- 7.5 escolher step 3 refused (a pre-flight failure): give the lease back so the same click can be retried at once;
-- the headline stays saved and the etapa stays headline_salva. `p_erro` is the refusal code.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_liberar(p_proposta UUID, p_org UUID, p_user UUID, p_erro TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_n INTEGER;
BEGIN
    UPDATE social_wiring.cs_chat_propostas p
       SET fluxo_lease_ate = NULL, fluxo_erro_codigo = p_erro
      FROM social_wiring.cs_chat_conversas c
     WHERE p.id = p_proposta AND p.org_id = p_org AND p.status = 'escolhida'
       AND c.id = p.conversa_id AND c.user_id = p_user;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN jsonb_build_object('liberada', v_n = 1);
END;
$fn$;

-- ----------------------------------------------------------------------------
-- 8. RPC privileges: service role only
-- ----------------------------------------------------------------------------
REVOKE ALL ON FUNCTION social_wiring.cs_fluxo_evento(UUID, UUID, UUID, TEXT, UUID, UUID, UUID, UUID, UUID, UUID, INTEGER, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_resposta_gravar(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_sintetizar(UUID, UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_reivindicar(UUID, UUID, UUID, UUID, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_salvar_headline(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_liberar(UUID, UUID, UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_fluxo_eventos_imutavel() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_fluxo_recusa_truncate() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_resposta_gravar(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_sintetizar(UUID, UUID, UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_reivindicar(UUID, UUID, UUID, UUID, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_salvar_headline(UUID, UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_liberar(UUID, UUID, UUID, TEXT) TO service_role;

-- ----------------------------------------------------------------------------
-- 9. RLS + grants (service-only), tiers
-- ----------------------------------------------------------------------------
-- No browser policy: the chat reads/writes only through the API (service role). The writes go through the RPCs above,
-- so the service role holds SELECT only -- except cs_fluxo_eventos, where it may INSERT (surfaces that record a
-- name-resolution attempt write their own event row).
ALTER TABLE social_wiring.cs_chat_propostas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_chat_propostas_service_role" ON social_wiring.cs_chat_propostas;
CREATE POLICY "cs_chat_propostas_service_role" ON social_wiring.cs_chat_propostas FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_chat_propostas FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_chat_propostas TO service_role;

ALTER TABLE social_wiring.cs_chat_proposta_estruturas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_chat_proposta_estruturas_service_role" ON social_wiring.cs_chat_proposta_estruturas;
CREATE POLICY "cs_chat_proposta_estruturas_service_role" ON social_wiring.cs_chat_proposta_estruturas FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_chat_proposta_estruturas FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_chat_proposta_estruturas TO service_role;

ALTER TABLE social_wiring.cs_fluxo_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_fluxo_eventos_service_role" ON social_wiring.cs_fluxo_eventos;
CREATE POLICY "cs_fluxo_eventos_service_role" ON social_wiring.cs_fluxo_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_fluxo_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.cs_fluxo_eventos TO service_role;

COMMENT ON TABLE social_wiring.cs_chat_propostas IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_chat_proposta_estruturas IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_fluxo_eventos IS 'tier:org';
COMMENT ON COLUMN social_wiring.cs_chat_propostas.fluxo_lease_ate IS
    'Resume lease of the escolher saga: a claim holds the flow until this instant; after it any later click resumes. Migration 352.';
COMMENT ON COLUMN social_wiring.cs_roteiros.formato IS
    'reels | carrossel | stories | post -- derived from the principal Estrutura (reels when none). Existing rows are Reels scripts. Migration 352.';
