-- ============================================
-- SISTEMA DE MATCH DE PERMUTAS IMOBILIÁRIAS
-- ============================================

-- Tipos enumerados
CREATE TYPE finalidade_imovel AS ENUM ('venda', 'aluguel');
CREATE TYPE tipo_imovel AS ENUM ('casa', 'apartamento', 'terreno', 'comercial', 'rural', 'outro');
CREATE TYPE categoria_permuta AS ENUM ('imovel', 'movel');
CREATE TYPE tipo_movel AS ENUM ('carro', 'moto');
CREATE TYPE status_negociacao AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado', 'cancelado');

-- ============================================
-- SEQUENCES PARA IDs CUSTOMIZADOS
-- ============================================

-- Sequence para imóveis (IM0001, IM0002...)
CREATE SEQUENCE IF NOT EXISTS public.imoveis_id_seq START WITH 1;

-- Sequence para perfis de permuta (PP0001, PP0002...)
CREATE SEQUENCE IF NOT EXISTS public.perfis_permutas_id_seq START WITH 1;

-- Sequence para negociações (NG0001, NG0002...)
CREATE SEQUENCE IF NOT EXISTS public.negociacoes_id_seq START WITH 1;

-- ============================================
-- FUNÇÕES DE GERAÇÃO DE IDs
-- ============================================

-- Função para gerar ID de imóvel
CREATE OR REPLACE FUNCTION public.generate_imovel_id()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    next_number INTEGER;
    next_id TEXT;
BEGIN
    next_number := nextval('public.imoveis_id_seq')::INTEGER;
    IF next_number <= 9999 THEN
        next_id := 'IM' || LPAD(next_number::TEXT, 4, '0');
    ELSE
        next_id := 'IM' || next_number::TEXT;
    END IF;
    RETURN next_id;
END;
$function$;

-- Função para gerar ID de perfil de permuta
CREATE OR REPLACE FUNCTION public.generate_perfil_permuta_id()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    next_number INTEGER;
    next_id TEXT;
BEGIN
    next_number := nextval('public.perfis_permutas_id_seq')::INTEGER;
    IF next_number <= 9999 THEN
        next_id := 'PP' || LPAD(next_number::TEXT, 4, '0');
    ELSE
        next_id := 'PP' || next_number::TEXT;
    END IF;
    RETURN next_id;
END;
$function$;

-- Função para gerar ID de negociação
CREATE OR REPLACE FUNCTION public.generate_negociacao_id()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    next_number INTEGER;
    next_id TEXT;
BEGIN
    next_number := nextval('public.negociacoes_id_seq')::INTEGER;
    IF next_number <= 9999 THEN
        next_id := 'NG' || LPAD(next_number::TEXT, 4, '0');
    ELSE
        next_id := 'NG' || next_number::TEXT;
    END IF;
    RETURN next_id;
END;
$function$;

-- ============================================
-- TABELA: imoveis
-- ============================================

CREATE TABLE public.imoveis (
    id TEXT PRIMARY KEY DEFAULT generate_imovel_id(),
    
    -- Identificação e controle
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'ativo',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    
    -- Comercial
    finalidade finalidade_imovel NOT NULL DEFAULT 'venda',
    preco_pedido NUMERIC(12,2) NOT NULL,
    aceita_permutas BOOLEAN NOT NULL DEFAULT false,
    observacoes_negociacao TEXT,
    
    -- Localização (CEP obrigatório)
    cep TEXT NOT NULL,
    logradouro TEXT,
    numero TEXT,
    complemento TEXT,
    bairro TEXT,
    cidade TEXT,
    estado TEXT,
    latitude NUMERIC(10,8),
    longitude NUMERIC(11,8),
    
    -- Especificações
    tipo tipo_imovel NOT NULL,
    area_privativa NUMERIC(8,2),
    area_total NUMERIC(8,2),
    quartos INTEGER,
    suites INTEGER,
    banheiros INTEGER,
    vagas INTEGER,
    andar INTEGER,
    condominio NUMERIC(10,2),
    iptu NUMERIC(10,2),
    condominio_nome TEXT,
    ano_construcao INTEGER,
    
    -- Mídia e qualidade do anúncio
    fotos TEXT[] DEFAULT ARRAY[]::TEXT[],
    tour_virtual_url TEXT,
    plantas TEXT[] DEFAULT ARRAY[]::TEXT[],
    titulo_anuncio TEXT,
    descricao_seo TEXT,
    palavras_chave TEXT[] DEFAULT ARRAY[]::TEXT[],
    pontos_de_interesse TEXT[] DEFAULT ARRAY[]::TEXT[],
    
    -- Qualidade
    pronto_para_portais BOOLEAN NOT NULL DEFAULT false,
    lqs_score_hint TEXT,
    
    CONSTRAINT check_palavras_chave_max CHECK (array_length(palavras_chave, 1) IS NULL OR array_length(palavras_chave, 1) <= 4)
);

-- ============================================
-- TABELA: perfis_permutas
-- ============================================

CREATE TABLE public.perfis_permutas (
    id TEXT PRIMARY KEY DEFAULT generate_perfil_permuta_id(),
    
    -- Identificação e controle
    cliente_ofertante_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'ativo',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    
    -- Tipo do bem
    categoria categoria_permuta NOT NULL,
    
    -- Se imóvel
    tipo_imovel tipo_imovel,
    faixa_preco_min NUMERIC(12,2),
    faixa_preco_max NUMERIC(12,2),
    regiao_preferida TEXT[] DEFAULT ARRAY[]::TEXT[],
    metragem_min NUMERIC(8,2),
    metragem_max NUMERIC(8,2),
    quartos_min INTEGER,
    vagas_min INTEGER,
    
    -- Se móvel
    tipo_movel tipo_movel,
    marca TEXT,
    modelo TEXT,
    ano_min INTEGER,
    ano_max INTEGER,
    quilometragem_max INTEGER,
    
    -- Flexibilidade
    aceita_completar_diferenca BOOLEAN NOT NULL DEFAULT false,
    limite_complemento NUMERIC(12,2),
    observacoes TEXT,
    
    -- Valor estimado da permuta
    valor_estimado NUMERIC(12,2)
);

-- ============================================
-- TABELA: imoveis_perfis_permutas (relacionamento N:N)
-- ============================================

CREATE TABLE public.imoveis_perfis_permutas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    imovel_id TEXT NOT NULL REFERENCES public.imoveis(id) ON DELETE CASCADE,
    perfil_permuta_id TEXT NOT NULL REFERENCES public.perfis_permutas(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    
    UNIQUE(imovel_id, perfil_permuta_id)
);

-- ============================================
-- TABELA: negociacoes
-- ============================================

CREATE TABLE public.negociacoes (
    id TEXT PRIMARY KEY DEFAULT generate_negociacao_id(),
    
    -- Identificação e controle
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    
    -- Vínculos
    imovel_id TEXT NOT NULL REFERENCES public.imoveis(id) ON DELETE CASCADE,
    perfil_permuta_id TEXT NOT NULL REFERENCES public.perfis_permutas(id) ON DELETE CASCADE,
    cliente_proprietario_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cliente_ofertante_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Proposta
    valor_imovel NUMERIC(12,2) NOT NULL,
    valor_permuta NUMERIC(12,2) NOT NULL,
    valor_complemento NUMERIC(12,2) DEFAULT 0,
    status_etapa status_negociacao NOT NULL DEFAULT 'qualificacao',
    
    -- Histórico e observações
    timeline JSONB DEFAULT '[]'::JSONB,
    observacoes TEXT
);

-- ============================================
-- ÍNDICES PARA PERFORMANCE
-- ============================================

-- Imóveis
CREATE INDEX idx_imoveis_owner ON public.imoveis(owner_id);
CREATE INDEX idx_imoveis_finalidade ON public.imoveis(finalidade);
CREATE INDEX idx_imoveis_tipo ON public.imoveis(tipo);
CREATE INDEX idx_imoveis_preco ON public.imoveis(preco_pedido);
CREATE INDEX idx_imoveis_aceita_permutas ON public.imoveis(aceita_permutas);
CREATE INDEX idx_imoveis_cep ON public.imoveis(cep);
CREATE INDEX idx_imoveis_cidade ON public.imoveis(cidade);
CREATE INDEX idx_imoveis_estado ON public.imoveis(estado);
CREATE INDEX idx_imoveis_status ON public.imoveis(status);

-- Perfis de Permuta
CREATE INDEX idx_perfis_cliente ON public.perfis_permutas(cliente_ofertante_id);
CREATE INDEX idx_perfis_categoria ON public.perfis_permutas(categoria);
CREATE INDEX idx_perfis_tipo_imovel ON public.perfis_permutas(tipo_imovel);
CREATE INDEX idx_perfis_tipo_movel ON public.perfis_permutas(tipo_movel);
CREATE INDEX idx_perfis_status ON public.perfis_permutas(status);

-- Relacionamento
CREATE INDEX idx_imoveis_perfis_imovel ON public.imoveis_perfis_permutas(imovel_id);
CREATE INDEX idx_imoveis_perfis_perfil ON public.imoveis_perfis_permutas(perfil_permuta_id);

-- Negociações
CREATE INDEX idx_negociacoes_imovel ON public.negociacoes(imovel_id);
CREATE INDEX idx_negociacoes_perfil ON public.negociacoes(perfil_permuta_id);
CREATE INDEX idx_negociacoes_proprietario ON public.negociacoes(cliente_proprietario_id);
CREATE INDEX idx_negociacoes_ofertante ON public.negociacoes(cliente_ofertante_id);
CREATE INDEX idx_negociacoes_status ON public.negociacoes(status_etapa);

-- ============================================
-- TRIGGERS PARA updated_at
-- ============================================

CREATE TRIGGER update_imoveis_updated_at
    BEFORE UPDATE ON public.imoveis
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_perfis_permutas_updated_at
    BEFORE UPDATE ON public.perfis_permutas
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_negociacoes_updated_at
    BEFORE UPDATE ON public.negociacoes
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- ============================================
-- RLS (Row Level Security)
-- ============================================

-- Habilitar RLS
ALTER TABLE public.imoveis ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.perfis_permutas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.imoveis_perfis_permutas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.negociacoes ENABLE ROW LEVEL SECURITY;

-- Políticas para imóveis
CREATE POLICY "Admins podem ver todos os imóveis"
    ON public.imoveis FOR SELECT
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem ver seus próprios imóveis"
    ON public.imoveis FOR SELECT
    USING (auth.uid() = owner_id);

CREATE POLICY "Usuários podem criar seus próprios imóveis"
    ON public.imoveis FOR INSERT
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Usuários podem atualizar seus próprios imóveis"
    ON public.imoveis FOR UPDATE
    USING (auth.uid() = owner_id);

CREATE POLICY "Admins podem atualizar todos os imóveis"
    ON public.imoveis FOR UPDATE
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem deletar seus próprios imóveis"
    ON public.imoveis FOR DELETE
    USING (auth.uid() = owner_id);

CREATE POLICY "Admins podem deletar todos os imóveis"
    ON public.imoveis FOR DELETE
    USING (has_role(auth.uid(), 'admin'));

-- Políticas para perfis de permuta
CREATE POLICY "Admins podem ver todos os perfis de permuta"
    ON public.perfis_permutas FOR SELECT
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem ver seus próprios perfis"
    ON public.perfis_permutas FOR SELECT
    USING (auth.uid() = cliente_ofertante_id);

CREATE POLICY "Usuários podem criar seus próprios perfis"
    ON public.perfis_permutas FOR INSERT
    WITH CHECK (auth.uid() = cliente_ofertante_id);

CREATE POLICY "Usuários podem atualizar seus próprios perfis"
    ON public.perfis_permutas FOR UPDATE
    USING (auth.uid() = cliente_ofertante_id);

CREATE POLICY "Admins podem atualizar todos os perfis"
    ON public.perfis_permutas FOR UPDATE
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem deletar seus próprios perfis"
    ON public.perfis_permutas FOR DELETE
    USING (auth.uid() = cliente_ofertante_id);

CREATE POLICY "Admins podem deletar todos os perfis"
    ON public.perfis_permutas FOR DELETE
    USING (has_role(auth.uid(), 'admin'));

-- Políticas para relacionamento imóveis_perfis_permutas
CREATE POLICY "Admins podem ver todos os relacionamentos"
    ON public.imoveis_perfis_permutas FOR SELECT
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem ver relacionamentos de seus imóveis"
    ON public.imoveis_perfis_permutas FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.imoveis
            WHERE imoveis.id = imoveis_perfis_permutas.imovel_id
            AND imoveis.owner_id = auth.uid()
        )
    );

CREATE POLICY "Usuários podem criar relacionamentos de seus imóveis"
    ON public.imoveis_perfis_permutas FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.imoveis
            WHERE imoveis.id = imoveis_perfis_permutas.imovel_id
            AND imoveis.owner_id = auth.uid()
        )
    );

CREATE POLICY "Usuários podem deletar relacionamentos de seus imóveis"
    ON public.imoveis_perfis_permutas FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM public.imoveis
            WHERE imoveis.id = imoveis_perfis_permutas.imovel_id
            AND imoveis.owner_id = auth.uid()
        )
    );

CREATE POLICY "Admins podem gerenciar todos os relacionamentos"
    ON public.imoveis_perfis_permutas FOR ALL
    USING (has_role(auth.uid(), 'admin'));

-- Políticas para negociações
CREATE POLICY "Admins podem ver todas as negociações"
    ON public.negociacoes FOR SELECT
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Proprietários podem ver suas negociações"
    ON public.negociacoes FOR SELECT
    USING (auth.uid() = cliente_proprietario_id);

CREATE POLICY "Ofertantes podem ver suas negociações"
    ON public.negociacoes FOR SELECT
    USING (auth.uid() = cliente_ofertante_id);

CREATE POLICY "Usuários podem criar negociações"
    ON public.negociacoes FOR INSERT
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Proprietários podem atualizar suas negociações"
    ON public.negociacoes FOR UPDATE
    USING (auth.uid() = cliente_proprietario_id OR auth.uid() = cliente_ofertante_id);

CREATE POLICY "Admins podem atualizar todas as negociações"
    ON public.negociacoes FOR UPDATE
    USING (has_role(auth.uid(), 'admin'));

CREATE POLICY "Usuários podem deletar negociações que criaram"
    ON public.negociacoes FOR DELETE
    USING (auth.uid() = owner_id);

CREATE POLICY "Admins podem deletar todas as negociações"
    ON public.negociacoes FOR DELETE
    USING (has_role(auth.uid(), 'admin'));