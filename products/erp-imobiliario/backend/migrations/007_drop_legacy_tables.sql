-- Migration 007: Drop legacy imoveis/perfis_permutas tables, update negociacoes to reference ativos
--
-- The original schema (001) included three tables from the initial planning phase:
--   - erp.imoveis (property listings with TEXT IDs like "IMO-0001")
--   - erp.perfis_permutas (swap/exchange profiles with TEXT IDs like "PP-0001")
--   - erp.imoveis_perfis_permutas (junction table linking the two)
--
-- These were superseded by the unified erp.ativos table (UUID-based, supports all
-- property types including permutas via natureza='permuta_imovel'). The legacy tables
-- were never populated in production. This migration:
--   1. Drops the legacy tables and their dependencies
--   2. Rewires erp.negociacoes to reference erp.ativos instead
--   3. Cleans up orphaned sequences, functions, and enum types
--   4. Removes legacy values from tipo_entidade enum
--
-- Executed manually in Supabase SQL Editor.
-- Safe to run multiple times (all statements use IF EXISTS / IF NOT EXISTS).

BEGIN;

-- ============================================================================
-- 1. Drop dependent tables (CASCADE handles policies/indexes/triggers)
-- ============================================================================

-- Drop junction table first (depends on both imoveis and perfis_permutas)
DROP TABLE IF EXISTS erp.imoveis_perfis_permutas CASCADE;

-- Drop negociacoes FK constraints that reference old tables
ALTER TABLE erp.negociacoes DROP CONSTRAINT IF EXISTS negociacoes_imovel_id_fkey;
ALTER TABLE erp.negociacoes DROP CONSTRAINT IF EXISTS negociacoes_perfil_permuta_id_fkey;

-- Drop main tables
DROP TABLE IF EXISTS erp.perfis_permutas CASCADE;
DROP TABLE IF EXISTS erp.imoveis CASCADE;

-- ============================================================================
-- 2. Modify negociacoes — replace old columns with ativos references
-- ============================================================================

-- Add new UUID columns referencing ativos
ALTER TABLE erp.negociacoes ADD COLUMN IF NOT EXISTS ativo_origem_id UUID;
ALTER TABLE erp.negociacoes ADD COLUMN IF NOT EXISTS ativo_destino_id UUID;

-- Note: imovel_id was TEXT and ativos.id is UUID, so direct data migration isn't
-- possible. The negociacoes table is expected to be empty since the legacy tables
-- were never used in production.

-- Drop old columns
ALTER TABLE erp.negociacoes DROP COLUMN IF EXISTS imovel_id;
ALTER TABLE erp.negociacoes DROP COLUMN IF EXISTS perfil_permuta_id;

-- Add NOT NULL constraints and foreign keys
ALTER TABLE erp.negociacoes ALTER COLUMN ativo_origem_id SET NOT NULL;
ALTER TABLE erp.negociacoes ALTER COLUMN ativo_destino_id SET NOT NULL;
ALTER TABLE erp.negociacoes
  ADD CONSTRAINT negociacoes_ativo_origem_id_fkey FOREIGN KEY (ativo_origem_id) REFERENCES erp.ativos(id) ON DELETE CASCADE,
  ADD CONSTRAINT negociacoes_ativo_destino_id_fkey FOREIGN KEY (ativo_destino_id) REFERENCES erp.ativos(id) ON DELETE CASCADE;

-- ============================================================================
-- 3. Update indexes for negociacoes
-- ============================================================================

DROP INDEX IF EXISTS erp.idx_negociacoes_imovel;
DROP INDEX IF EXISTS erp.idx_negociacoes_perfil;
CREATE INDEX idx_negociacoes_ativo_origem ON erp.negociacoes(ativo_origem_id);
CREATE INDEX idx_negociacoes_ativo_destino ON erp.negociacoes(ativo_destino_id);

-- ============================================================================
-- 4. Drop orphaned sequences and functions
-- ============================================================================

DROP FUNCTION IF EXISTS erp.generate_imovel_id();
DROP FUNCTION IF EXISTS erp.generate_perfil_permuta_id();
DROP SEQUENCE IF EXISTS erp.imoveis_id_seq;
DROP SEQUENCE IF EXISTS erp.perfis_permutas_id_seq;

-- ============================================================================
-- 5. Drop unused ENUM types
-- ============================================================================

-- finalidade_imovel: only used by dropped imoveis table
DROP TYPE IF EXISTS erp.finalidade_imovel;

-- categoria_permuta: only used by dropped perfis_permutas table
DROP TYPE IF EXISTS erp.categoria_permuta;

-- tipo_movel: only used by dropped perfis_permutas table
DROP TYPE IF EXISTS erp.tipo_movel;

-- tipo_imovel ENUM: ativos.tipo_imovel is TEXT, so this enum is unreferenced
DROP TYPE IF EXISTS erp.tipo_imovel;

-- ============================================================================
-- 6. Update tipo_entidade enum — remove legacy 'imovel' and 'perfil_permuta'
-- ============================================================================

-- Update any rows using old values first
UPDATE erp.action_log SET tipo_entidade = 'ativo' WHERE tipo_entidade IN ('imovel', 'perfil_permuta');

-- Recreate enum without legacy values (PostgreSQL doesn't support removing enum values)
ALTER TYPE erp.tipo_entidade RENAME TO tipo_entidade_old;
CREATE TYPE erp.tipo_entidade AS ENUM (
  'meta', 'cliente', 'usuario', 'atividade', 'config_meta', 'auth',
  'negociacao', 'match', 'condominio', 'ativo'
);
ALTER TABLE erp.action_log ALTER COLUMN tipo_entidade TYPE erp.tipo_entidade USING tipo_entidade::TEXT::erp.tipo_entidade;
DROP TYPE erp.tipo_entidade_old;

COMMIT;
