-- ============================================================================
-- Migration 269 -- social_wiring: Lais "Perguntas essenciais" (wave 2)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/social-wiring/projects/lais/specs/lais-build-contract.md section 4.
--   lais_perguntas_catalogo  GLOBAL catalogue (no org) of the questions Julia may ask, seeded from
--                            analysis/agent-brain.md section 2. `objetivo` is the locked one.
--                            `sensivel` marks a slot stored protected (contract 17): 'hash' (CPF) /
--                            'faixa' (renda) -- the handler hashes / buckets before it writes.
--   lais_perguntas_org       the org's selection: PK (org_id, chave). A row = a question the org
--                            switched on; `qualificatoria` = it counts toward "ready to send".
-- Limits (DB guard, trigger lais_perguntas_org_limites): <= 8 active, <= 5 qualifying, and the
-- `objetivo` row can be neither deleted nor deactivated. The API validates first (422 codes); the
-- trigger is the backstop for any other writer. A full-replace applies deletions + downgrades first
-- so every intermediate state also respects the limits.
--
-- RLS: select_own_org (authenticated) + service_role; the catalogue is readable by any
-- authenticated user. Writes go through the backend service client only (pattern 255/258/267).
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 014 (status_pagina), core 070.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'whatsapp_chat') THEN
    RAISE EXCEPTION 'Migration 269 requires the whatsapp_chat status row (migration 014) -- apply 014 first';
  END IF;
END
$guard$;

-- -- 1. catalogue (global) -------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_perguntas_catalogo (
    chave      text        PRIMARY KEY,
    label      text        NOT NULL,
    dica       text,
    categoria  text        NOT NULL,
    operacao   text,
    numerica   boolean     NOT NULL DEFAULT false,
    moeda      boolean     NOT NULL DEFAULT false,
    sensivel   text,
    ordem      integer     NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lais_perguntas_catalogo_chave_valida CHECK (chave ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT lais_perguntas_catalogo_categoria_valida
        CHECK (categoria IN ('operacao', 'lead', 'imovel', 'localizacao', 'financeiro', 'interesses')),
    CONSTRAINT lais_perguntas_catalogo_operacao_valida CHECK (operacao IS NULL OR operacao IN ('compra', 'aluguel')),
    CONSTRAINT lais_perguntas_catalogo_sensivel_valido CHECK (sensivel IS NULL OR sensivel IN ('hash', 'faixa'))
);

COMMENT ON TABLE social_wiring.lais_perguntas_catalogo IS
    'Global catalogue of Julia''s essential questions (migration 269); the org picks <= 8 of them.';

INSERT INTO social_wiring.lais_perguntas_catalogo (chave, label, dica, categoria, operacao, numerica, moeda, sensivel, ordem)
VALUES
    ('objetivo', 'Objetivo: comprar ou alugar', 'Descubra se o lead quer comprar, alugar ou outra operação; registre também com definir_operacao.', 'operacao', NULL, false, false, NULL, 1),
    ('nome', 'Nome', 'Pergunte como o lead gostaria de ser chamado.', 'lead', NULL, false, false, NULL, 2),
    ('email', 'E-mail', 'Peça um e-mail de contato, sem insistir se o lead recusar.', 'lead', NULL, false, false, NULL, 3),
    ('regiao_residencia', 'Região de residência atual', 'Pergunte em qual bairro ou cidade o lead mora hoje.', 'lead', NULL, false, false, NULL, 4),
    ('casado_filhos', 'Casado e tem filhos', 'Pergunte de forma natural sobre a composição familiar.', 'lead', NULL, false, false, NULL, 5),
    ('data_nascimento', 'Data de nascimento', 'Peça a data de nascimento apenas quando necessária para análise.', 'lead', NULL, false, false, NULL, 6),
    ('animal_estimacao', 'Animal de estimação', 'Pergunte se o lead tem animais de estimação; relevante para a locação.', 'lead', 'aluguel', false, false, NULL, 7),
    ('estado_civil', 'Estado civil', 'Pergunte o estado civil do lead.', 'lead', NULL, false, false, NULL, 8),
    ('filhos_menores', 'Filhos menores de idade', 'Pergunte se há filhos menores de idade na família.', 'lead', NULL, false, false, NULL, 9),
    ('cpf', 'CPF', 'Peça o CPF somente quando indispensável; o valor é guardado protegido.', 'lead', NULL, false, false, 'hash', 10),
    ('faixa_preco', 'Faixa de preço desejada', 'Descubra o valor máximo (ou a faixa) que o lead pretende investir ou pagar.', 'imovel', NULL, true, true, NULL, 11),
    ('tipo_imovel', 'Tipo do imóvel', 'Pergunte o tipo de imóvel buscado (casa, apartamento, terreno, comercial).', 'imovel', NULL, false, false, NULL, 12),
    ('tipo_imovel_compra', 'Tipo do imóvel – Compra', 'Mesmo comportamento de tipo do imóvel, mas perguntada somente nas conversas de usuários querendo comprar.', 'imovel', 'compra', false, false, NULL, 13),
    ('tipo_imovel_apartamento_casa', 'Tipo do imóvel: apartamento ou casa', 'Pergunte somente se o lead prefere apartamento ou casa.', 'imovel', NULL, false, false, NULL, 14),
    ('tamanho', 'Tamanho', 'Pergunte o tamanho aproximado desejado para o imóvel.', 'imovel', NULL, false, false, NULL, 15),
    ('caracteristicas_especificas', 'Características específicas', 'Pergunte se há características indispensáveis (piscina, quintal, varanda).', 'imovel', NULL, false, false, NULL, 16),
    ('planta_preferida', 'Planta preferida', 'Pergunte a planta ou o layout preferido.', 'imovel', 'compra', false, false, NULL, 17),
    ('interesse_principal', 'Interesse principal no imóvel', 'Descubra o que mais importa ao lead no imóvel.', 'imovel', NULL, false, false, NULL, 18),
    ('garagem', 'Garagem', 'Pergunte quantas vagas de garagem o lead precisa.', 'imovel', NULL, true, false, NULL, 19),
    ('idade_maxima', 'Idade máxima do imóvel', 'Pergunte a idade máxima aceitável do imóvel.', 'imovel', NULL, true, false, NULL, 20),
    ('banheiros', 'Número de banheiros', 'Pergunte quantos banheiros o lead precisa.', 'imovel', NULL, true, false, NULL, 21),
    ('quartos', 'Número de quartos', 'Pergunte quantos quartos o lead precisa.', 'imovel', NULL, true, false, NULL, 22),
    ('area_m2', 'Área em m²', 'Pergunte a área mínima desejada em metros quadrados.', 'imovel', NULL, true, false, NULL, 23),
    ('necessidade_especial', 'Necessidade especial', 'Pergunte se há necessidade de acessibilidade ou adaptação.', 'imovel', NULL, false, false, NULL, 24),
    ('cidade', 'Cidade', 'Pergunte em qual cidade o lead procura o imóvel.', 'localizacao', NULL, false, false, NULL, 25),
    ('proximidade_servicos', 'Proximidade a serviços', 'Pergunte de quais serviços o lead precisa perto (escola, mercado, transporte).', 'localizacao', NULL, false, false, NULL, 26),
    ('bairro_desejado', 'Bairro desejado', 'Pergunte em quais bairros o lead gostaria de morar.', 'localizacao', NULL, false, false, NULL, 27),
    ('renda_familiar', 'Renda familiar', 'Pergunte a renda familiar mensal; o valor é guardado apenas como faixa.', 'financeiro', NULL, true, true, 'faixa', 28),
    ('comprovacao_renda_3x', 'Comprovação de renda de 3× o aluguel', 'Pergunte se o lead comprova renda de pelo menos três vezes o valor do aluguel.', 'financeiro', 'aluguel', false, false, NULL, 29),
    ('recurso_entrada', 'Recurso para entrada', 'Pergunte de onde virá o recurso da entrada (poupança, FGTS, venda de imóvel).', 'financeiro', 'compra', false, false, NULL, 30),
    ('forma_pagamento', 'Forma de pagamento', 'Pergunte a forma de pagamento pretendida (à vista, financiamento, consórcio).', 'financeiro', 'compra', false, false, NULL, 31),
    ('parcela_ideal_financiamento', 'Parcela ideal de financiamento', 'Pergunte o valor de parcela mensal confortável.', 'financeiro', NULL, true, true, NULL, 32),
    ('garantia_locacao', 'Garantia a utilizar', 'Pergunte qual garantia o lead pretende usar (fiador, seguro-fiança, caução).', 'financeiro', 'aluguel', false, false, NULL, 33),
    ('permuta_imovel', 'Permuta com imóvel', 'Pergunte se o lead aceita ou tem imóvel para permuta.', 'financeiro', NULL, false, false, NULL, 34),
    ('documentacao_credito', 'Documentação para análise de crédito', 'Pergunte se o lead tem a documentação para análise de crédito.', 'financeiro', NULL, false, false, NULL, 35),
    ('compra_individual_conjunta', 'Compra individual ou conjunta', 'Pergunte se a compra será individual ou em conjunto.', 'financeiro', NULL, false, false, NULL, 36),
    ('valor_entrada', 'Valor de entrada disponível', 'Pergunte quanto o lead tem disponível para a entrada.', 'financeiro', NULL, true, true, NULL, 37),
    ('tipo_renda', 'Tipo de renda: formal ou informal', 'Pergunte se a renda é formal ou informal.', 'financeiro', NULL, false, false, NULL, 38),
    ('valor_adequado', 'Valor considerado adequado', 'Pergunte qual valor o lead considera adequado para o imóvel.', 'financeiro', NULL, true, true, NULL, 39),
    ('tempo_carteira_assinada', 'Tempo de carteira assinada (3 anos ou mais)', 'Pergunte há quanto tempo o lead tem carteira assinada.', 'financeiro', NULL, false, false, NULL, 40),
    ('locacao_anual_temporada', 'Locação anual ou temporada', 'Pergunte se a locação é anual ou por temporada.', 'interesses', 'aluguel', false, false, NULL, 41),
    ('tempo_busca', 'Tempo de busca', 'Pergunte há quanto tempo o lead procura um imóvel.', 'interesses', NULL, false, false, NULL, 42),
    ('conhecimento_documentacao', 'Conhecimento de documentação', 'Pergunte se o lead conhece a documentação necessária.', 'interesses', NULL, false, false, NULL, 43),
    ('estagio_busca', 'Estágio de busca', 'Descubra em que estágio da busca o lead está (pesquisando, comparando, decidido).', 'interesses', NULL, false, false, NULL, 44),
    ('motivo_localizacao', 'Motivo da localização', 'Pergunte por que o lead escolheu essa região.', 'interesses', NULL, false, false, NULL, 45),
    ('morar_ou_investir', 'Morar ou investir', 'Pergunte se o imóvel é para morar ou para investir.', 'interesses', NULL, false, false, NULL, 46),
    ('investimento_depreciacao_aluguel', 'Investimento: depreciação ou aluguel', 'Pergunte se o foco do investimento é valorização ou renda de aluguel.', 'interesses', NULL, false, false, NULL, 47),
    ('experiencia_aluguel', 'Experiência com aluguel', 'Pergunte se o lead já alugou imóvel antes.', 'interesses', 'aluguel', false, false, NULL, 48),
    ('tempo_locacao', 'Tempo de locação', 'Pergunte por quanto tempo o lead pretende alugar.', 'interesses', 'aluguel', false, false, NULL, 49),
    ('empreendimento_especifico', 'Empreendimento específico', 'Pergunte se o lead tem um empreendimento específico em mente.', 'interesses', NULL, false, false, NULL, 50),
    ('mais_info_ou_outras_opcoes', 'Mais informações do imóvel ou outras opções', 'Pergunte se o lead quer mais informações deste imóvel ou ver outras opções.', 'interesses', NULL, false, false, NULL, 51),
    ('decisao_imovel', 'Decisão por algum imóvel', 'Pergunte se o lead já decidiu por algum imóvel.', 'interesses', NULL, false, false, NULL, 52),
    ('prazo_compra', 'Prazo para compra', 'Pergunte em quanto tempo o lead pretende comprar.', 'interesses', 'compra', false, false, NULL, 53),
    ('prazo_mudanca', 'Prazo para mudança', 'Pergunte em quanto tempo o lead pretende se mudar.', 'interesses', NULL, false, false, NULL, 54),
    ('prazo_mudanca_aluguel', 'Prazo para mudança – Aluguel', 'Mesmo comportamento de prazo para mudança, mas perguntada somente nas conversas de usuários querendo alugar.', 'interesses', 'aluguel', false, false, NULL, 55),
    ('experiencia_compra_aluguel', 'Experiência comprando ou alugando', 'Pergunte se o lead já comprou ou alugou imóvel.', 'interesses', NULL, false, false, NULL, 56),
    ('parceria_ou_interesse', 'Parceria ou interesse no imóvel', 'Identifique se o contato é corretor buscando parceria ou cliente interessado no imóvel.', 'interesses', NULL, false, false, NULL, 57),
    ('imovel_proprio', 'Possui imóvel próprio', 'Pergunte se o lead possui imóvel próprio.', 'interesses', NULL, false, false, NULL, 58),
    ('pronto_ou_planta', 'Pronto ou na planta', 'Pergunte se o lead prefere imóvel pronto ou na planta.', 'interesses', 'compra', false, false, NULL, 59),
    ('conhecimento_processo_locacao', 'Conhecimento do processo de locação', 'Pergunte se o lead conhece o processo de locação.', 'interesses', 'aluguel', false, false, NULL, 60)
ON CONFLICT (chave) DO NOTHING;

-- -- 2. org selection --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.lais_perguntas_org (
    org_id         uuid        NOT NULL,
    chave          text        NOT NULL REFERENCES social_wiring.lais_perguntas_catalogo (chave),
    ativa          boolean     NOT NULL DEFAULT true,
    qualificatoria boolean     NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, chave),
    CONSTRAINT lais_perguntas_org_qualificatoria_ativa CHECK (NOT qualificatoria OR ativa)
);

COMMENT ON TABLE social_wiring.lais_perguntas_org IS
    'The org''s selected questions (migration 269). Limits enforced by trigger lais_perguntas_org_limites.';

-- -- 3. limits trigger ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.lais_perguntas_org_limites()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $fn$
DECLARE
  v_outras integer;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.chave = 'objetivo' THEN
      RAISE EXCEPTION 'a pergunta objetivo e obrigatoria'
        USING ERRCODE = 'check_violation', CONSTRAINT = 'lais_perguntas_org_objetivo_obrigatorio';
    END IF;
    RETURN OLD;
  END IF;

  IF NEW.chave = 'objetivo' AND NOT NEW.ativa THEN
    RAISE EXCEPTION 'a pergunta objetivo nao pode ser desativada'
      USING ERRCODE = 'check_violation', CONSTRAINT = 'lais_perguntas_org_objetivo_obrigatorio';
  END IF;

  IF NEW.ativa THEN
    SELECT count(*) INTO v_outras FROM social_wiring.lais_perguntas_org
     WHERE org_id = NEW.org_id AND chave <> NEW.chave AND ativa;
    IF v_outras >= 8 THEN
      RAISE EXCEPTION 'limite de 8 perguntas ativas por organizacao'
        USING ERRCODE = 'check_violation', CONSTRAINT = 'lais_perguntas_org_limites';
    END IF;
  END IF;

  IF NEW.qualificatoria THEN
    SELECT count(*) INTO v_outras FROM social_wiring.lais_perguntas_org
     WHERE org_id = NEW.org_id AND chave <> NEW.chave AND qualificatoria;
    IF v_outras >= 5 THEN
      RAISE EXCEPTION 'limite de 5 perguntas qualificatorias por organizacao'
        USING ERRCODE = 'check_violation', CONSTRAINT = 'lais_perguntas_org_limites';
    END IF;
  END IF;

  NEW.updated_at := now();
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS lais_perguntas_org_limites ON social_wiring.lais_perguntas_org;
CREATE TRIGGER lais_perguntas_org_limites
    BEFORE INSERT OR UPDATE OR DELETE ON social_wiring.lais_perguntas_org
    FOR EACH ROW EXECUTE FUNCTION social_wiring.lais_perguntas_org_limites();

-- -- 4. RLS ----------------------------------------------------------------------------
ALTER TABLE social_wiring.lais_perguntas_catalogo ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.lais_perguntas_org      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lais_perguntas_catalogo_select_authenticated" ON social_wiring.lais_perguntas_catalogo;
CREATE POLICY "lais_perguntas_catalogo_select_authenticated" ON social_wiring.lais_perguntas_catalogo
    FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "lais_perguntas_catalogo_service_role" ON social_wiring.lais_perguntas_catalogo;
CREATE POLICY "lais_perguntas_catalogo_service_role" ON social_wiring.lais_perguntas_catalogo
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lais_perguntas_org_select_own_org" ON social_wiring.lais_perguntas_org;
CREATE POLICY "lais_perguntas_org_select_own_org" ON social_wiring.lais_perguntas_org
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "lais_perguntas_org_service_role" ON social_wiring.lais_perguntas_org;
CREATE POLICY "lais_perguntas_org_service_role" ON social_wiring.lais_perguntas_org
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -- 5. status_pagina (copies whatsapp_chat, pattern 259) -----------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status, descricao)
SELECT novo.nome_pagina, origem.status, novo.descricao
  FROM (VALUES ('lais_perguntas', 'Lais — Perguntas essenciais')) AS novo (nome_pagina, descricao)
 CROSS JOIN social_wiring.status_pagina AS origem
 WHERE origem.nome_pagina = 'whatsapp_chat'
ON CONFLICT (nome_pagina) DO NOTHING;
