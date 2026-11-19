-- ============================================================================
-- Migration 360 · social_wiring: the chat saga's steps 4-7 (RP-3 of estruturas-contract.md section 16.6 / 9.2-9.3)
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/core-studio-build/specs/estruturas-contract.md sections 9.2 steps 4-7, 9.3 and
-- 16.6. The steps after the claim / save / pre-flight (roteiro, card, finalizer job, roteiro_gerado message, and for a
-- chosen roteiro the generated headline) run in the API and in two queue jobs. The service role holds SELECT only on
-- cs_chat_propostas (352), so the saga's progress (`fluxo_etapa`) and its events are recorded through ONE definer RPC:
--
--   * cs_chat_fluxo_registrar(p_proposta, p_org, p_user, p_tipo, p_etapa, p_erro, p_headline, p_roteiro, p_post, p_codigo)
--       row-locks the proposta; moves `fluxo_etapa` FORWARD only (headline_salva|roteiro_salvo < roteiro_criado|
--       headline_gerada < card_criado < concluido); `falhou` is reachable from anything but `concluido` (sets
--       `fluxo_erro_codigo`) and a later forward step recovers from it (clears the code); `concluido` is terminal.
--       The event is written in the SAME transaction, once: when the etapa moved, or (no move) when no event with the
--       same (proposta, tipo, codigo) exists yet -- so a retried step never writes a second row.
--   * cs_roteiros.estrutura_ids -- the Estruturas a roteiro was asked to follow (principal first, 1..3; EST-RO 6.7),
--       read by the generation job. Empty array = none (the legacy reels path).
--
-- Records -> metrics (measurement-by-design): time per step per direction (roteiro_criado / headline_gerada ->
-- card_criado -> fluxo_concluido), card failure rate (card_falhou / card_criado), caption outcome mix
-- (legenda_gerada / legenda_falhou by codigo), finalizer timeouts (roteiro_falhou codigo='demorou').
--
-- Backward compatible with the previous image (N-1): one additive column with a constant default (no rewrite), one
-- NEW function; nothing dropped / renamed / retyped. FORWARD-ONLY, IDEMPOTENT. Requires 352 + 358.
-- ============================================================================

SET search_path = social_wiring, public;
SET lock_timeout = '5s';

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_chat_propostas') IS NULL OR to_regclass('social_wiring.cs_fluxo_eventos') IS NULL
     OR NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'social_wiring'
                    AND table_name = 'cs_chat_propostas' AND column_name = 'roteiro_id') THEN
    RAISE EXCEPTION 'Migration 360 requires migrations 352 and 358 (cs_chat_propostas.roteiro_id) -- apply them first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. cs_roteiros.estrutura_ids (EST-RO 6.7)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_roteiros ADD COLUMN IF NOT EXISTS estrutura_ids UUID[] NOT NULL DEFAULT '{}'::uuid[];
ALTER TABLE social_wiring.cs_roteiros DROP CONSTRAINT IF EXISTS cs_roteiros_estrutura_ids_max;
ALTER TABLE social_wiring.cs_roteiros
    ADD CONSTRAINT cs_roteiros_estrutura_ids_max CHECK (cardinality(estrutura_ids) <= 3) NOT VALID;
ALTER TABLE social_wiring.cs_roteiros VALIDATE CONSTRAINT cs_roteiros_estrutura_ids_max;
COMMENT ON COLUMN social_wiring.cs_roteiros.estrutura_ids IS
    'The Estruturas this roteiro follows (principal first, at most 3); empty = none. EST-RO (estruturas-contract 6.7).';

-- ----------------------------------------------------------------------------
-- 2. the saga's progress + its event, one transaction
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.cs_chat_fluxo_registrar(
    p_proposta UUID, p_org UUID, p_user UUID, p_tipo TEXT, p_etapa TEXT, p_erro TEXT,
    p_headline UUID, p_roteiro UUID, p_post UUID, p_codigo TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_p social_wiring.cs_chat_propostas%ROWTYPE;
    v_atual TEXT;
    v_mudou BOOLEAN := false;
    v_rank_atual INTEGER;
    v_rank_novo INTEGER;
    v_gravou BOOLEAN := false;
BEGIN
    IF p_tipo IS NULL OR p_tipo NOT IN (
        'roteiro_criado', 'headline_gerando', 'headline_falhou', 'card_criado', 'card_falhou', 'roteiro_gerado',
        'roteiro_falhou', 'legenda_gerada', 'legenda_falhou', 'fluxo_concluido', 'roteiro_invalido') THEN
        RAISE EXCEPTION 'evento_invalido';
    END IF;
    IF p_etapa IS NOT NULL AND p_etapa NOT IN ('roteiro_criado', 'card_criado', 'concluido', 'falhou') THEN
        RAISE EXCEPTION 'etapa_invalida';
    END IF;
    IF p_etapa = 'falhou' AND NULLIF(btrim(COALESCE(p_erro, '')), '') IS NULL THEN
        RAISE EXCEPTION 'erro_obrigatorio';
    END IF;

    SELECT * INTO v_p FROM social_wiring.cs_chat_propostas
     WHERE id = p_proposta AND org_id = p_org FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposta_nao_encontrada';
    END IF;
    IF v_p.status <> 'escolhida' THEN
        RAISE EXCEPTION 'proposta_nao_escolhida';
    END IF;

    v_atual := v_p.fluxo_etapa;
    IF v_atual IS DISTINCT FROM 'concluido' AND p_etapa IS NOT NULL THEN
        IF p_etapa = 'falhou' THEN
            IF v_atual IS DISTINCT FROM 'falhou' THEN
                UPDATE social_wiring.cs_chat_propostas
                   SET fluxo_etapa = 'falhou', fluxo_erro_codigo = btrim(p_erro) WHERE id = v_p.id;
                v_mudou := true;
            END IF;
        ELSE
            v_rank_atual := CASE v_atual
                WHEN 'headline_salva' THEN 1 WHEN 'roteiro_salvo' THEN 1
                WHEN 'roteiro_criado' THEN 2 WHEN 'headline_gerada' THEN 2
                WHEN 'card_criado' THEN 3 ELSE 0 END;
            v_rank_novo := CASE p_etapa WHEN 'roteiro_criado' THEN 2 WHEN 'card_criado' THEN 3 ELSE 4 END;
            IF v_atual = 'falhou' OR v_rank_novo > v_rank_atual THEN
                UPDATE social_wiring.cs_chat_propostas
                   SET fluxo_etapa = p_etapa, fluxo_erro_codigo = NULL WHERE id = v_p.id;
                v_mudou := true;
            END IF;
        END IF;
    END IF;

    IF v_mudou OR NOT EXISTS (
        SELECT 1 FROM social_wiring.cs_fluxo_eventos e
         WHERE e.proposta_id = v_p.id AND e.tipo = p_tipo AND COALESCE(e.codigo, '') = COALESCE(p_codigo, '')) THEN
        PERFORM social_wiring.cs_fluxo_evento(v_p.org_id, v_p.marca_id, v_p.conversa_id, p_tipo, v_p.id, NULL,
            COALESCE(p_headline, v_p.headline_id), COALESCE(p_roteiro, v_p.roteiro_id), p_post, p_user, NULL, p_codigo);
        v_gravou := true;
    END IF;

    RETURN jsonb_build_object(
        'etapa', CASE WHEN v_mudou THEN COALESCE(p_etapa, v_atual) ELSE v_atual END,
        'mudou', v_mudou, 'registrado', v_gravou);
END;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_chat_fluxo_registrar(UUID, UUID, UUID, TEXT, TEXT, TEXT, UUID, UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_chat_fluxo_registrar(UUID, UUID, UUID, TEXT, TEXT, TEXT, UUID, UUID, UUID, TEXT)
    TO service_role;

COMMENT ON FUNCTION social_wiring.cs_chat_fluxo_registrar(UUID, UUID, UUID, TEXT, TEXT, TEXT, UUID, UUID, UUID, TEXT) IS
    'Saga steps 4-7: forward-only fluxo_etapa + its cs_fluxo_eventos row, once, in one transaction (estruturas-contract 9.2/16.6).';
