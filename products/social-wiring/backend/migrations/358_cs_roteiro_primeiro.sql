-- ============================================================================
-- Migration 358 · social_wiring: roteiro-first in the unified chat (M6 of estruturas-contract.md section 16.2)
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/core-studio-build/specs/estruturas-contract.md section 16 (amendment v1.1,
-- owner decisions D16a/D16b of 2026-11-17). The chat now works both ways: besides headlines, the assistant may propose
-- COMPLETE scripts (3 by default, at most 5). Clicking one saves it as-is as a `cs_roteiros` row (born `completo`), then
-- ONE headline is generated from it automatically, then the card -- the forward flow's steps 5-7, unchanged.
--
--   * cs_chat_propostas  -- + tipo ('headline' | 'roteiro'), + titulo / formato (roteiro only, both or none -- a CHECK),
--                           + roteiro_id; texto widened to 12000 chars for a roteiro (a headline stays <= 1000);
--                           fluxo_etapa gains 'roteiro_salvo' and 'headline_gerada'.
--   * cs_roteiros        -- + proposta_id; UNIQUE (conversa_id, proposta_id): a retried save is a lookup.
--   * cs_headlines.modo  -- gains 'do_roteiro' (the headline generated from a chosen roteiro).
--   * cs_fluxo_eventos   -- tipo gains roteiro_salvo, headline_gerando, headline_gerada, headline_falhou, roteiro_invalido.
--   * RPCs               -- cs_chat_resposta_gravar persists tipo/titulo/formato; NEW cs_chat_proposta_salvar_roteiro
--                           (roteiro-first step 2); NEW 4-arg cs_chat_proposta_salvar_headline(..., p_texto) carries
--                           the roteiro-first headline branch (step 4's write) and the forward branch; the existing
--                           3-arg signature is kept and delegates to it (the N-1 image keeps calling it unchanged).
--
-- Every state change is still ONE call to a SECURITY DEFINER function that writes its cs_fluxo_eventos row in the SAME
-- transaction. Records -> metrics (measurement-by-design): direction mix = chosen propostas by tipo; pick rate per
-- direction; time-to-card per direction (roteiro_salvo|headline_salva -> card_criado); headline-from-roteiro failure
-- rate (headline_falhou / roteiro_salvo).
--
-- Backward compatible with the previous image (N-1): additive columns with defaults, CHECKs only widened (a headline
-- row is held to exactly the old rules), the old RPC signature kept. FORWARD-ONLY, IDEMPOTENT.
-- GuardProbes: _SW_358_PROBES in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
-- Requires 352 (cs_chat_propostas, cs_fluxo_eventos, the chat RPCs).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_chat_propostas') IS NULL OR to_regclass('social_wiring.cs_fluxo_eventos') IS NULL THEN
    RAISE EXCEPTION 'Migration 358 requires cs_chat_propostas / cs_fluxo_eventos (migration 352) -- apply 352 first';
  END IF;
END
$guard$;

SET LOCAL lock_timeout = '5s';

-- ----------------------------------------------------------------------------
-- 1. cs_chat_propostas: tipo, titulo, formato, roteiro_id; widened texto + fluxo_etapa
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_chat_propostas ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'headline';
ALTER TABLE social_wiring.cs_chat_propostas ADD COLUMN IF NOT EXISTS titulo TEXT;
ALTER TABLE social_wiring.cs_chat_propostas ADD COLUMN IF NOT EXISTS formato TEXT;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD COLUMN IF NOT EXISTS roteiro_id UUID REFERENCES social_wiring.cs_roteiros (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS cs_chat_propostas_roteiro_idx
    ON social_wiring.cs_chat_propostas (roteiro_id) WHERE roteiro_id IS NOT NULL;

ALTER TABLE social_wiring.cs_chat_propostas DROP CONSTRAINT IF EXISTS cs_chat_propostas_tipo_check;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD CONSTRAINT cs_chat_propostas_tipo_check CHECK (tipo IN ('headline', 'roteiro')) NOT VALID;
ALTER TABLE social_wiring.cs_chat_propostas VALIDATE CONSTRAINT cs_chat_propostas_tipo_check;

ALTER TABLE social_wiring.cs_chat_propostas DROP CONSTRAINT IF EXISTS cs_chat_propostas_titulo_check;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD CONSTRAINT cs_chat_propostas_titulo_check CHECK (char_length(titulo) BETWEEN 1 AND 120) NOT VALID;
ALTER TABLE social_wiring.cs_chat_propostas VALIDATE CONSTRAINT cs_chat_propostas_titulo_check;

ALTER TABLE social_wiring.cs_chat_propostas DROP CONSTRAINT IF EXISTS cs_chat_propostas_formato_check;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD CONSTRAINT cs_chat_propostas_formato_check CHECK (formato IN ('reels', 'carrossel', 'stories', 'post')) NOT VALID;
ALTER TABLE social_wiring.cs_chat_propostas VALIDATE CONSTRAINT cs_chat_propostas_formato_check;

-- a roteiro carries its title and formato; a headline carries neither
ALTER TABLE social_wiring.cs_chat_propostas DROP CONSTRAINT IF EXISTS cs_chat_propostas_tipo_campos_check;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD CONSTRAINT cs_chat_propostas_tipo_campos_check
    CHECK ((tipo = 'roteiro') = (titulo IS NOT NULL AND formato IS NOT NULL)
           AND (tipo = 'roteiro' OR (titulo IS NULL AND formato IS NULL))) NOT VALID;
ALTER TABLE social_wiring.cs_chat_propostas VALIDATE CONSTRAINT cs_chat_propostas_tipo_campos_check;

-- a roteiro is a whole script (a carrossel can be long); a headline keeps the old 1..1000
ALTER TABLE social_wiring.cs_chat_propostas DROP CONSTRAINT IF EXISTS cs_chat_propostas_texto_check;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD CONSTRAINT cs_chat_propostas_texto_check
    CHECK (char_length(texto) BETWEEN 1 AND CASE WHEN tipo = 'roteiro' THEN 12000 ELSE 1000 END) NOT VALID;
ALTER TABLE social_wiring.cs_chat_propostas VALIDATE CONSTRAINT cs_chat_propostas_texto_check;

ALTER TABLE social_wiring.cs_chat_propostas DROP CONSTRAINT IF EXISTS cs_chat_propostas_fluxo_etapa_check;
ALTER TABLE social_wiring.cs_chat_propostas
    ADD CONSTRAINT cs_chat_propostas_fluxo_etapa_check
    CHECK (fluxo_etapa IN ('headline_salva', 'roteiro_salvo', 'headline_gerada', 'roteiro_criado', 'card_criado',
                           'concluido', 'falhou')) NOT VALID;
ALTER TABLE social_wiring.cs_chat_propostas VALIDATE CONSTRAINT cs_chat_propostas_fluxo_etapa_check;

-- ----------------------------------------------------------------------------
-- 2. cs_roteiros.proposta_id (a retried save is a lookup)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_roteiros ADD COLUMN IF NOT EXISTS proposta_id UUID;
CREATE UNIQUE INDEX IF NOT EXISTS cs_roteiros_conversa_proposta_uq
    ON social_wiring.cs_roteiros (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. cs_headlines.modo gains 'do_roteiro'
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_headlines DROP CONSTRAINT IF EXISTS cs_headlines_modo_check;
ALTER TABLE social_wiring.cs_headlines
    ADD CONSTRAINT cs_headlines_modo_check CHECK (modo IN ('manual', 'automatico', 'do_roteiro')) NOT VALID;
ALTER TABLE social_wiring.cs_headlines VALIDATE CONSTRAINT cs_headlines_modo_check;

-- ----------------------------------------------------------------------------
-- 4. cs_fluxo_eventos.tipo: the roteiro-first vocabulary (the ledger stays append-only and content-free)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_fluxo_eventos DROP CONSTRAINT IF EXISTS cs_fluxo_eventos_tipo_check;
ALTER TABLE social_wiring.cs_fluxo_eventos
    ADD CONSTRAINT cs_fluxo_eventos_tipo_check CHECK (tipo IN (
        'propostas_geradas', 'proposta_escolhida', 'headline_salva', 'roteiro_criado', 'roteiro_gerado', 'roteiro_falhou',
        'card_criado', 'card_falhou', 'legenda_gerada', 'legenda_falhou', 'fluxo_concluido', 'fluxo_retomado',
        'perfil_resolvido', 'perfil_ambiguo', 'perfil_nao_encontrado', 'citacao_rejeitada', 'atribuicao_ausente',
        'placeholder_remanescente', 'formato_misturado',
        'roteiro_salvo', 'headline_gerando', 'headline_gerada', 'headline_falhou', 'roteiro_invalido')) NOT VALID;
ALTER TABLE social_wiring.cs_fluxo_eventos VALIDATE CONSTRAINT cs_fluxo_eventos_tipo_check;

-- ----------------------------------------------------------------------------
-- 5. RPCs (service role only; SECURITY DEFINER, REVOKE EXECUTE below). One call = one transaction.
-- ----------------------------------------------------------------------------

-- 5.1 The assistant's answer: message + propostas (both kinds) + Estrutura links + events, atomically.
-- p = {org_id, conversa_id, user_id, conteudo, truncada, modelo, contexto_chars,
--      propostas: [{ordem, tipo, texto, titulo, formato, gatilho_tag, estrutura_ids: [uuid, ...]}],  (tipo default headline)
--      eventos:   [{tipo, contagem}]}
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
        INSERT INTO social_wiring.cs_chat_propostas
            (org_id, marca_id, conversa_id, mensagem_id, ordem, texto, gatilho_tag, tipo, titulo, formato)
        VALUES (v_org, v_marca, v_conversa, v_msg, (v_item->>'ordem')::smallint, v_item->>'texto',
                NULLIF(v_item->>'gatilho_tag', ''), COALESCE(NULLIF(v_item->>'tipo', ''), 'headline'),
                NULLIF(v_item->>'titulo', ''), NULLIF(v_item->>'formato', ''))
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

-- 5.2 roteiro-first step 2 -- the chosen script saved as-is: the cs_roteiros row (born `completo`: the user approved the
-- text by clicking it), one cs_estrutura_usos per cited Estrutura, fluxo_etapa='roteiro_salvo' and the event, in one
-- transaction. Idempotent: a retry finds the roteiro (UNIQUE (conversa_id, proposta_id)), writes no second uso and no
-- second event. `headline_texto` is NOT NULL on cs_roteiros and the headline does not exist yet: it holds the script's
-- title until 5.3 writes the generated headline over it.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_salvar_roteiro(p_proposta UUID, p_org UUID, p_user UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_prop social_wiring.cs_chat_propostas;
    v_r UUID;
    v_criado BOOLEAN := false;
BEGIN
    SELECT p.* INTO v_prop
      FROM social_wiring.cs_chat_propostas p
      JOIN social_wiring.cs_chat_conversas c ON c.id = p.conversa_id
     WHERE p.id = p_proposta AND p.org_id = p_org AND c.user_id = p_user
       FOR UPDATE OF p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposta_nao_encontrada';
    END IF;
    IF v_prop.tipo <> 'roteiro' THEN
        RAISE EXCEPTION 'proposta_nao_e_roteiro';
    END IF;
    IF v_prop.status <> 'escolhida' THEN
        RAISE EXCEPTION 'proposta_nao_escolhida';
    END IF;

    v_r := v_prop.roteiro_id;
    IF v_r IS NULL THEN
        INSERT INTO social_wiring.cs_roteiros
            (org_id, marca_id, created_by, nome, headline_texto, fonte, status, conteudo, formato, versao,
             conversa_id, proposta_id, finished_at)
        VALUES (v_prop.org_id, v_prop.marca_id, p_user, v_prop.titulo, v_prop.titulo, 'ia', 'completo', v_prop.texto,
                v_prop.formato, 1, v_prop.conversa_id, v_prop.id, now())
        ON CONFLICT (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL DO NOTHING
        RETURNING id INTO v_r;
        IF v_r IS NULL THEN
            SELECT id INTO v_r FROM social_wiring.cs_roteiros WHERE conversa_id = v_prop.conversa_id AND proposta_id = v_prop.id;
        END IF;
        UPDATE social_wiring.cs_chat_propostas SET roteiro_id = v_r WHERE id = v_prop.id;
    END IF;

    -- one use per cited Estrutura; the unique index (estrutura_id, roteiro_id) makes a retry a no-op
    INSERT INTO social_wiring.cs_estrutura_usos
        (org_id, marca_id, estrutura_id, contexto, papel, ordem, bloco_ids, roteiro_id, proposta_id, created_by)
    SELECT v_prop.org_id, v_prop.marca_id, pe.estrutura_id, 'chat',
           CASE WHEN pe.principal THEN 'principal' ELSE 'mistura' END, pe.ordem, '{}'::uuid[], v_r, v_prop.id, p_user
      FROM social_wiring.cs_chat_proposta_estruturas pe
     WHERE pe.proposta_id = v_prop.id
    ON CONFLICT DO NOTHING;

    IF v_prop.fluxo_etapa IS NULL THEN
        UPDATE social_wiring.cs_chat_propostas SET fluxo_etapa = 'roteiro_salvo' WHERE id = v_prop.id;
        PERFORM social_wiring.cs_fluxo_evento(v_prop.org_id, v_prop.marca_id, v_prop.conversa_id, 'roteiro_salvo',
                                              v_prop.id, v_prop.mensagem_id, NULL, v_r, NULL, p_user, NULL, NULL);
        v_criado := true;
    END IF;
    RETURN jsonb_build_object('roteiro_id', v_r, 'criado', v_criado);
END;
$fn$;

-- 5.3 The headline of a proposta, both directions, in one transaction. Idempotent: a retry finds the headline
-- (UNIQUE (conversa_id, proposta_id)), writes no second uso and no second event.
--   * tipo='headline' (forward step 2): exactly the 352 behaviour; p_texto must be NULL (the proposta IS the headline).
--   * tipo='roteiro'  (roteiro-first step 4's write): p_texto is the generated headline; the roteiro must already be saved.
--     Inserts cs_headlines (modo='do_roteiro', favorita), links it to the roteiro (headline_id + headline_texto), sets
--     fluxo_etapa='headline_gerada' (also out of 'falhou': a retried headline after headline_falhou recovers the flow)
--     and writes headline_gerada. The Estrutura usos were written against the roteiro by 5.2.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_salvar_headline(p_proposta UUID, p_org UUID, p_user UUID, p_texto TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_prop social_wiring.cs_chat_propostas;
    v_h UUID;
    v_texto TEXT := btrim(p_texto);
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

    IF v_prop.tipo = 'roteiro' THEN
        IF v_prop.roteiro_id IS NULL THEN
            RAISE EXCEPTION 'roteiro_nao_salvo';
        END IF;
        v_h := v_prop.headline_id;
        IF v_h IS NULL THEN
            IF v_texto IS NULL OR v_texto = '' THEN
                RAISE EXCEPTION 'headline_texto_ausente';
            END IF;
            INSERT INTO social_wiring.cs_headlines
                (org_id, marca_id, texto, conversa_id, proposta_id, modo, favorita, favoritada_em, created_by)
            VALUES (v_prop.org_id, v_prop.marca_id, v_texto, v_prop.conversa_id, v_prop.id, 'do_roteiro', true, now(), p_user)
            ON CONFLICT (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL DO NOTHING
            RETURNING id INTO v_h;
            IF v_h IS NULL THEN
                SELECT id INTO v_h FROM social_wiring.cs_headlines WHERE conversa_id = v_prop.conversa_id AND proposta_id = v_prop.id;
            END IF;
            UPDATE social_wiring.cs_chat_propostas SET headline_id = v_h WHERE id = v_prop.id;
            UPDATE social_wiring.cs_roteiros
               SET headline_id = v_h, headline_texto = (SELECT texto FROM social_wiring.cs_headlines WHERE id = v_h)
             WHERE id = v_prop.roteiro_id AND headline_id IS NULL;
        END IF;
        IF COALESCE(v_prop.fluxo_etapa, '') IN ('', 'roteiro_salvo', 'falhou') THEN
            UPDATE social_wiring.cs_chat_propostas SET fluxo_etapa = 'headline_gerada', fluxo_erro_codigo = NULL WHERE id = v_prop.id;
            PERFORM social_wiring.cs_fluxo_evento(v_prop.org_id, v_prop.marca_id, v_prop.conversa_id, 'headline_gerada',
                                                  v_prop.id, v_prop.mensagem_id, v_h, v_prop.roteiro_id, NULL, p_user, NULL, NULL);
            v_criada := true;
        END IF;
        RETURN jsonb_build_object('headline_id', v_h, 'criada', v_criada);
    END IF;

    -- forward (tipo='headline'): the proposta's own text is the headline
    IF p_texto IS NOT NULL THEN
        RAISE EXCEPTION 'headline_texto_inesperado';
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

-- 5.4 The 352 signature, kept so the N-1 image (and the forward saga) call it unchanged: delegates to 5.3.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_proposta_salvar_headline(p_proposta UUID, p_org UUID, p_user UUID)
RETURNS JSONB
LANGUAGE sql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
    SELECT social_wiring.cs_chat_proposta_salvar_headline(p_proposta, p_org, p_user, NULL::text);
$fn$;

-- ----------------------------------------------------------------------------
-- 6. RPC privileges: service role only
-- ----------------------------------------------------------------------------
REVOKE ALL ON FUNCTION social_wiring.cs_chat_resposta_gravar(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_salvar_roteiro(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_salvar_headline(UUID, UUID, UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_salvar_headline(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_resposta_gravar(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_salvar_roteiro(UUID, UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_salvar_headline(UUID, UUID, UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_salvar_headline(UUID, UUID, UUID) TO service_role;

COMMENT ON COLUMN social_wiring.cs_chat_propostas.tipo IS
    'headline | roteiro -- what the assistant proposed; the proposta''s tipo decides the escolher saga. Migration 358.';
COMMENT ON COLUMN social_wiring.cs_roteiros.proposta_id IS
    'The chat proposta this roteiro was saved from (roteiro-first); UNIQUE with conversa_id. Migration 358.';
