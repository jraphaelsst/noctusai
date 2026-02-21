-- Remover trigger que cria automaticamente metas agregadas ao criar/atualizar metas diárias
-- As metas agregadas (semanal, mensal, anual) agora só serão criadas através das configurações de metas

-- Drop trigger that auto-creates aggregated metas
DROP TRIGGER IF EXISTS metas_diaria_on_write ON public.metas;

-- A função trigger_rollup_on_diaria continua existindo caso seja necessária no futuro,
-- mas não será mais executada automaticamente