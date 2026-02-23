-- =============================================
-- Migration: Create unified `ativos` table
-- Merges imoveis + perfis_permutas into one table
-- Discriminator column: natureza (imovel | permuta_imovel | permuta_automovel)
-- =============================================

-- 1. Create the unified table
CREATE TABLE IF NOT EXISTS ativos (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    natureza text NOT NULL CHECK (natureza IN ('imovel', 'permuta_imovel', 'permuta_automovel')),

    -- === Shared fields (all naturezas) ===
    valor numeric NOT NULL DEFAULT 0,
    status text DEFAULT 'ativo',
    observacoes text,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,

    -- === Property fields (imovel + permuta_imovel) ===
    tipo_imovel text,                       -- casa, apartamento, terreno, comercial, rural
    cep text,
    logradouro text,
    numero text,
    complemento text,
    bairro text,
    cidade text,
    estado text,
    zona text,                              -- norte, sul, leste, oeste
    condominio_id uuid REFERENCES condominios(id) ON DELETE SET NULL,
    condominio_nome text,
    area_privativa numeric,
    area_total numeric,
    quartos integer,
    suites integer,
    banheiros integer,
    vagas integer,
    andar integer,
    ano_construcao integer,

    -- === Imóvel-only fields (natureza = 'imovel') ===
    ref text,                               -- referência do imóvel
    corretor text,
    proprietario_id text REFERENCES clientes(id) ON DELETE SET NULL,
    aceita_permutas boolean DEFAULT false,
    finalidade text DEFAULT 'venda',
    iptu numeric,
    pronto_para_portais boolean DEFAULT false,
    titulo_anuncio text,
    descricao_seo text,
    fotos text[],
    plantas text[],
    palavras_chave text[],
    pontos_de_interesse text[],
    tour_virtual_url text,
    latitude numeric,
    longitude numeric,
    lqs_score_hint text,
    observacoes_negociacao text,

    -- === Interesses (natureza = 'imovel') — what the owner wants in exchange ===
    interesses jsonb DEFAULT '[]'::jsonb,

    -- === Vehicle fields (natureza = 'permuta_automovel') ===
    tipo_veiculo text,                      -- carro, moto, SUV
    marca text,
    modelo text,
    motor text,                             -- gasolina, alcool, flex, eletrico, hibrido
    ano integer,
    quilometragem integer,

    -- === Permuta flexibility fields ===
    faixa_preco_min numeric,
    faixa_preco_max numeric,
    regiao_preferida text[],
    aceita_completar_diferenca boolean DEFAULT false,
    limite_complemento numeric,
    metragem_min numeric,
    metragem_max numeric,
    quartos_min integer,
    vagas_min integer,
    ano_min integer,
    ano_max integer,
    quilometragem_max integer
);

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_ativos_owner_id ON ativos(owner_id);
CREATE INDEX IF NOT EXISTS idx_ativos_natureza ON ativos(natureza);
CREATE INDEX IF NOT EXISTS idx_ativos_tipo_imovel ON ativos(tipo_imovel);
CREATE INDEX IF NOT EXISTS idx_ativos_cidade ON ativos(cidade);
CREATE INDEX IF NOT EXISTS idx_ativos_estado ON ativos(estado);
CREATE INDEX IF NOT EXISTS idx_ativos_valor ON ativos(valor);
CREATE INDEX IF NOT EXISTS idx_ativos_status ON ativos(status);
CREATE INDEX IF NOT EXISTS idx_ativos_proprietario ON ativos(proprietario_id);

-- 3. RLS
ALTER TABLE ativos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view all active ativos"
    ON ativos FOR SELECT TO authenticated USING (true);

CREATE POLICY "Users can insert their own ativos"
    ON ativos FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update their own ativos"
    ON ativos FOR UPDATE TO authenticated
    USING (auth.uid() = owner_id);

CREATE POLICY "Users can delete their own ativos"
    ON ativos FOR DELETE TO authenticated
    USING (auth.uid() = owner_id);

-- 4. Migrate existing imoveis → ativos
INSERT INTO ativos (
    id, owner_id, natureza, valor, status, observacoes, created_at, updated_at,
    tipo_imovel, cep, logradouro, numero, complemento, bairro, cidade, estado,
    condominio_nome, area_privativa, area_total, quartos, suites, banheiros, vagas,
    andar, ano_construcao, aceita_permutas, finalidade, iptu, pronto_para_portais,
    titulo_anuncio, descricao_seo, fotos, plantas, palavras_chave,
    pontos_de_interesse, tour_virtual_url, latitude, longitude,
    lqs_score_hint, observacoes_negociacao
)
SELECT
    id, owner_id, 'imovel', preco_pedido, status, NULL, created_at, updated_at,
    tipo::text, cep, logradouro, numero, complemento, bairro, cidade, estado,
    condominio_nome, area_privativa, area_total, quartos, suites, banheiros, vagas,
    andar, ano_construcao, aceita_permutas, finalidade::text, iptu, pronto_para_portais,
    titulo_anuncio, descricao_seo, fotos, plantas, palavras_chave,
    pontos_de_interesse, tour_virtual_url, latitude, longitude,
    lqs_score_hint, observacoes_negociacao
FROM imoveis
ON CONFLICT (id) DO NOTHING;

-- 5. Migrate existing perfis_permutas → ativos
INSERT INTO ativos (
    id, owner_id, natureza, valor, status, observacoes, created_at, updated_at,
    tipo_imovel, marca, modelo,
    faixa_preco_min, faixa_preco_max, regiao_preferida,
    aceita_completar_diferenca, limite_complemento,
    metragem_min, metragem_max, quartos_min, vagas_min,
    ano_min, ano_max, quilometragem_max
)
SELECT
    id,
    cliente_ofertante_id,
    CASE
        WHEN categoria::text = 'imovel' THEN 'permuta_imovel'
        ELSE 'permuta_automovel'
    END,
    COALESCE(valor_estimado, 0),
    status,
    observacoes,
    created_at,
    updated_at,
    tipo_imovel::text,
    marca,
    modelo,
    faixa_preco_min,
    faixa_preco_max,
    regiao_preferida,
    aceita_completar_diferenca,
    limite_complemento,
    metragem_min,
    metragem_max,
    quartos_min,
    vagas_min,
    ano_min,
    ano_max,
    quilometragem_max
FROM perfis_permutas
ON CONFLICT (id) DO NOTHING;

-- 6. Update matches table to reference ativos instead of imoveis/perfis_permutas
-- First drop existing FK constraints on matches if they exist
DO $$ BEGIN
    ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_imovel_id_fkey;
    ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_perfil_permuta_id_fkey;
EXCEPTION WHEN undefined_table THEN
    NULL;
END $$;

-- Rename columns to be generic
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'matches' AND column_name = 'imovel_id') THEN
        ALTER TABLE matches RENAME COLUMN imovel_id TO ativo_origem_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'matches' AND column_name = 'perfil_permuta_id') THEN
        ALTER TABLE matches RENAME COLUMN perfil_permuta_id TO ativo_destino_id;
    END IF;
EXCEPTION WHEN undefined_table THEN
    NULL;
END $$;

-- Add FK constraints to ativos
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'matches') THEN
        ALTER TABLE matches ADD CONSTRAINT matches_ativo_origem_id_fkey
            FOREIGN KEY (ativo_origem_id) REFERENCES ativos(id) ON DELETE CASCADE;
        ALTER TABLE matches ADD CONSTRAINT matches_ativo_destino_id_fkey
            FOREIGN KEY (ativo_destino_id) REFERENCES ativos(id) ON DELETE CASCADE;
    END IF;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

-- 7. Add 'ativo' to tipo_entidade enum for action logging
DO $$ BEGIN
    ALTER TYPE tipo_entidade ADD VALUE IF NOT EXISTS 'ativo';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 8. Register ativos page in status_pagina (if not already there for imoveis)
-- The page names stay the same (imoveis, permutas) but now query ativos

-- 9. Add unique constraint on matches for upsert (after column rename)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'matches') THEN
        -- Drop old unique constraint if it exists
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_imovel_id_perfil_permuta_id_key;
        -- Add new unique constraint on renamed columns
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'matches_ativo_origem_ativo_destino_key') THEN
            ALTER TABLE matches ADD CONSTRAINT matches_ativo_origem_ativo_destino_key
                UNIQUE (ativo_origem_id, ativo_destino_id);
        END IF;
    END IF;
END $$;

-- Done! Old tables (imoveis, perfis_permutas) are preserved as backup.
-- You can drop them later with: DROP TABLE imoveis CASCADE; DROP TABLE perfis_permutas CASCADE;
