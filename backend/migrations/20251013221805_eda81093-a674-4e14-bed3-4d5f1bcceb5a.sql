-- Add impediment tracking columns to metas table
ALTER TABLE public.metas
ADD COLUMN tem_impedimento BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN motivo_impedimento TEXT;

-- Add check constraint to ensure motivo_impedimento is not empty when tem_impedimento is true
ALTER TABLE public.metas
ADD CONSTRAINT check_motivo_impedimento
CHECK (
  (tem_impedimento = false) OR 
  (tem_impedimento = true AND motivo_impedimento IS NOT NULL AND trim(motivo_impedimento) <> '')
);

-- Create index for better query performance when filtering by impedimentos
CREATE INDEX idx_metas_tem_impedimento ON public.metas(tem_impedimento) WHERE tem_impedimento = true;

-- Add comment to explain the columns
COMMENT ON COLUMN public.metas.tem_impedimento IS 
'Indica se a meta possui algum impedimento que impossibilita sua execução';

COMMENT ON COLUMN public.metas.motivo_impedimento IS 
'Descrição detalhada do impedimento que está bloqueando a meta. Obrigatório quando tem_impedimento = true';