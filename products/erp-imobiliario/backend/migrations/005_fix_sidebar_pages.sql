-- ═══════════════════════════════════════════════════════════════════════
-- Migration 005: Fix Sidebar — Seed all page routes + admin role
-- ═══════════════════════════════════════════════════════════════════════
-- Fully idempotent — safe to run multiple times.
-- Run this in Supabase SQL Editor on your deployed database.
-- ═══════════════════════════════════════════════════════════════════════

-- 0. Fix set_timestamps_sp() — the version from migration 004 blindly
--    sets NEW.updated_at which crashes on tables without that column
--    (e.g. user_roles, password_request_codes). This version checks first.
CREATE OR REPLACE FUNCTION erp.set_timestamps_sp()
RETURNS TRIGGER AS $$
DECLARE
  has_updated_at boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = TG_TABLE_SCHEMA
      AND table_name = TG_TABLE_NAME
      AND column_name = 'updated_at'
  ) INTO has_updated_at;

  IF TG_OP = 'INSERT' THEN
    NEW.created_at := COALESCE(NEW.created_at, now() AT TIME ZONE 'America/Sao_Paulo');
    IF has_updated_at THEN
      NEW.updated_at := NEW.created_at;
    END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    IF has_updated_at THEN
      NEW.updated_at := now() AT TIME ZONE 'America/Sao_Paulo';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 1. Insert all sidebar routes into status_pagina
--    ON CONFLICT updates existing rows so re-runs are safe.
INSERT INTO erp.status_pagina (nome_pagina, status, tipo_pagina) VALUES
  -- Principal
  ('dashboard', 'producao', 'geral'),
  ('funil', 'producao', 'geral'),
  ('clientes', 'producao', 'geral'),
  ('metas', 'producao', 'geral'),
  -- Comercial
  ('imoveis', 'producao', 'geral'),
  ('condominios', 'producao', 'geral'),
  ('permutas', 'producao', 'geral'),
  ('negociacoes', 'producao', 'geral'),
  ('propostas', 'producao', 'geral'),
  ('contratos', 'producao', 'geral'),
  ('locacoes', 'producao', 'geral'),
  ('comissoes', 'producao', 'geral'),
  -- Financeiro
  ('financeiro', 'producao', 'geral'),
  ('impostos', 'producao', 'geral'),
  ('banco', 'producao', 'geral'),
  ('analise-credito', 'producao', 'geral'),
  -- Operacional
  ('agenda', 'producao', 'geral'),
  ('vistorias', 'producao', 'geral'),
  ('manutencao', 'producao', 'geral'),
  ('chaves', 'producao', 'geral'),
  ('campo', 'producao', 'geral'),
  ('seguros', 'producao', 'geral'),
  -- Marketing & Comunicação
  ('marketing', 'producao', 'geral'),
  ('emails', 'producao', 'geral'),
  ('whatsapp', 'producao', 'geral'),
  ('meta-ads', 'producao', 'geral'),
  ('notificacoes', 'producao', 'geral'),
  -- Documentos
  ('documentos', 'producao', 'geral'),
  ('assinaturas', 'producao', 'geral'),
  ('dimob', 'producao', 'geral'),
  ('relatorios', 'producao', 'geral'),
  -- Portais & Site
  ('portal-cliente', 'producao', 'geral'),
  ('portal', 'producao', 'geral'),
  ('site', 'producao', 'geral'),
  -- Analytics & IA
  ('bi', 'producao', 'geral'),
  ('matching', 'producao', 'geral'),
  ('gamificacao', 'producao', 'geral'),
  -- Standalone
  ('distribuicao', 'producao', 'geral'),
  ('filiais', 'producao', 'geral'),
  ('configuracoes', 'producao', 'geral'),
  -- Painel de Controle (admin only — tipo_pagina = 'administrativa')
  ('usuarios', 'producao', 'administrativa'),
  ('admin', 'producao', 'administrativa'),
  ('log-acoes', 'producao', 'administrativa')
ON CONFLICT (nome_pagina) DO UPDATE SET
  status = EXCLUDED.status,
  tipo_pagina = EXCLUDED.tipo_pagina;

-- 2. Set jraphaelsst@noctusai.com as admin
--    Profiles table has NOT NULL on: nome, email, telefone.
--    COALESCE handles missing metadata gracefully.
INSERT INTO erp.profiles (id, nome, email, telefone)
SELECT
  id,
  COALESCE(NULLIF(raw_user_meta_data->>'full_name', ''), split_part(email, '@', 1)),
  email,
  COALESCE(NULLIF(raw_user_meta_data->>'phone', ''), '')
FROM auth.users
WHERE email = 'jraphaelsst@noctusai.com'
ON CONFLICT (id) DO NOTHING;

-- 3. Assign admin role (skip if already exists)
INSERT INTO erp.user_roles (user_id, role)
SELECT id, 'admin'::erp.app_role
FROM auth.users
WHERE email = 'jraphaelsst@noctusai.com'
ON CONFLICT (user_id, role) DO NOTHING;

-- 4. Verify
SELECT 'status_pagina rows' AS check_name, count(*)::text AS result FROM erp.status_pagina
UNION ALL
SELECT 'admin role assigned', count(*)::text FROM erp.user_roles ur
  JOIN auth.users u ON u.id = ur.user_id
  WHERE u.email = 'jraphaelsst@noctusai.com' AND ur.role = 'admin';
