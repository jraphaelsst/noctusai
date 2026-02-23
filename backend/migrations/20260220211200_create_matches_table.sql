-- =============================================
-- Migration: Create matches table for server-side matching
-- =============================================

-- Enum for match status
DO $$ BEGIN
    CREATE TYPE status_match AS ENUM ('pendente', 'aceito', 'rejeitado', 'expirado');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Matches table: stores computed matches between imóveis and perfis de permuta
CREATE TABLE IF NOT EXISTS matches (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    imovel_id text NOT NULL REFERENCES imoveis(id) ON DELETE CASCADE,
    perfil_permuta_id text NOT NULL REFERENCES perfis_permutas(id) ON DELETE CASCADE,
    score integer NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
    status status_match NOT NULL DEFAULT 'pendente',
    justificativa text,
    detalhes jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,

    -- Prevent duplicate matches for the same pair
    UNIQUE(imovel_id, perfil_permuta_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_matches_imovel_id ON matches(imovel_id);
CREATE INDEX IF NOT EXISTS idx_matches_perfil_permuta_id ON matches(perfil_permuta_id);
CREATE INDEX IF NOT EXISTS idx_matches_score_desc ON matches(score DESC);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);

-- RLS
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;

-- Authenticated users can read all matches
CREATE POLICY "Authenticated users can view matches"
    ON matches FOR SELECT
    TO authenticated
    USING (true);

-- Authenticated users can update match status (aceitar/rejeitar)
CREATE POLICY "Authenticated users can update match status"
    ON matches FOR UPDATE
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- Allow inserts from authenticated users (Edge Function runs with user's auth context)
CREATE POLICY "Authenticated users can insert matches"
    ON matches FOR INSERT
    TO authenticated
    WITH CHECK (true);

-- Allow deletes from authenticated users (for recalculation)
CREATE POLICY "Authenticated users can delete matches"
    ON matches FOR DELETE
    TO authenticated
    USING (true);

-- Add 'match' to tipo_entidade enum for action logging
DO $$ BEGIN
    ALTER TYPE tipo_entidade ADD VALUE IF NOT EXISTS 'match';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
