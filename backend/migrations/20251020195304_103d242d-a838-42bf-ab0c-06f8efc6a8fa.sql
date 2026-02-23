-- Ajustar o trigger de validação de status para permitir atualizações do sistema
CREATE OR REPLACE FUNCTION public.validar_alteracao_status_meta()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
BEGIN
  -- Permitir se for admin
  IF public.has_role(auth.uid(), 'admin') THEN
    RETURN NEW;
  END IF;
  
  -- Permitir se não há usuário autenticado (chamadas do sistema/funções internas)
  IF auth.uid() IS NULL THEN
    RETURN NEW;
  END IF;
  
  -- Permitir alteração para 'concluida' (conclusão manual)
  IF NEW.status = 'concluida' AND OLD.status != 'concluida' THEN
    RETURN NEW;
  END IF;
  
  -- Bloquear alterações de status diferentes de conclusão por não-admins
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status != 'concluida' THEN
    RAISE EXCEPTION 'O status da meta é atualizado automaticamente pelo sistema';
  END IF;
  
  RETURN NEW;
END;
$$;

-- Criar enum para nível de performance
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'nivel_performance_meta') THEN
        CREATE TYPE nivel_performance_meta AS ENUM ('baixo', 'regular', 'bom', 'excelente');
    END IF;
END $$;

-- Adicionar coluna de nível de performance na tabela metas se não existir
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'metas' AND column_name = 'nivel_performance'
    ) THEN
        ALTER TABLE public.metas
        ADD COLUMN nivel_performance nivel_performance_meta DEFAULT 'baixo' NOT NULL;
    END IF;
END $$;

-- Criar função para calcular e atualizar o nível de performance
CREATE OR REPLACE FUNCTION public.calcular_nivel_performance(p_meta_realizada INTEGER, p_meta_pretendida INTEGER)
RETURNS nivel_performance_meta
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_progresso NUMERIC;
BEGIN
  IF p_meta_pretendida = 0 THEN
    RETURN 'baixo';
  END IF;
  
  v_progresso := (p_meta_realizada::NUMERIC / p_meta_pretendida::NUMERIC) * 100;
  
  IF v_progresso >= 100 THEN
    RETURN 'excelente';
  ELSIF v_progresso >= 80 THEN
    RETURN 'bom';
  ELSIF v_progresso >= 50 THEN
    RETURN 'regular';
  ELSE
    RETURN 'baixo';
  END IF;
END;
$$;

-- Criar função de trigger para atualizar automaticamente o nível de performance
CREATE OR REPLACE FUNCTION public.atualizar_nivel_performance()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
BEGIN
  -- Calcular e definir o nível de performance automaticamente
  NEW.nivel_performance := calcular_nivel_performance(
    COALESCE(NEW.meta_realizada, 0),
    NEW.meta_pretendida
  );
  
  RETURN NEW;
END;
$$;

-- Criar trigger para atualizar performance em INSERT e UPDATE
DROP TRIGGER IF EXISTS trigger_atualizar_nivel_performance ON public.metas;
CREATE TRIGGER trigger_atualizar_nivel_performance
  BEFORE INSERT OR UPDATE OF meta_realizada, meta_pretendida ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.atualizar_nivel_performance();

-- Atualizar performance de todas as metas existentes
UPDATE public.metas
SET nivel_performance = calcular_nivel_performance(
  COALESCE(meta_realizada, 0),
  meta_pretendida
);

-- Criar função para proteger alterações manuais do nível de performance
CREATE OR REPLACE FUNCTION public.validar_alteracao_nivel_performance()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
BEGIN
  -- Permitir se for admin
  IF public.has_role(auth.uid(), 'admin') THEN
    RETURN NEW;
  END IF;
  
  -- Permitir se não há usuário autenticado (chamadas do sistema)
  IF auth.uid() IS NULL THEN
    RETURN NEW;
  END IF;
  
  -- Bloquear alterações manuais do nível de performance
  IF OLD.nivel_performance IS DISTINCT FROM NEW.nivel_performance THEN
    -- Se a mudança não veio do trigger de atualização, bloquear
    IF NEW.nivel_performance != calcular_nivel_performance(COALESCE(NEW.meta_realizada, 0), NEW.meta_pretendida) THEN
      RAISE EXCEPTION 'O nível de performance é calculado automaticamente e não pode ser alterado manualmente';
    END IF;
  END IF;
  
  RETURN NEW;
END;
$$;

-- Criar trigger de validação (executado após o trigger de atualização)
DROP TRIGGER IF EXISTS trigger_validar_nivel_performance ON public.metas;
CREATE TRIGGER trigger_validar_nivel_performance
  BEFORE UPDATE ON public.metas
  FOR EACH ROW
  EXECUTE FUNCTION public.validar_alteracao_nivel_performance();