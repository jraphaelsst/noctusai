-- Adicionar coluna para identificar tipo de página
ALTER TABLE public.status_pagina 
ADD COLUMN IF NOT EXISTS tipo_pagina TEXT NOT NULL DEFAULT 'geral';

-- Atualizar páginas existentes como administrativas
UPDATE public.status_pagina 
SET tipo_pagina = 'administrativa'
WHERE nome_pagina IN ('usuarios', 'admin');

-- Remover políticas existentes
DROP POLICY IF EXISTS "Todos podem ver páginas em produção" ON public.status_pagina;
DROP POLICY IF EXISTS "Devs e admins podem ver todas as páginas" ON public.status_pagina;
DROP POLICY IF EXISTS "Apenas admins podem gerenciar páginas" ON public.status_pagina;

-- Política: Todos podem ver páginas gerais em produção
CREATE POLICY "Todos podem ver páginas gerais em produção"
ON public.status_pagina
FOR SELECT
USING (status = 'producao' AND tipo_pagina = 'geral');

-- Política: Admins podem ver todas as páginas
CREATE POLICY "Admins podem ver todas as páginas"
ON public.status_pagina
FOR SELECT
USING (has_role(auth.uid(), 'admin'::app_role));

-- Política: Devs podem ver páginas gerais em desenvolvimento (mas não administrativas)
CREATE POLICY "Devs podem ver páginas gerais em desenvolvimento"
ON public.status_pagina
FOR SELECT
USING (
  has_role(auth.uid(), 'dev'::app_role) 
  AND tipo_pagina = 'geral'
);

-- Política: Apenas admins podem gerenciar páginas
CREATE POLICY "Apenas admins podem gerenciar páginas"
ON public.status_pagina
FOR ALL
USING (has_role(auth.uid(), 'admin'::app_role))
WITH CHECK (has_role(auth.uid(), 'admin'::app_role));