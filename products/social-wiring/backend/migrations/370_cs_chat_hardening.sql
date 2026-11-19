-- ============================================================================
-- Migration 370 · social_wiring: CoreStudio chat hardening (prod findings + agents-security audit, 2026-11-19)
-- ============================================================================
-- WHY
-- ---
-- Three gaps seen on prod in the unified chat (chat_unificado on claude-opus-5):
--
--   1. The daily chat cap could be reset by the user. `ChatService.checar_caps` counted `cs_chat_mensagens` rows, and
--      deleting a conversation hard-deletes them: send N, delete, send again. Every user message now records an
--      append-only `mensagem_enviada` row in `cs_fluxo_eventos` (who / when / which message; no content) IN THE SAME
--      INSERT, through an AFTER INSERT trigger on `cs_chat_mensagens` -- so every writer (this image, the N-1 image, a
--      future one) records it by construction. `cs_fluxo_eventos.conversa_id` has no FK and the ledger is append-only,
--      so deleting the conversation never removes the count. A partial UNIQUE index keeps one row per message. The
--      existing user messages are backfilled (idempotent), so the cap reads the ledger alone from the first deploy.
--   2. `cs_roteiros.estrutura_ids` (migration 360, EST-RO 6.7) stayed `{}` on a roteiro saved from a chosen roteiro
--      proposta although the proposta cited its Estruturas. `cs_chat_proposta_salvar_roteiro` now writes them
--      (principal first, `cs_chat_proposta_estruturas.ordem`), on the insert and on a retry that finds an empty row;
--      the roteiros already saved that way are backfilled from their propostas.
--   3. The chat parser now refuses a headline that fails the untrusted-output guard (URL / domain / markdown image /
--      secret / injection echo, > 12 words, > 1000 chars): counted as `headline_invalida`.
--
-- `cs_fluxo_eventos.tipo` gains `mensagem_enviada` and `headline_invalida` (the 367 vocabulary is restated whole).
--
-- Records -> metrics: chat messages sent per user / org / day (survives conversation deletion: the cap's source and the
-- usage metric are one derivation); unsafe-headline rate per reply; roteiros per Estrutura from the roteiro-first path.
--
-- Backward compatible with the previous image (N-1): the trigger only ADDS a ledger row to an insert the N-1 image
-- already makes (it never reads it); the RPC keeps its signature and return shape; a CHECK only widened; the backfill
-- UPDATE touches only rows whose estrutura_ids is still empty. FORWARD-ONLY, IDEMPOTENT.
-- GuardProbes: _SW_370_PROBES in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
-- Requires 352 / 358 / 360 (cs_fluxo_eventos, the roteiro-first RPCs, cs_roteiros.estrutura_ids).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_fluxo_eventos') IS NULL OR to_regclass('social_wiring.cs_chat_propostas') IS NULL THEN
    RAISE EXCEPTION 'Migration 370 requires cs_fluxo_eventos / cs_chat_propostas (migration 352) -- apply 352 first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'social_wiring' AND table_name = 'cs_roteiros' AND column_name = 'estrutura_ids') THEN
    RAISE EXCEPTION 'Migration 370 requires cs_roteiros.estrutura_ids (migration 360) -- apply 360 first';
  END IF;
END
$guard$;

SET LOCAL lock_timeout = '5s';

-- ----------------------------------------------------------------------------
-- 1. cs_fluxo_eventos.tipo: + mensagem_enviada, headline_invalida (the ledger stays append-only and content-free)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_fluxo_eventos DROP CONSTRAINT IF EXISTS cs_fluxo_eventos_tipo_check;
ALTER TABLE social_wiring.cs_fluxo_eventos
    ADD CONSTRAINT cs_fluxo_eventos_tipo_check CHECK (tipo IN (
        'propostas_geradas', 'proposta_escolhida', 'headline_salva', 'roteiro_criado', 'roteiro_gerado', 'roteiro_falhou',
        'card_criado', 'card_falhou', 'legenda_gerada', 'legenda_falhou', 'fluxo_concluido', 'fluxo_retomado',
        'perfil_resolvido', 'perfil_ambiguo', 'perfil_nao_encontrado', 'citacao_rejeitada', 'atribuicao_ausente',
        'placeholder_remanescente', 'formato_misturado',
        'roteiro_salvo', 'headline_gerando', 'headline_gerada', 'headline_falhou', 'roteiro_invalido',
        'opcoes_selecionadas', 'publicacao_gerada', 'publicacao_invalida', 'publicacao_falhou',
        'mensagem_enviada', 'headline_invalida')) NOT VALID;
ALTER TABLE social_wiring.cs_fluxo_eventos VALIDATE CONSTRAINT cs_fluxo_eventos_tipo_check;

-- one ledger row per sent message (the trigger and the backfill can never double-count one)
CREATE UNIQUE INDEX IF NOT EXISTS cs_fluxo_eventos_mensagem_enviada_uq
    ON social_wiring.cs_fluxo_eventos (mensagem_id) WHERE tipo = 'mensagem_enviada';
-- the per-user cap read: (org, ator) inside the 24 h window
CREATE INDEX IF NOT EXISTS cs_fluxo_eventos_mensagem_enviada_ator_idx
    ON social_wiring.cs_fluxo_eventos (org_id, ator_id, created_at) WHERE tipo = 'mensagem_enviada';

-- ----------------------------------------------------------------------------
-- 2. Every user message records `mensagem_enviada` in the same INSERT
-- ----------------------------------------------------------------------------
-- Invoker (the writer's own role): service_role already holds INSERT on cs_fluxo_eventos and SELECT on the conversations.
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_mensagem_enviada()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
BEGIN
    INSERT INTO social_wiring.cs_fluxo_eventos (org_id, marca_id, conversa_id, mensagem_id, ator_id, tipo)
    SELECT NEW.org_id, c.marca_id, NEW.conversa_id, NEW.id, c.user_id, 'mensagem_enviada'
      FROM social_wiring.cs_chat_conversas c
     WHERE c.id = NEW.conversa_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'cs_chat_mensagem_enviada: conversa % não encontrada', NEW.conversa_id;
    END IF;
    RETURN NULL;
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_chat_mensagem_enviada() FROM PUBLIC, anon, authenticated;
COMMENT ON FUNCTION social_wiring.cs_chat_mensagem_enviada() IS
    'Records mensagem_enviada (cs_fluxo_eventos) for every user chat message, in the same INSERT: the daily chat cap and '
    'the messages-sent metric read the append-only ledger, which survives conversation deletion (migration 370).';

DROP TRIGGER IF EXISTS cs_chat_mensagem_enviada ON social_wiring.cs_chat_mensagens;
CREATE TRIGGER cs_chat_mensagem_enviada
    AFTER INSERT ON social_wiring.cs_chat_mensagens
    FOR EACH ROW WHEN (NEW.role = 'user')
    EXECUTE FUNCTION social_wiring.cs_chat_mensagem_enviada();

-- backfill: the user messages that exist today (their own created_at, so the 24 h window is right from the first read)
INSERT INTO social_wiring.cs_fluxo_eventos (org_id, marca_id, conversa_id, mensagem_id, ator_id, tipo, created_at)
SELECT m.org_id, c.marca_id, m.conversa_id, m.id, c.user_id, 'mensagem_enviada', m.created_at
  FROM social_wiring.cs_chat_mensagens m
  JOIN social_wiring.cs_chat_conversas c ON c.id = m.conversa_id
 WHERE m.role = 'user'
   AND NOT EXISTS (SELECT 1 FROM social_wiring.cs_fluxo_eventos e
                    WHERE e.tipo = 'mensagem_enviada' AND e.mensagem_id = m.id);

-- ----------------------------------------------------------------------------
-- 3. cs_chat_proposta_salvar_roteiro writes cs_roteiros.estrutura_ids (same signature, same return)
-- ----------------------------------------------------------------------------
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
    v_estruturas UUID[];
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

    -- the Estruturas the proposta cited, principal first (1..3: the links' own CHECK)
    SELECT COALESCE(array_agg(pe.estrutura_id ORDER BY pe.ordem), '{}'::uuid[]) INTO v_estruturas
      FROM social_wiring.cs_chat_proposta_estruturas pe
     WHERE pe.proposta_id = v_prop.id;

    v_r := v_prop.roteiro_id;
    IF v_r IS NULL THEN
        INSERT INTO social_wiring.cs_roteiros
            (org_id, marca_id, created_by, nome, headline_texto, fonte, status, conteudo, formato, versao,
             conversa_id, proposta_id, finished_at, estrutura_ids)
        VALUES (v_prop.org_id, v_prop.marca_id, p_user, v_prop.titulo, v_prop.titulo, 'ia', 'completo', v_prop.texto,
                v_prop.formato, 1, v_prop.conversa_id, v_prop.id, now(), v_estruturas)
        ON CONFLICT (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL DO NOTHING
        RETURNING id INTO v_r;
        IF v_r IS NULL THEN
            SELECT id INTO v_r FROM social_wiring.cs_roteiros WHERE conversa_id = v_prop.conversa_id AND proposta_id = v_prop.id;
        END IF;
        UPDATE social_wiring.cs_chat_propostas SET roteiro_id = v_r WHERE id = v_prop.id;
    END IF;
    -- a roteiro saved before this migration (or found by the crash-repair lookup) gets its Estruturas once
    UPDATE social_wiring.cs_roteiros SET estrutura_ids = v_estruturas
     WHERE id = v_r AND cardinality(estrutura_ids) = 0 AND cardinality(v_estruturas) > 0;

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
REVOKE ALL ON FUNCTION social_wiring.cs_chat_proposta_salvar_roteiro(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_proposta_salvar_roteiro(UUID, UUID, UUID) TO service_role;

-- backfill: the roteiros already saved from a roteiro proposta with an empty estrutura_ids
UPDATE social_wiring.cs_roteiros r
   SET estrutura_ids = sub.ids
  FROM (SELECT pe.proposta_id, array_agg(pe.estrutura_id ORDER BY pe.ordem) AS ids
          FROM social_wiring.cs_chat_proposta_estruturas pe
         GROUP BY pe.proposta_id) sub
 WHERE r.proposta_id = sub.proposta_id
   AND cardinality(r.estrutura_ids) = 0;
