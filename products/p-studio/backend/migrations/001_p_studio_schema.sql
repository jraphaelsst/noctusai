-- ============================================================================
-- 001_p_studio_schema.sql — P Studio
-- Schema: p_studio
--
-- Sistema de gestão operacional e financeira de uma produtora de fotografia e
-- audiovisual imobiliário. Padrão NoctusAI: 1 produto = 1 schema Postgres,
-- RLS em todas as tabelas, escopo por organização.
--
-- Modelo: `negocios` é a espinha dorsal. Um negócio aponta para um cliente e
-- (opcionalmente) um imóvel, contrata um conjunto de serviços, e origina uma
-- captação (agenda), uma produção (pós) e um ou mais lançamentos financeiros.
-- Os três pipelines correm em paralelo e avançam de forma independente —
-- por isso são tabelas separadas com status próprios, e não um único campo.
--
-- Acesso: todos os membros da organização enxergam e gerenciam os dados da
-- organização, via public.current_org_id() (SECURITY DEFINER, lê a tabela
-- confiável public.noctus_users — nunca user_metadata do JWT, que é editável
-- pelo próprio usuário).
-- ============================================================================

SET search_path = p_studio, public;

CREATE SCHEMA IF NOT EXISTS p_studio;

-- Grants exigidos pelo PostgREST (padrão do template product-seed)
GRANT USAGE ON SCHEMA p_studio TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA p_studio GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA p_studio GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Helpers
-- ============================================================================

CREATE OR REPLACE FUNCTION p_studio.set_updated_at()
  RETURNS trigger
  LANGUAGE plpgsql
AS $f$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$f$;

-- Resolve a organização do usuário logado.
--
-- **Esta função é do Core da plataforma, não nossa.** Toda policy de RLS de
-- todo produto depende dela. Por isso aqui ela é criada SÓ SE NÃO EXISTIR —
-- nunca substituída.
--
-- A versão anterior usava CREATE OR REPLACE "por idempotência". Não é
-- idempotência: é a migration de um produto com poder de redefinir, em
-- silêncio, o predicado de autorização de todos os outros. Basta alguém editar
-- esta cópia, ou o Core evoluir a dele, e o próximo `psql -f 001` reescreve a
-- função viva. O corpo abaixo confere byte a byte com o Core em 13/08/2026, o
-- que só significa que hoje daria certo — o risco não é o corpo, é o verbo.
--
-- O CREATE continua existindo para o caso de bootstrap num Supabase limpo, que
-- foi o motivo original.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'current_org_id'
  ) THEN
    EXECUTE $f$
      CREATE FUNCTION public.current_org_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE SECURITY DEFINER
        SET search_path TO 'public'
      AS $corpo$
        SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
      $corpo$;
    $f$;
    RAISE NOTICE 'public.current_org_id() criada (bootstrap de banco limpo)';
  ELSE
    RAISE NOTICE 'public.current_org_id() já existe — preservada como está';
  END IF;
END $$;


-- ============================================================================
-- Clientes — imobiliárias, corretores autônomos e incorporadoras.
-- Quem a produtora fatura.
-- ============================================================================

CREATE TABLE p_studio.clientes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    nome         TEXT NOT NULL,
    empresa      TEXT,
    corretor     TEXT,               -- contato do dia a dia dentro da imobiliária
    email        TEXT,
    telefone     TEXT,
    cidade       TEXT,
    estado       TEXT,
    observacoes  TEXT,
    ativo        BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- Imóveis — o portfólio captado. Um imóvel pertence a um cliente e pode ser
-- captado mais de uma vez (relançamento, troca de corretor, nova temporada).
-- ============================================================================

CREATE TABLE p_studio.imoveis (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    cliente_id     UUID REFERENCES p_studio.clientes(id) ON DELETE SET NULL,
    codigo         TEXT NOT NULL,     -- código interno, ex. PS-001
    endereco       TEXT NOT NULL,
    condominio     TEXT,
    cidade         TEXT,
    estado         TEXT,
    tipo           TEXT NOT NULL DEFAULT 'apartamento'
                   CHECK (tipo IN ('casa', 'apartamento', 'cobertura', 'terreno',
                                   'comercial', 'galpao')),
    padrao         TEXT NOT NULL DEFAULT 'medio'
                   CHECK (padrao IN ('alto', 'medio', 'economico')),
    area           NUMERIC(10,2),     -- área construída em m²
    dormitorios    INTEGER NOT NULL DEFAULT 0,
    banheiros      INTEGER NOT NULL DEFAULT 0,
    vagas          INTEGER NOT NULL DEFAULT 0,
    valor          NUMERIC(14,2),     -- valor do imóvel (8 dígitos são comuns)
    maps_url       TEXT,
    observacoes    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, codigo)
);


-- ============================================================================
-- Serviços — catálogo com preço e prazo. Um negócio contrata um ou mais.
-- ============================================================================

CREATE TABLE p_studio.servicos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    nome          TEXT NOT NULL,
    categoria     TEXT,
    preco         NUMERIC(12,2) NOT NULL DEFAULT 0,
    prazo_dias    INTEGER NOT NULL DEFAULT 3,
    descricao     TEXT,
    ativo         BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- Equipamentos — inventário. Alimenta o checklist da captação.
-- ============================================================================

CREATE TABLE p_studio.equipamentos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    nome            TEXT NOT NULL,
    marca           TEXT,
    modelo          TEXT,
    numero_serie    TEXT,
    categoria       TEXT               -- camera, lente, drone, microfone,
                                       -- gimbal, bateria, cartao, iluminacao
                    CHECK (categoria IS NULL OR categoria IN
                          ('camera', 'lente', 'drone', 'microfone', 'gimbal',
                           'bateria', 'cartao', 'iluminacao', 'outro')),
    valor           NUMERIC(12,2) NOT NULL DEFAULT 0,
    quantidade      INTEGER NOT NULL DEFAULT 1,
    observacoes     TEXT,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- Negócios — o pipeline comercial. A espinha dorsal do modelo.
--
-- Etapas (spec § 2):
--   novo_lead → orcamento → negociacao → aprovado → agendamento
--             → producao → entregue → recebido → arquivado
-- ============================================================================

CREATE TABLE p_studio.negocios (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL,
    cliente_id         UUID NOT NULL REFERENCES p_studio.clientes(id) ON DELETE RESTRICT,
    imovel_id          UUID REFERENCES p_studio.imoveis(id) ON DELETE SET NULL,
    titulo             TEXT,           -- rótulo curto; default = endereço do imóvel
    corretor           TEXT,           -- corretor responsável neste negócio
    etapa              TEXT NOT NULL DEFAULT 'novo_lead'
                       CHECK (etapa IN ('novo_lead', 'orcamento', 'negociacao',
                                        'aprovado', 'agendamento', 'producao',
                                        'entregue', 'recebido', 'arquivado')),
    valor              NUMERIC(12,2) NOT NULL DEFAULT 0,
    prazo_entrega      DATE,
    forma_pagamento    TEXT
                       CHECK (forma_pagamento IS NULL OR forma_pagamento IN
                             ('pix', 'boleto', 'cartao', 'transferencia')),
    observacoes        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Serviços contratados no negócio (seleção múltipla — spec § 6).
-- `preco` é copiado do catálogo no momento da contratação: o preço de tabela
-- muda, o preço já negociado não.
CREATE TABLE p_studio.negocio_servicos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    negocio_id   UUID NOT NULL REFERENCES p_studio.negocios(id) ON DELETE CASCADE,
    servico_id   UUID NOT NULL REFERENCES p_studio.servicos(id) ON DELETE RESTRICT,
    preco        NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (negocio_id, servico_id)
);


-- ============================================================================
-- Captações — a agenda operacional (spec § 3). A ida ao imóvel.
-- ============================================================================

CREATE TABLE p_studio.captacoes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    negocio_id           UUID REFERENCES p_studio.negocios(id) ON DELETE SET NULL,
    cliente_id           UUID REFERENCES p_studio.clientes(id) ON DELETE SET NULL,
    imovel_id            UUID REFERENCES p_studio.imoveis(id) ON DELETE SET NULL,
    data                 DATE NOT NULL,
    hora                 TIME NOT NULL DEFAULT '09:00',
    duracao_minutos      INTEGER NOT NULL DEFAULT 120,
    endereco             TEXT NOT NULL,
    maps_url             TEXT,
    responsavel          TEXT,
    status               TEXT NOT NULL DEFAULT 'agendado'
                         CHECK (status IN ('agendado', 'captado', 'cancelado')),
    observacoes          TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Checklist de equipamentos da captação (spec § 3).
-- `conferido` é o check em campo, antes de sair do estúdio.
CREATE TABLE p_studio.captacao_equipamentos (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    captacao_id       UUID NOT NULL REFERENCES p_studio.captacoes(id) ON DELETE CASCADE,
    equipamento_id    UUID NOT NULL REFERENCES p_studio.equipamentos(id) ON DELETE RESTRICT,
    conferido         BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (captacao_id, equipamento_id)
);


-- ============================================================================
-- Produções — o pipeline de pós (spec § 4).
--
-- Etapas: agendado → captado → backup → selecao → edicao → revisao
--                  → entregue → arquivado
-- ============================================================================

CREATE TABLE p_studio.producoes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    negocio_id      UUID REFERENCES p_studio.negocios(id) ON DELETE SET NULL,
    captacao_id     UUID REFERENCES p_studio.captacoes(id) ON DELETE SET NULL,
    cliente_id      UUID REFERENCES p_studio.clientes(id) ON DELETE SET NULL,
    etapa           TEXT NOT NULL DEFAULT 'agendado'
                    CHECK (etapa IN ('agendado', 'captado', 'backup', 'selecao',
                                     'edicao', 'revisao', 'entregue', 'arquivado')),
    responsavel     TEXT,
    prazo_entrega   DATE,
    entregue_em     DATE,          -- preenchido ao entrar em `entregue`;
                                   -- alimenta prazo médio e dispara faturamento
    observacoes     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Histórico append-only da produção (spec § 4: data/hora, responsável,
-- comentários, upload de arquivos, histórico de alterações).
-- Nunca sofre UPDATE nem DELETE — é o registro do que aconteceu.
CREATE TABLE p_studio.producao_eventos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    producao_id    UUID NOT NULL REFERENCES p_studio.producoes(id) ON DELETE CASCADE,
    etapa          TEXT NOT NULL,       -- etapa em que o evento ocorreu
    tipo           TEXT NOT NULL DEFAULT 'comentario'
                   CHECK (tipo IN ('transicao', 'comentario', 'arquivo')),
    responsavel    TEXT,
    comentario     TEXT,
    arquivo_url    TEXT,                -- reservado; upload não entra nesta fase
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- Lançamentos financeiros (spec § 7).
--
-- Tabela separada de `negocios` porque um negócio pode ser faturado em
-- parcelas e porque o dashboard financeiro agrega através de negócios.
--
-- `atrasado` é DERIVADO (faturado + vencimento passado), não armazenado —
-- a API calcula na leitura para que o status nunca fique obsoleto.
-- ============================================================================

CREATE TABLE p_studio.lancamentos (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    negocio_id        UUID REFERENCES p_studio.negocios(id) ON DELETE SET NULL,
    cliente_id        UUID NOT NULL REFERENCES p_studio.clientes(id) ON DELETE RESTRICT,
    descricao         TEXT,
    valor             NUMERIC(12,2) NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'a_faturar'
                      CHECK (status IN ('a_faturar', 'faturado', 'recebido', 'cancelado')),
    data_entrega      DATE,
    vencimento        DATE,
    pago_em           DATE,
    forma_pagamento   TEXT
                      CHECK (forma_pagamento IS NULL OR forma_pagamento IN
                            ('pix', 'boleto', 'cartao', 'transferencia')),
    observacoes       TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- Status das páginas (feature flags) — convenção da plataforma.
-- ============================================================================

CREATE TABLE p_studio.status_pagina (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina   TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL DEFAULT 'producao'
                  CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao     TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- Triggers updated_at
-- ============================================================================

CREATE TRIGGER set_updated_at_clientes      BEFORE UPDATE ON p_studio.clientes      FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_imoveis       BEFORE UPDATE ON p_studio.imoveis       FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_servicos      BEFORE UPDATE ON p_studio.servicos      FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_equipamentos  BEFORE UPDATE ON p_studio.equipamentos  FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_negocios      BEFORE UPDATE ON p_studio.negocios      FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_captacoes     BEFORE UPDATE ON p_studio.captacoes     FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_producoes     BEFORE UPDATE ON p_studio.producoes     FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();
CREATE TRIGGER set_updated_at_lancamentos   BEFORE UPDATE ON p_studio.lancamentos   FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();


-- ============================================================================
-- Índices
--
-- Todo índice começa por org_id: RLS filtra por org em toda query, então o
-- índice composto serve tanto o predicado da policy quanto o filtro do app.
-- ============================================================================

CREATE INDEX idx_ps_clientes_org           ON p_studio.clientes(org_id, ativo);
CREATE INDEX idx_ps_imoveis_org            ON p_studio.imoveis(org_id);
CREATE INDEX idx_ps_imoveis_cliente        ON p_studio.imoveis(org_id, cliente_id);
CREATE INDEX idx_ps_servicos_org           ON p_studio.servicos(org_id, ativo);
CREATE INDEX idx_ps_equipamentos_org       ON p_studio.equipamentos(org_id, ativo);
CREATE INDEX idx_ps_negocios_org_etapa     ON p_studio.negocios(org_id, etapa);
CREATE INDEX idx_ps_negocios_cliente       ON p_studio.negocios(org_id, cliente_id);
CREATE INDEX idx_ps_negocio_servicos_neg   ON p_studio.negocio_servicos(negocio_id);
CREATE INDEX idx_ps_captacoes_org_data     ON p_studio.captacoes(org_id, data);
CREATE INDEX idx_ps_captacoes_negocio      ON p_studio.captacoes(org_id, negocio_id);
CREATE INDEX idx_ps_captacao_equip_cap     ON p_studio.captacao_equipamentos(captacao_id);
CREATE INDEX idx_ps_producoes_org_etapa    ON p_studio.producoes(org_id, etapa);
CREATE INDEX idx_ps_producoes_negocio      ON p_studio.producoes(org_id, negocio_id);
CREATE INDEX idx_ps_producao_eventos_prod  ON p_studio.producao_eventos(producao_id, created_at DESC);
CREATE INDEX idx_ps_lancamentos_org_status ON p_studio.lancamentos(org_id, status);
CREATE INDEX idx_ps_lancamentos_venc       ON p_studio.lancamentos(org_id, vencimento);
CREATE INDEX idx_ps_lancamentos_cliente    ON p_studio.lancamentos(org_id, cliente_id);


-- ============================================================================
-- RLS — escopo por organização em todas as tabelas de domínio.
--
-- Um único padrão: quem pertence à organização lê e gerencia os dados dela.
-- Diferente do protótipo (created_by = auth.uid()), onde um fotógrafo não
-- conseguia editar a captação agendada por outro — errado para um estúdio
-- em que a equipe inteira trabalha os mesmos jobs.
--
-- producao_eventos é append-only: SELECT + INSERT, sem UPDATE nem DELETE.
-- ============================================================================

ALTER TABLE p_studio.clientes              ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.imoveis               ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.servicos              ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.equipamentos          ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.negocios              ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.negocio_servicos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.captacoes             ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.captacao_equipamentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.producoes             ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.producao_eventos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.lancamentos           ENABLE ROW LEVEL SECURITY;
ALTER TABLE p_studio.status_pagina         ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'clientes', 'imoveis', 'servicos', 'equipamentos', 'negocios',
    'negocio_servicos', 'captacoes', 'captacao_equipamentos',
    'producoes', 'lancamentos'
  ] LOOP
    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR SELECT TO authenticated
        USING (org_id = public.current_org_id());
    $p$, t || '_select_own_org', t);

    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR INSERT TO authenticated
        WITH CHECK (org_id = public.current_org_id());
    $p$, t || '_insert_own_org', t);

    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR UPDATE TO authenticated
        USING (org_id = public.current_org_id())
        WITH CHECK (org_id = public.current_org_id());
    $p$, t || '_update_own_org', t);

    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR DELETE TO authenticated
        USING (org_id = public.current_org_id());
    $p$, t || '_delete_own_org', t);
  END LOOP;
END $$;

-- Append-only: sem UPDATE, sem DELETE.
CREATE POLICY producao_eventos_select_own_org ON p_studio.producao_eventos
  FOR SELECT TO authenticated USING (org_id = public.current_org_id());
CREATE POLICY producao_eventos_insert_own_org ON p_studio.producao_eventos
  FOR INSERT TO authenticated WITH CHECK (org_id = public.current_org_id());

-- Feature flags: leitura liberada (não carrega dado de organização).
CREATE POLICY status_pagina_select_producao ON p_studio.status_pagina
  FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Páginas
-- ============================================================================

INSERT INTO p_studio.status_pagina (nome_pagina, status) VALUES
    ('dashboard',    'producao'),
    ('crm',          'producao'),
    ('agenda',       'producao'),
    ('producao',     'producao'),
    ('imoveis',      'producao'),
    ('servicos',     'producao'),
    ('financeiro',   'producao'),
    ('equipamentos', 'producao'),
    ('clientes',     'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
