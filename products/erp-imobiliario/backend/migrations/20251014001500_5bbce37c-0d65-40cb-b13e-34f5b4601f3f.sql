-- Remover políticas existentes na tabela status_pagina
DROP POLICY IF EXISTS "Admins podem gerenciar páginas" ON public.status_pagina;
DROP POLICY IF EXISTS "Devs podem ver todas as páginas" ON public.status_pagina;
DROP POLICY IF EXISTS "Todos podem ver páginas em produção" ON public.status_pagina;

-- Política para permitir todos verem páginas em produção
CREATE POLICY "Todos podem ver páginas em produção"
ON public.status_pagina
FOR SELECT
USING (status = 'producao');

-- Política para devs/admins verem todas as páginas (incluindo desenvolvimento)
CREATE POLICY "Devs e admins podem ver todas as páginas"
ON public.status_pagina
FOR SELECT
USING (
  has_role(auth.uid(), 'dev'::app_role) OR 
  has_role(auth.uid(), 'admin'::app_role)
);

-- Apenas admins podem gerenciar as páginas (insert, update, delete)
CREATE POLICY "Apenas admins podem gerenciar páginas"
ON public.status_pagina
FOR ALL
USING (has_role(auth.uid(), 'admin'::app_role))
WITH CHECK (has_role(auth.uid(), 'admin'::app_role));