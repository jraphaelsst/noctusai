-- 1) Enum para prazo de conclusão
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'conclusao_prazo_meta') THEN
    CREATE TYPE public.conclusao_prazo_meta AS ENUM ('no_prazo', 'atrasada');
  END IF;
END $$;

-- 2) Nova coluna em metas com default e not null
ALTER TABLE public.metas
  ADD COLUMN IF NOT EXISTS conclusao_prazo public.conclusao_prazo_meta NOT NULL DEFAULT 'no_prazo';

-- 3) Trigger function para definir automaticamente e impedir alterações manuais
CREATE OR REPLACE FUNCTION public.set_conclusao_prazo()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Quando a meta for concluída agora, definir campos automaticamente
  IF TG_OP = 'UPDATE' THEN
    IF NEW.status = 'concluida' AND (OLD.status IS DISTINCT FROM 'concluida') THEN
      IF NEW.finalizada_em IS NULL THEN
        NEW.finalizada_em := now();
      END IF;
      NEW.finalizada_no_prazo := (NEW.finalizada_em::date <= NEW.data_prazo);
      NEW.conclusao_prazo := CASE
        WHEN NEW.finalizada_em::date <= NEW.data_prazo THEN 'no_prazo'
        ELSE 'atrasada'
      END;
    ELSE
      -- Bloquear alterações manuais do campo
      IF NEW.conclusao_prazo IS DISTINCT FROM OLD.conclusao_prazo THEN
        RAISE EXCEPTION 'conclusao_prazo é gerenciado pelo sistema e não pode ser alterado manualmente';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- 4) Trigger que aplica a regra antes de updates
DROP TRIGGER IF EXISTS trg_set_conclusao_prazo ON public.metas;
CREATE TRIGGER trg_set_conclusao_prazo
BEFORE UPDATE ON public.metas
FOR EACH ROW
EXECUTE FUNCTION public.set_conclusao_prazo();

-- 5) Atualizar a função de concluir meta agregada para preencher também a nova coluna
CREATE OR REPLACE FUNCTION public.concluir_meta_agrupada(p_meta_id text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_meta RECORD;
  v_result jsonb;
  v_no_prazo boolean;
BEGIN
  -- Buscar a meta
  SELECT * INTO v_meta
  FROM public.metas
  WHERE id = p_meta_id
    AND tipo IN ('semanal', 'mensal', 'anual')
    AND usuario_id = auth.uid();
    
  IF NOT FOUND THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não encontrada ou sem permissão');
  END IF;
  
  -- Verificar elegibilidade
  IF v_meta.meta_realizada < v_meta.meta_pretendida THEN
    RETURN jsonb_build_object('success', false, 'error', 'Meta não atingida. Realize: ' || v_meta.meta_realizada || '/' || v_meta.meta_pretendida);
  END IF;
  
  -- Concluir
  v_no_prazo := (CURRENT_DATE <= v_meta.data_prazo);
  
  UPDATE public.metas
  SET 
    status = 'concluida',
    finalizada_em = NOW(),
    finalizada_no_prazo = v_no_prazo,
    conclusao_prazo = CASE WHEN v_no_prazo THEN 'no_prazo' ELSE 'atrasada' END::public.conclusao_prazo_meta,
    updated_at = NOW()
  WHERE id = p_meta_id;
  
  RETURN jsonb_build_object('success', true, 'message', 'Meta concluída com sucesso');
END;
$function$;