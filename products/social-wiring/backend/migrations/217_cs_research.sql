-- ============================================================================
-- Migration 217 · social_wiring: Minha Pesquisa (CoreStudio rebuild) —
-- `cs_research_variables` (static 40-row taxonomy) + `cs_research_items`
-- ============================================================================
-- WHY
-- ---
-- Per-marca research items (pains, desires, fears, ...) that later feed
-- headline generation. Contract: projects/core-studio/specs/pesquisa-contract.md
-- section 2. Owner decisions: scoped per marca; all 40 variables; manual add =
-- approved, AI-produced = pending, rejected = soft (kept for dedupe/audit,
-- never listed).
--
-- The 40-row seed is GENERATED from the Python source of truth
-- (app/modules/media_creation/pesquisa_variables.py :: seed_sql()); a test
-- asserts this file carries exactly that text, so taxonomy and classifier
-- prompt cannot drift from the table.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'migration 217 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Static taxonomy
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_research_variables (
    slug          TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    grupo         TEXT NOT NULL CHECK (grupo IN ('publico', 'especialista', 'produto', 'global')),
    description   TEXT NOT NULL,
    corestudio_id INTEGER,
    sort_order    INTEGER NOT NULL,
    classifiable  BOOLEAN NOT NULL DEFAULT true
);

COMMENT ON TABLE social_wiring.cs_research_variables IS
    'Migration 217 - Minha Pesquisa taxonomy: 29 CoreStudio variables + 4 globals + 7 classifier-only. '
    'Seeded from pesquisa_variables.py; read-only for authenticated users.';

-- ----------------------------------------------------------------------------
-- 2. Items
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_research_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id      UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    variable_slug TEXT NOT NULL REFERENCES social_wiring.cs_research_variables (slug),
    content       TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 500 AND content = btrim(content)),
    status        TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    origin        TEXT NOT NULL CHECK (origin IN ('manual', 'ai_classified', 'extraction')),
    source_ref    JSONB,
    plays         BIGINT,
    created_by    UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_research_items IS
    'Migration 217 - Minha Pesquisa items, per marca. manual => approved; ai_classified/extraction => pending; '
    'rejected is soft (kept for dedupe/audit, never listed).';

CREATE UNIQUE INDEX IF NOT EXISTS cs_research_items_dedupe_uq
    ON social_wiring.cs_research_items (marca_id, variable_slug, lower(content));

CREATE INDEX IF NOT EXISTS cs_research_items_marca_status_idx
    ON social_wiring.cs_research_items (marca_id, status, created_at DESC);

DROP TRIGGER IF EXISTS set_updated_at_cs_research_items ON social_wiring.cs_research_items;
CREATE TRIGGER set_updated_at_cs_research_items
    BEFORE UPDATE ON social_wiring.cs_research_items
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

-- ----------------------------------------------------------------------------
-- 3. RLS
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_research_variables ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_research_variables_select" ON social_wiring.cs_research_variables;
CREATE POLICY "cs_research_variables_select"
    ON social_wiring.cs_research_variables
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_research_variables_service_role" ON social_wiring.cs_research_variables;
CREATE POLICY "cs_research_variables_service_role"
    ON social_wiring.cs_research_variables
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_research_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_research_items_select_own_org" ON social_wiring.cs_research_items;
CREATE POLICY "cs_research_items_select_own_org"
    ON social_wiring.cs_research_items
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_research_items_write_own_org" ON social_wiring.cs_research_items;
CREATE POLICY "cs_research_items_write_own_org"
    ON social_wiring.cs_research_items
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_research_items_service_role" ON social_wiring.cs_research_items;
CREATE POLICY "cs_research_items_service_role"
    ON social_wiring.cs_research_items
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. Seed: exactly 40 variables (generated -- do not hand-edit)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.cs_research_variables
    (slug, label, grupo, description, corestudio_id, sort_order, classifiable)
VALUES
    ('DESEJOS-TANGIVEIS-DO-AVATAR', 'Desejos do meu público', 'publico', 'Resultados concretos que o avatar quer alcançar', 18, 1, true),
    ('DORES-TANGIVEIS-DO-AVATAR', 'Dores do meu público', 'publico', 'Problemas concretos que o avatar vive agora', 17, 2, true),
    ('CARACTERISTICAS-DEMOGRAFICAS-DO-AVATAR', 'Características demográficas do meu público', 'publico', 'Gênero, idade, profissão, estado civil, localização, renda, escolaridade', 16, 3, true),
    ('CARACTERISTICAS-POSITIVAS-DO-AVATAR', 'Qualidades do meu público', 'publico', 'Qualidades e pontos fortes do avatar', 25, 4, true),
    ('CARACTERISTICAS-NEGATIVAS-DO-AVATAR', 'Defeitos do meu público', 'publico', 'Defeitos e pontos fracos do avatar', 26, 5, true),
    ('ITENS-CONHECIDOS-PELO-AVATAR', 'Itens conhecidos pelo meu público', 'publico', 'Objetos, marcas e coisas do dia a dia que o público reconhece', 15, 6, true),
    ('INSTITUICOES-CONHECIDAS-PELO-AVATAR', 'Instituições conhecidas pelo meu público', 'publico', 'Órgãos, empresas e instituições que o público conhece', 14, 7, true),
    ('PESSOAS-PERSONAGENS-CONHECIDOS-PELO-AVATAR', 'Pessoas e personagens conhecidos pelo meu público', 'publico', 'Figuras, celebridades, personagens que o público reconhece', 13, 8, true),
    ('INIMIGOS-DO-AVATAR', 'Inimigos do meu público', 'publico', 'Pessoas, grupos ou coisas que o público considera inimigas', 32, 9, true),
    ('FILMES-SERIES-E-MUSICAS-CONHECIDAS-PELO-AVATAR', 'Filmes, séries ou músicas conhecidas pelo meu público', 'publico', 'Filmes, séries e músicas que o público reconhece', 11, 10, true),
    ('EVENTOS-CONHECIDOS-PELO-AVATAR', 'Eventos conhecidos pelo meu público', 'publico', 'Eventos, datas e acontecimentos que o público reconhece', 19, 11, true),
    ('LOCAIS-CONHECIDOS-PELO-AVATAR', 'Locais conhecidos pelo meu público', 'publico', 'Lugares que o público conhece e frequenta', 20, 12, true),
    ('MOMENTO-DE-VIDA-DO-AVATAR', 'Momentos de vida do meu público', 'publico', 'Fases e momentos de vida pelos quais o avatar passa', 21, 13, true),
    ('OBJECOES-DO-AVATAR', 'Objeções do meu público', 'publico', 'Barreiras e dúvidas que impedem ação/compra', 10, 14, true),
    ('MEDOS-DO-AVATAR', 'Medos do meu público', 'publico', 'Cenários futuros negativos que o avatar teme', 9, 15, true),
    ('CRENCAS-DO-AVATAR', 'Crenças do meu público', 'publico', 'Crenças do avatar sobre o mundo, o dinheiro e a sociedade', 8, 16, true),
    ('DESEJOS-ALCANCADOS-PELO-ESPECIALISTA', 'Desejos e conquistas que eu realizei', 'especialista', 'Desejos e conquistas que o especialista já realizou', 5, 17, true),
    ('PRODUTOS-CONHECIDOS-PELO-AVATAR', 'Produtos conhecidos pelo meu público', 'publico', 'Produtos que o público conhece e reconhece', 34, 18, true),
    ('SITUACOES-DOLOROSAS-DA-VIDA-DO-ESPECIALISTA', 'Situações dolorosas que eu enfrentei', 'especialista', 'Situações dolorosas que o especialista viveu', 4, 19, true),
    ('HABITOS-DO-ESPECIALISTA', 'Meus hábitos e hobbies', 'especialista', 'Hábitos e hobbies do especialista', 30, 20, true),
    ('FORMACAO-PROFISSAO-DO-ESPECIALISTA', 'Minha formação profissional', 'especialista', 'Formação e profissão do especialista', 31, 21, true),
    ('CARACTERISTICAS-DEMOGRAFICAS-DO-ESPECIALISTA', 'Quem eu sou (idade, estado civil, nacionalidade, etc)', 'especialista', 'Quem é o especialista: idade, estado civil, nacionalidade', 28, 22, true),
    ('CARACTERISTICAS-POSITIVAS-DO-ESPECIALISTA', 'Minhas qualidades', 'especialista', 'Qualidades do especialista', 7, 23, true),
    ('CARACTERISTICAS-NEGATIVAS-DO-ESPECIALISTA', 'Meus defeitos', 'especialista', 'Defeitos do especialista', 27, 24, true),
    ('TECNICAS-E-PROCEDIMENTOS-EFETUADOS-PELO-ESPECIALISTA', 'Técnicas, serviços e procedimentos que eu efetuo', 'especialista', 'Técnicas, serviços e procedimentos que o especialista efetua', 6, 25, true),
    ('TECNICAS-PROCEDIMENTOS-NAO-RECOMENDADOS-PELO-ESPECIALISTA', 'Técnicas, serviços e procedimentos que eu não recomendo', 'especialista', 'Técnicas, serviços e procedimentos que o especialista não recomenda', 12, 26, true),
    ('HABITOS-RECOMENDADOS-PELO-ESPECIALISTA', 'Hábitos que eu recomendo para o meu público', 'especialista', 'Hábitos que o especialista recomenda ao público', 3, 27, true),
    ('HABITOS-NAO-RECOMENDADOS-PELO-ESPECIALISTA', 'Hábitos que eu não recomendo para o meu público', 'especialista', 'Hábitos que o especialista não recomenda ao público', 2, 28, true),
    ('CRENCAS-DO-ESPECIALISTA', 'Crenças e ideias que eu defendo', 'especialista', 'Crenças e ideias que o especialista defende', 1, 29, true),
    ('FRUSTRACOES-DO-AVATAR', 'Frustrações do meu público', 'publico', 'Tentativas passadas que falharam', NULL, 30, true),
    ('CRENCAS-LIMITANTES-DO-AVATAR', 'Crenças limitantes do meu público', 'publico', 'Crenças internas negativas sobre si mesmo', NULL, 31, true),
    ('INIMIGO-COMUM', 'Inimigo comum', 'publico', 'Vilão externo que o avatar culpa', NULL, 32, true),
    ('MECANISMO-UNICO', 'Mecanismo único', 'produto', 'Método ou sistema que diferencia a solução', NULL, 33, true),
    ('PROMESSA-PRINCIPAL', 'Promessa principal', 'produto', 'Transformação central prometida', NULL, 34, true),
    ('PROVA-SOCIAL', 'Prova social', 'produto', 'Resultados de terceiros, números, autoridade', NULL, 35, true),
    ('NICHO-OU-MERCADO', 'Nicho ou mercado', 'produto', 'Área ou segmento do produto', NULL, 36, true),
    ('VERBOS-PODEROSOS', 'Verbos Poderosos', 'global', 'Lista global de verbos de impacto', 22, 37, false),
    ('ADJETIVOS-PODEROSOS', 'Adjetivos Poderosos', 'global', 'Lista global de adjetivos de impacto', 23, 38, false),
    ('MOMENTO-DO-DIA', 'Momento do dia', 'global', 'Momentos do dia (manhã, tarde, noite…)', 24, 39, false),
    ('GPT', 'GPT', 'global', 'Lista global GPT (uso a refinar)', 29, 40, false)
ON CONFLICT (slug) DO UPDATE SET
    label = EXCLUDED.label, grupo = EXCLUDED.grupo,
    description = EXCLUDED.description, corestudio_id = EXCLUDED.corestudio_id,
    sort_order = EXCLUDED.sort_order, classifiable = EXCLUDED.classifiable;
