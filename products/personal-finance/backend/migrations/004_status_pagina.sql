-- Personal Finance: Page status (feature flags / dev-gated pages)
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS "personal-finance".status_pagina (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_pagina TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
  descricao TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE "personal-finance".status_pagina ENABLE ROW LEVEL SECURITY;

-- All authenticated users can see producao pages
CREATE POLICY "Todos veem paginas em producao" ON "personal-finance".status_pagina FOR SELECT
  USING (status = 'producao');

-- Dev/owner see all non-desativado (via app-layer check + service role)
-- Admin manages via service role (get_admin_client bypasses RLS)

-- Seed current routes
INSERT INTO "personal-finance".status_pagina (nome_pagina, status) VALUES
  ('dashboard', 'producao'),
  ('contas', 'producao'),
  ('transacoes', 'producao'),
  ('categorias', 'producao'),
  ('orcamentos', 'producao'),
  ('metas', 'producao'),
  ('recorrentes', 'producao'),
  ('carteira', 'producao'),
  ('watchlist', 'producao'),
  ('operacoes', 'producao'),
  ('patrimonio', 'producao'),
  ('relatorios', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
