-- ============================================================================
-- Migration 367 · social_wiring: the Publicação of a chat proposta (criacao-pipeline-contract.md 2.3, slice S9)
-- ============================================================================
-- WHY
-- ---
-- The Diretor de Criação answers every option with a `### Publicação <n>` block (caption, exactly five hashtags, first
-- comment, the CTA objective + its justification, sources). SW parses and validates it when the reply is saved
-- (`services/publicacoes.py`) and must keep it until the option is picked: the card does not exist yet at that point,
-- and the proposta row has no room for it. So the block is its own dated table, one row per proposta that carried a
-- valid block (measurement-by-design: a business thing is a row, never a jsonb list on the proposta):
--
--   * cs_chat_proposta_publicacoes -- legenda, hashtags (CHECK: exactly 5), primeiro_comentario, cta, cta_objetivo (CHECK
--                                     enum, incl. 'nenhum'), cta_justificativa, fontes (jsonb array of
--                                     {url|afirmacao, verificada}). PK = proposta_id: a retried save is a no-op.
--                                     The post link is NOT here: it is the existing cs_posts.permalink, filled by hand.
--   * cs_fluxo_eventos.tipo         -- gains opcoes_selecionadas (a multi-select pick: contagem = N),
--                                     publicacao_gerada (a valid block stored for a proposta), publicacao_invalida
--                                     (blocks dropped by the validator / binder: contagem), publicacao_falhou (the
--                                     block could not be applied to the card: codigo).
--
-- Records -> metrics: CTA objective mix per org; share of options that carried a valid block; blocks rejected per reply;
-- batch size of multi-select picks; publication-apply failure rate.
--
-- Backward compatible with the previous image (N-1): a new table nobody reads yet, a CHECK only WIDENED.
-- FORWARD-ONLY, IDEMPOTENT. Requires 352/358 (cs_chat_propostas, cs_fluxo_eventos).
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_chat_propostas') IS NULL OR to_regclass('social_wiring.cs_fluxo_eventos') IS NULL THEN
    RAISE EXCEPTION 'Migration 367 requires cs_chat_propostas / cs_fluxo_eventos (migration 352) -- apply 352 first';
  END IF;
END
$guard$;

SET LOCAL lock_timeout = '5s';

-- ----------------------------------------------------------------------------
-- 1. cs_chat_proposta_publicacoes
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_chat_proposta_publicacoes (
    proposta_id         UUID PRIMARY KEY REFERENCES social_wiring.cs_chat_propostas (id) ON DELETE CASCADE,
    org_id              UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id            UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    -- the option number the block carried in the reply (audit: which `### Publicação <n>` it was)
    numero              INTEGER NOT NULL CHECK (numero >= 1),
    legenda             TEXT NOT NULL CONSTRAINT cs_chat_proposta_publicacoes_legenda_check
                            CHECK (char_length(legenda) BETWEEN 1 AND 2200),
    hashtags            TEXT[] NOT NULL CONSTRAINT cs_chat_proposta_publicacoes_hashtags_check
                            CHECK (cardinality(hashtags) = 5),
    primeiro_comentario TEXT CONSTRAINT cs_chat_proposta_publicacoes_comentario_check
                            CHECK (primeiro_comentario IS NULL OR char_length(primeiro_comentario) <= 2200),
    -- NULL = the post carries no CTA (cta_objetivo = 'nenhum')
    cta                 TEXT,
    cta_objetivo        TEXT NOT NULL CONSTRAINT cs_chat_proposta_publicacoes_cta_objetivo_check
                            CHECK (cta_objetivo IN ('alcance', 'salvamentos', 'conversa', 'seguidores', 'autoridade', 'reflexao', 'nenhum')),
    cta_justificativa   TEXT,
    fontes              JSONB NOT NULL DEFAULT '[]'::jsonb CONSTRAINT cs_chat_proposta_publicacoes_fontes_check
                            CHECK (jsonb_typeof(fontes) = 'array'),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cs_chat_proposta_publicacoes_org_idx
    ON social_wiring.cs_chat_proposta_publicacoes (org_id, cta_objetivo, created_at);
CREATE INDEX IF NOT EXISTS cs_chat_proposta_publicacoes_marca_idx
    ON social_wiring.cs_chat_proposta_publicacoes (marca_id);

-- ----------------------------------------------------------------------------
-- 2. cs_fluxo_eventos.tipo: the publication / multi-select vocabulary (the ledger stays append-only and content-free)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_fluxo_eventos DROP CONSTRAINT IF EXISTS cs_fluxo_eventos_tipo_check;
ALTER TABLE social_wiring.cs_fluxo_eventos
    ADD CONSTRAINT cs_fluxo_eventos_tipo_check CHECK (tipo IN (
        'propostas_geradas', 'proposta_escolhida', 'headline_salva', 'roteiro_criado', 'roteiro_gerado', 'roteiro_falhou',
        'card_criado', 'card_falhou', 'legenda_gerada', 'legenda_falhou', 'fluxo_concluido', 'fluxo_retomado',
        'perfil_resolvido', 'perfil_ambiguo', 'perfil_nao_encontrado', 'citacao_rejeitada', 'atribuicao_ausente',
        'placeholder_remanescente', 'formato_misturado',
        'roteiro_salvo', 'headline_gerando', 'headline_gerada', 'headline_falhou', 'roteiro_invalido',
        'opcoes_selecionadas', 'publicacao_gerada', 'publicacao_invalida', 'publicacao_falhou')) NOT VALID;
ALTER TABLE social_wiring.cs_fluxo_eventos VALIDATE CONSTRAINT cs_fluxo_eventos_tipo_check;

-- ----------------------------------------------------------------------------
-- 3. RLS + grants (service-only: the chat reads/writes only through the API), tier
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_chat_proposta_publicacoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_chat_proposta_publicacoes_service_role" ON social_wiring.cs_chat_proposta_publicacoes;
CREATE POLICY "cs_chat_proposta_publicacoes_service_role" ON social_wiring.cs_chat_proposta_publicacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_chat_proposta_publicacoes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.cs_chat_proposta_publicacoes TO service_role;

COMMENT ON TABLE social_wiring.cs_chat_proposta_publicacoes IS 'tier:org';
