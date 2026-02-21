-- Criar tabela status_pagina
CREATE TABLE IF NOT EXISTS public.status_pagina (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_pagina text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento')),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.status_pagina ENABLE ROW LEVEL SECURITY;

-- Políticas RLS
CREATE POLICY "Todos podem ver páginas em produção"
ON public.status_pagina
FOR SELECT
USING (status = 'producao');

CREATE POLICY "Devs podem ver todas as páginas"
ON public.status_pagina
FOR SELECT
USING (has_role(auth.uid(), 'dev') OR has_role(auth.uid(), 'admin'));

CREATE POLICY "Admins podem gerenciar páginas"
ON public.status_pagina
FOR ALL
USING (has_role(auth.uid(), 'admin'));

-- Inserir páginas atuais do sistema
INSERT INTO public.status_pagina (nome_pagina, status) VALUES
  ('dashboard', 'producao'),
  ('metas', 'producao'),
  ('usuarios', 'producao'),
  ('admin', 'producao'),
  ('funil', 'desenvolvimento'),
  ('clientes', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;

-- Atribuir role dev ao usuário joaoraphaelsst@gmail.com
INSERT INTO public.user_roles (user_id, role)
SELECT id, 'dev'::app_role
FROM auth.users
WHERE email = 'joaoraphaelsst@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;