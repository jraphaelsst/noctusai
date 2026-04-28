-- Therapy Platform: Page status (feature flags / dev-gated pages)
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS therapy.status_pagina (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_pagina TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
  descricao TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE therapy.status_pagina ENABLE ROW LEVEL SECURITY;

-- All authenticated users can see producao pages
CREATE POLICY "Todos veem paginas em producao" ON therapy.status_pagina FOR SELECT
  USING (status = 'producao');

-- Seed current routes (admin)
INSERT INTO therapy.status_pagina (nome_pagina, status) VALUES
  -- Admin routes
  ('admin-dashboard', 'producao'),
  ('admin-terapeutas', 'producao'),
  ('admin-clinicas', 'producao'),
  ('admin-pacientes', 'producao'),
  ('admin-agendamentos', 'producao'),
  ('admin-financeiro', 'producao'),
  ('admin-reembolsos', 'producao'),
  ('admin-configuracoes', 'producao'),
  ('admin-prompts-ia', 'producao'),
  ('admin-suporte', 'producao'),
  ('admin-moderacao', 'producao'),
  ('admin-alertas-crise', 'producao'),
  ('admin-avaliacoes', 'producao'),
  -- Clinic routes
  ('clinic-dashboard', 'producao'),
  ('clinic-terapeutas', 'producao'),
  ('clinic-pacientes', 'producao'),
  ('clinic-agendamentos', 'producao'),
  ('clinic-financeiro', 'producao'),
  ('clinic-mensagens', 'producao'),
  ('clinic-avaliacoes', 'producao'),
  ('clinic-configuracoes', 'producao'),
  -- Therapist routes
  ('therapist-dashboard', 'producao'),
  ('therapist-agenda', 'producao'),
  ('therapist-pacientes', 'producao'),
  ('therapist-sessoes', 'producao'),
  ('therapist-prontuario', 'producao'),
  ('therapist-financeiro', 'producao'),
  ('therapist-tarefas', 'producao'),
  ('therapist-bi', 'producao'),
  ('therapist-alertas-crise', 'producao'),
  ('therapist-avaliacoes', 'producao'),
  ('therapist-mensagens', 'producao'),
  ('therapist-configuracoes', 'producao'),
  -- Patient routes
  ('patient-dashboard', 'producao'),
  ('patient-agenda', 'producao'),
  ('patient-sessoes', 'producao'),
  ('patient-jornada', 'producao'),
  ('patient-humor', 'producao'),
  ('patient-diario', 'producao'),
  ('patient-tarefas', 'producao'),
  ('patient-carteira', 'producao'),
  ('patient-recibos', 'producao'),
  ('patient-avaliacoes', 'producao'),
  ('patient-mensagens', 'producao'),
  ('patient-configuracoes', 'producao'),
  -- Directory
  ('therapists', 'producao'),
  ('clinics', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
