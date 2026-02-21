-- =============================================
-- Migration: Create condominios table
-- =============================================

CREATE TABLE IF NOT EXISTS condominios (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    nome text NOT NULL,
    endereco text,
    bairro text,
    cidade text,
    estado text,
    cep text,
    valor_condominio numeric DEFAULT 0,
    sindico text,
    telefone_sindico text,
    administradora text,
    torres integer,
    unidades_por_andar integer,
    total_unidades integer,
    possui_portaria boolean DEFAULT false,
    possui_piscina boolean DEFAULT false,
    possui_academia boolean DEFAULT false,
    possui_salao_festas boolean DEFAULT false,
    possui_playground boolean DEFAULT false,
    possui_churrasqueira boolean DEFAULT false,
    observacoes text,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_condominios_owner_id ON condominios(owner_id);
CREATE INDEX IF NOT EXISTS idx_condominios_cidade ON condominios(cidade);

-- RLS
ALTER TABLE condominios ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view all condominios"
    ON condominios FOR SELECT TO authenticated USING (true);

CREATE POLICY "Users can insert their own condominios"
    ON condominios FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update their own condominios"
    ON condominios FOR UPDATE TO authenticated
    USING (auth.uid() = owner_id);

CREATE POLICY "Users can delete their own condominios"
    ON condominios FOR DELETE TO authenticated
    USING (auth.uid() = owner_id);

-- Add condominios page to status_pagina so it shows in navigation
INSERT INTO status_pagina (nome_pagina, status, descricao)
VALUES ('condominios', 'producao', 'Gestão de Condomínios')
ON CONFLICT (nome_pagina) DO NOTHING;

-- Add condominio_id FK to imoveis (links imóvel to a condominio entity)
ALTER TABLE imoveis ADD COLUMN IF NOT EXISTS condominio_id uuid REFERENCES condominios(id) ON DELETE SET NULL;

-- Add 'condominio' to tipo_entidade enum for action logging
DO $$ BEGIN
    ALTER TYPE tipo_entidade ADD VALUE IF NOT EXISTS 'condominio';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
