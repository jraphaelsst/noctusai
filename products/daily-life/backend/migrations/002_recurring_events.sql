-- Daily Life: Add recurrence support to eventos table
-- Run in Supabase SQL Editor

ALTER TABLE daily_life.eventos ADD COLUMN IF NOT EXISTS recorrencia TEXT DEFAULT 'nenhuma'
  CHECK (recorrencia IN ('nenhuma', 'diario', 'semanal', 'mensal', 'anual'));
ALTER TABLE daily_life.eventos ADD COLUMN IF NOT EXISTS recorrencia_fim DATE;
ALTER TABLE daily_life.eventos ADD COLUMN IF NOT EXISTS evento_pai_id UUID REFERENCES daily_life.eventos(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_eventos_evento_pai ON daily_life.eventos(evento_pai_id);
